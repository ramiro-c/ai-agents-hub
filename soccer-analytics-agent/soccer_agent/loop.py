"""Hand-written agent loop: model -> tool calls -> tool results -> model."""

import time
from functools import lru_cache

from google.genai import errors, types

from soccer_agent import trace
from soccer_agent.tools import TOOL_DECLARATIONS, dispatch

MAX_TOOL_ROUNDS = 5
# Gemini's 429 (RESOURCE_EXHAUSTED) is a per-minute quota; a short backoff
# usually clears it, so transient spikes never reach the user.
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_BACKOFF_BASE_S = 2.0

SYSTEM_PROMPT = (
    "You are a soccer analytics assistant with access to a PostgreSQL database of "
    "international matches from 1872 to today. Answer in the user's language. "
    "Team names in the database are stored in English. "
    "When the user writes a team name in another language, "
    "translate it to English before embedding it in SQL. "
    "If a query returns no rows, say so honestly instead of guessing.\n\n"
    "TOOL SELECTION — always prefer the most specific tool for the question:\n"
    "- get_h2h: head-to-head record between two specific teams. "
    "Use when the user asks about previous meetings, H2H, or 'X vs Y'.\n"
    "- get_team_form: a single team's last N match results. "
    "Use when the user asks about recent form, last matches, or 'how is X doing'.\n"
    "- predict_match: win/draw/loss probabilities from a trained XGBoost model "
    "(uses Elo, form, head-to-head and goal features; falls back to an Elo "
    "heuristic only if the model is unavailable). "
    "Use when the user asks who will win or wants a prediction between two teams.\n"
    "- get_team_elo: current Elo ratings for one or two teams. "
    "Use when the user asks about Elo, ratings, or relative team strength.\n"
    "- recall: search conversation memory for facts the user mentioned earlier. "
    "Use when the user references past conversations or says 'remember'.\n"
    "- sql_query: custom SQL aggregations over the database. "
    "Use ONLY when no specialized tool covers the question "
    "(e.g., 'top scorers in 2018 WC', 'average goals per tournament').\n\n"
    "When writing SQL, use PostgreSQL syntax: EXTRACT(YEAR FROM match_date) for "
    "year filtering, ILIKE for case-insensitive text, LIMIT to cap rows, and "
    "proper date literals (DATE '2022-12-18'). "
    "The matches table has columns home_team, away_team, home_score, away_score "
    "— there is NO winner column. For 'latest', 'most recent', or winner "
    "questions, always ORDER BY match_date DESC before LIMIT so you see the "
    "newest match, not the oldest. Tournament values are 'FIFA World Cup' "
    "(finals) and 'FIFA World Cup qualification' (qualifiers): for World Cup "
    "results use exact equality tournament = 'FIFA World Cup' or exclude "
    "qualifiers with NOT LIKE '%qualification%'.\n\n"
    "ERROR RECOVERY — when a tool call returns an error:\n"
    "1. If a specialized tool can answer the question, switch to it — "
    "do NOT keep retrying sql_query for the same intent.\n"
    "2. If using sql_query, fix the SQL and retry — you have multiple attempts.\n"
    "3. If the same approach fails twice, try a different tool or tell the user "
    "honestly what data is missing. Do not respond with only an apology.\n\n"
    "GROUNDING — never answer match results, tournament winners, teams, scores, "
    "or any factual claim about matches from your memory. ALWAYS call a "
    "tool (sql_query, get_h2h, get_team_form, get_team_elo) to resolve facts "
    "before answering. If tools return no rows, missing scores (NULL), or "
    "incomplete data, state exactly what the database shows and explicitly say "
    "what is missing instead of guessing. A fact not backed by a tool result is "
    "not a fact in this conversation. "
    "COVERAGE — missing, empty, truncated, or NULL-score rows mean the dataset "
    "lacks evidence, not that the event did not occur. Never invent why (no date "
    'extrapolation, no "last update", no "too early"). Say the answer is not '
    "in this dataset (or state exactly which rows you have), that it may exist "
    "outside the database, and offer a next step (more specific query, different "
    "tool, check with a human). On user pushback, acknowledge the limitation once; "
    "do not argue; do not repeat an unsupported temporal claim. "
    "If the user challenges, doubts, or seems surprised by an answer you gave "
    "(e.g. '¿cómo?', 'estás seguro?', 'are you sure?'), "
    "DO NOT retract a tool-backed positive fact from your parametric memory — "
    "re-verify with a tool call and show the row the database returns."
)


