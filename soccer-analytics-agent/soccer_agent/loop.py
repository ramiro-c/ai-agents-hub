"""Hand-written agent loop: model -> tool calls -> tool results -> model."""

import time

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
    "proper date literals (DATE '2022-12-18').\n\n"
    "ERROR RECOVERY — when a tool call returns an error:\n"
    "1. If a specialized tool can answer the question, switch to it — "
    "do NOT keep retrying sql_query for the same intent.\n"
    "2. If using sql_query, fix the SQL and retry — you have multiple attempts.\n"
    "3. If the same approach fails twice, try a different tool or tell the user "
    "honestly what data is missing. Do not respond with only an apology."
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
    client, history: list, user_message: str, model: str, trace_ctx: dict | None = None
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
    history.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
    step = 0

    for _ in range(MAX_TOOL_ROUNDS):
        step += 1
        text_parts: list[str] = []
        fn_calls = []
        for chunk in _generate_stream(
            client, model=model, history=history, config=_config()
        ):
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
        history.append(types.Content(role="model", parts=agg_parts))

        if not fn_calls:
            if trace_ctx:
                trace.save_step(
                    trace_ctx["session_id"],
                    trace_ctx["turn_id"],
                    step,
                    {"kind": "answer", "text": full_text},
                )
            yield {"type": "done", "answer": full_text}
            return history, step

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
    client, history: list, user_message: str, model: str, trace_ctx: dict | None = None
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
    gen = run_turn_events(client, history, user_message, model, trace_ctx)
    try:
        while True:
            event = next(gen)
            if event["type"] == "done":
                answer = event["answer"]
    except StopIteration as stop:
        if stop.value is not None:
            final_history, step = stop.value
    return answer, final_history, step