ERROR_RETRY_REASK = (
    "[SYSTEM] The last tool call failed with an error. Inspect the error, fix your "
    "query/approach, and call the tool again. If you are sure no tool can answer, "
    "state exactly what data is missing."
)

TRUNCATION_REASK = (
    "[SYSTEM] The last query hit the 50-row cap, so this sample is not the full "
    "result. Do not conclude coverage from it. Re-query more specifically — for a "
    "tournament winner: ORDER BY match_date DESC LIMIT 1 (or a Final filter). Then "
    "answer from that result."
)

COVERAGE_REASK = (
    "[SYSTEM] Do not infer that an event did not happen from missing, empty, "
    "truncated, or incomplete tool results. Say this dataset does not contain "
    "the answer — it may exist outside this database. Do not invent why "
    "(no dates, no recency, no 'last update'). Offer a concrete next step "
    "(a more specific query, a different tool, or checking with a human). "
    "Do not argue."
)

# Lexical phrases that claim an event never occurred — used to catch post-tool
# overclaims ("the tournament would not have concluded") after incomplete samples.
_COVERAGE_OVERCLAIM_PHRASES = (
    "has not been played",
    "haven't been played",
    "hasn't been played",
    "would not have concluded",
    "wouldn't have concluded",
    "has not taken place",
    "hasn't taken place",
    "hasn't happened",
    "last data update",
    "no se ha jugado",
    "no habría concluido",
)


def _is_coverage_overclaim(text: str) -> bool:
    """True when text claims an event did not occur."""
    lowered = text.lower()
    return any(phrase in lowered for phrase in _COVERAGE_OVERCLAIM_PHRASES)


# Grounding enforcement. Prompt instructions alone are not enough: Gemini's
# parametric prior can outweigh them (e.g. "the 2026 World Cup has not been
# played yet"). If the model tries to answer a factual match question on the
# first pass without calling any tool, the loop injects exactly ONE re-ask
# that forces a tool round, then accepts whatever comes next. Never nudges
# more than once per user message, and never nudges non-factual queries.
_QUESTION_HINTS = (
    "who ",
    "what ",
    "when ",
    "where ",
    "why ",
    "how ",
    "which ",
    "¿qué",
    "¿quién",
    "¿cuál",
    "¿cómo",
    "¿cuándo",
    "¿dónde",
    "?",
    "won",
    "score",
    "result",
    "ganó",
)
_FACT_HINTS = (
    "match",
    "game",
    "team",
    "tournament",
    "cup",
    "world cup",
    "champion",
    "winner",
    "goal",
    "score",
    "result",
    "won",
    "beat",
    "defeat",
    "h2h",
    "form",
    "elo",
    "prediction",
    "partido",
    "torneo",
    "copa",
    "campeón",
    "gol",
    "marcador",
    "resultado",
    "equipo",
)
GROUNDING_REASK = (
    "[SYSTEM] You must call a tool from your available functions before "
    "answering this question. Query the database for match facts. If the tools "
    "cannot answer definitively, state exactly what data is missing."
)

# Follow-up challenge enforcement. The grounding nudge above only fires when
# the user message itself contains fact vocabulary ("match", "team", ...), but
# the most dangerous retraction happens AFTER a grounded answer: the user
# challenges it ("¿cómo?", "estás seguro?", "are you sure?") and the model
# folds to its parametric prior, contradicting the tool result it just saw.
# When the model answers such a challenge with plain text and no tool call,
# inject exactly ONE re-verification re-ask, then accept whatever comes next.
_CHALLENGE_HINTS = (
    "como?",
    "cómo?",
    "¿cómo?",
    "¿como?",
    "como es posible",
    "cómo es posible",
    "estás seguro",
    "estas seguro",
    "are you sure",
    "really?",
    "en serio?",
    "no puede ser",
    "no es posible",
    "no es cierto",
    "no creo",
    "no me digas",
    "imposible",
    "impossible",
    "that can't",
    "eso no",
    "no es así",
    "wrong",
    "incorrect",
    "mentira",
)
CHALLENGE_REASK = (
    "[SYSTEM] The user is questioning your previous answer. "
    "If that answer was backed by tool results, do NOT retract a tool-backed "
    "positive fact from parametric memory — re-run a tool call to re-verify and "
    "show the row. "
    "If the prior answer was incomplete or 'I don't know', refine the query "
    "(e.g. winner → latest match / Final). If still no definitive row, say it "
    "is not in this dataset without explaining why. Do not argue."
)

# Semantic layer for challenge detection: MiniLM embeddings of curated
# challenge exemplars, compared by cosine against the current user message.
# Layer 1 (lexical hints) is zero-latency and precise; layer 2 catches
# paraphrases the list cannot enumerate. Threshold 0.80 was tuned empirically:
# true positives ("no te creo" 0.845, "estás de joda" 0.813) vs worst observed
# false positive ("¿cómo estás?" 0.679). If embeddings are unavailable this
# layer degrades to False and the lexical layer still works.
_CHALLENGE_EXEMPLARS = (
    "¿es un chiste?",
    "estás jodiendo",
    "no me la creo",
    "eso no tiene sentido",
    "eso no me cuadra",
    "te equivocás",
    "no es verdad",
    "no jodas",
    "are you serious?",
    "you must be joking",
    "that's ridiculous",
    "no way",
    "this can't be true",
)
CHALLENGE_SIMILARITY_THRESHOLD = 0.80


@lru_cache(maxsize=1)
def _challenge_exemplar_vectors() -> tuple[list[float], ...]:
    """Embedded exemplars, computed once per process."""
    from soccer_agent.embeddings import embed_batch

    return tuple(embed_batch(_CHALLENGE_EXEMPLARS))


def _semantic_is_challenge(message: str) -> bool:
    try:
        from soccer_agent.embeddings import cosine_similarity, embed

        vector = embed(message)
        return (
            max(
                cosine_similarity(vector, exemplar)
                for exemplar in _challenge_exemplar_vectors()
            )
            >= CHALLENGE_SIMILARITY_THRESHOLD
        )
    except (ImportError, OSError, RuntimeError, ValueError):
        return False


def _is_challenge(message: str) -> bool:
    """True when the user message signals doubt about a previous answer."""
    lowered = message.lower()
    if any(hint in lowered for hint in _CHALLENGE_HINTS):
        return True
    return _semantic_is_challenge(message)


def _has_prior_model_turn(history: list) -> bool:
    """True when incoming history already contains a model answer to challenge."""
    return any(getattr(content, "role", None) == "model" for content in history)


def _needs_grounding(query: str) -> bool:
    """True when a user question plausibly asks for database-backed match facts."""
    lowered = query.lower()
    return any(hint in lowered for hint in _QUESTION_HINTS) and any(
        hint in lowered for hint in _FACT_HINTS
    )


def _config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
    )


def _generate(client, *, model, history, config):
    """Call the model, retrying with exponential backoff on 429 rate limits.

    A 429 usually means the per-minute quota was hit; waiting a couple of
    seconds and retrying clears it transparently. Any other error, or an
    exhausted retry budget, propagates to the caller (blocking sleep is fine —
    this runs in a worker thread, not the event loop).
    """
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            return client.models.generate_content(
                model=model, contents=history, config=config
            )
        except errors.ClientError as exc:
            if exc.code != 429 or attempt == RATE_LIMIT_RETRIES:
                raise
            time.sleep(RATE_LIMIT_BACKOFF_BASE_S * 2**attempt)


def _generate_stream(client, *, model, history, config):
    """Stream a model response, retrying on 429 only before the first chunk.

    Mirrors ``_generate``'s backoff, but a stream can only be safely retried
    while nothing has been yielded yet — once chunks flow, re-issuing the call
    would duplicate them, so a mid-stream 429 propagates to the caller (surfaced
    as an ``error`` event). The common case (429 on the very first call) is
    still retried transparently.
    """
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        started = False
        try:
            stream = client.models.generate_content_stream(
                model=model, contents=history, config=config
            )
            for chunk in stream:
                started = True
                yield chunk
            return
        except errors.ClientError as exc:
            if started or exc.code != 429 or attempt == RATE_LIMIT_RETRIES:
                raise
            time.sleep(RATE_LIMIT_BACKOFF_BASE_S * 2**attempt)


def run_turn_events(
    client,
    history: list,
    user_message: str,
    model: str,
    trace_ctx: dict | None = None,
    *,
    classify_as: str | None = None,
):
    """Run one turn as a stream of events, dispatching tool calls until answered.

    Yields dicts describing live progress, in order:
      - {"type": "tool_call", "calls": [...]}  once per tool round
      - {"type": "delta", "text": ...}         per text chunk of the final answer
      - {"type": "done", "answer": ...}        exactly once, when the turn ends

    Text is streamed live only while no function_call has been seen in the
    current round; because Gemini emits function_call parts before any text when
    it decides to call a tool, tool-round reasoning text is naturally suppressed.
    In the rare case where the model streams text *before* a function_call in the
    same round, a little interim text may leak — accepted as an edge case rather
    than buffering (which would defeat live streaming).

    When trace_ctx is provided (dict with 'session_id' and 'turn_id'), every
    model response and tool result is recorded to agent_trace, exactly as the
    blocking path did.

    Returns (full_history, step_count) via StopIteration.value so the drainer
    below can reconstruct run_turn's original contract.
    """
    history = list(history)
    prior_model_turn = _has_prior_model_turn(history)
    classifier_text = user_message if classify_as is None else classify_as
    history.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
    step = 0
    grounding_nudge_used = False
    challenge_nudge_used = False
    any_tool_calls_this_turn = False
    error_retry_used = False
    truncation_nudge_used = False
    coverage_nudge_used = False
    last_tool_error = False
    last_tool_truncated = False

    for _ in range(MAX_TOOL_ROUNDS):
        step += 1
        text_parts: list[str] = []
        fn_calls = []
        for chunk in _generate_stream(
            client, model=model, history=history, config=_config()
        ):
            if not chunk.candidates:
                # Safety block / MAX_TOKENS finish: no candidate to read.
                continue
            candidate = chunk.candidates[0]
            if not candidate.content or not candidate.content.parts:
                continue
            for part in candidate.content.parts:
                if part.function_call:
                    fn_calls.append(part.function_call)
                elif part.text:
                    text_parts.append(part.text)
                    if not fn_calls:
                        yield {"type": "delta", "text": part.text}

        full_text = "".join(text_parts)

        # Rebuild the aggregated model turn for history (text first, then calls).
        agg_parts = []
        if full_text:
            agg_parts.append(types.Part(text=full_text))
        for call in fn_calls:
            agg_parts.append(types.Part(function_call=call))
        if agg_parts:
            history.append(types.Content(role="model", parts=agg_parts))

        if not fn_calls:
            if not full_text:
                # Every chunk was empty (safety block, MAX_TOKENS finish, or a
                # response filtered entirely by the guards above): complete the
                # turn with a graceful message instead of an empty answer.
                full_text = (
                    "I could not generate a response this time. Please try again."
                )
            if (
                not grounding_nudge_used
                and not any_tool_calls_this_turn
                and _needs_grounding(classifier_text)
            ):
                # Bounded grounding enforcement: the model tried to answer a
                # factual question without calling any tool. Inject ONE re-ask
                # forcing a tool round, then continue the loop.
                grounding_nudge_used = True
                history.append(
                    types.Content(role="user", parts=[types.Part(text=GROUNDING_REASK)])
                )
                continue
            if (
                not challenge_nudge_used
                and not any_tool_calls_this_turn
                and prior_model_turn
                and _is_challenge(classifier_text)
            ):
                # Bounded challenge enforcement: the user doubts a previous
                # answer and the model folds to memory without re-verifying.
                # Inject ONE re-ask that forces a tool round, then continue.
                challenge_nudge_used = True
                history.append(
                    types.Content(role="user", parts=[types.Part(text=CHALLENGE_REASK)])
                )
                continue
            if (
                not error_retry_used
                and last_tool_error
                and _needs_grounding(classifier_text)
            ):
                # Bounded error-driven retry: the last tool round errored and the
                # model still tried to answer from memory. Inject ONE retry that
                # forces it to fix the query/approach, then continue the loop.
                error_retry_used = True
                history.append(
                    types.Content(
                        role="user", parts=[types.Part(text=ERROR_RETRY_REASK)]
                    )
                )
                continue
            if not truncation_nudge_used and last_tool_truncated:
                # Bounded truncation enforcement: the last tool round returned a
                # capped sample and the model tried to answer from it. Inject ONE
                # re-ask that forces a more specific query, then continue the loop.
                truncation_nudge_used = True
                history.append(
                    types.Content(
                        role="user", parts=[types.Part(text=TRUNCATION_REASK)]
                    )
                )
                continue
            if not coverage_nudge_used and _is_coverage_overclaim(full_text):
                # Bounded coverage-overclaim enforcement: the model claimed an
                # event never happened (from incomplete results or memory).
                # Runs after grounding/challenge/error/truncation nudges.
                # Inject ONE re-ask, then continue the loop.
                coverage_nudge_used = True
                history.append(
                    types.Content(role="user", parts=[types.Part(text=COVERAGE_REASK)])
                )
                continue
            if trace_ctx:
                trace.save_step(
                    trace_ctx["session_id"],
                    trace_ctx["turn_id"],
                    step,
                    {"kind": "answer", "text": full_text},
                )
            yield {"type": "done", "answer": full_text}
            return history, step

        any_tool_calls_this_turn = True
        # Persist tool calls + results as one trace step
        tool_info = []
        result_parts = []
        for call in fn_calls:
            result = dispatch(call.name, dict(call.args))
            tool_info.append(
                {
                    "tool": call.name,
                    "args": dict(call.args),
                    "result": result,
                }
            )
            result_parts.append(
                types.Part.from_function_response(
                    name=call.name,
                    response={"result": result},
                )
            )

        if trace_ctx:
            trace.save_step(
                trace_ctx["session_id"],
                trace_ctx["turn_id"],
                step,
                {"kind": "tool_calls", "calls": tool_info},
            )

        yield {"type": "tool_call", "calls": tool_info}
        last_tool_error = any(
            isinstance(ti["result"], dict) and "error" in ti["result"]
            for ti in tool_info
        )
        last_tool_truncated = any(
            isinstance(ti["result"], dict) and ti["result"].get("truncated") is True
            for ti in tool_info
        )
        history.append(types.Content(role="user", parts=result_parts))

    if trace_ctx:
        trace.save_step(
            trace_ctx["session_id"],
            trace_ctx["turn_id"],
            step + 1,
            {"kind": "limit_exceeded", "rounds": MAX_TOOL_ROUNDS},
        )
    fallback = "I could not finish within the tool-call limit."
    yield {"type": "done", "answer": fallback}
    return history, step + 1


def run_turn(
    client,
    history: list,
    user_message: str,
    model: str,
    trace_ctx: dict | None = None,
    *,
    classify_as: str | None = None,
) -> tuple[str, list, int]:
    """Run one conversational turn, dispatching tool calls until the model answers.

    Thin drainer over ``run_turn_events``: consumes the event stream and
    reconstructs the original blocking contract so ``/api/chat`` and existing
    tests keep working unchanged.

    Returns (answer_text, full_history, step_count).
    """
    answer = ""
    final_history = list(history)
    step = 0
    gen = run_turn_events(
        client, history, user_message, model, trace_ctx, classify_as=classify_as
    )
    try:
        while True:
            event = next(gen)
            if event["type"] == "done":
                answer = event["answer"]
    except StopIteration as stop:
        if stop.value is not None:
            final_history, step = stop.value
    return answer, final_history, step
