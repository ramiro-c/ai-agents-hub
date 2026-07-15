"""Hand-written agent loop: model -> tool calls -> tool results -> model."""

from google.genai import types

from soccer_agent import trace
from soccer_agent.tools import TOOL_DECLARATIONS, dispatch

MAX_TOOL_ROUNDS = 8

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


def run_turn(
    client, history: list, user_message: str, model: str, trace_ctx: dict | None = None
) -> tuple[str, list, int]:
    """Run one conversational turn, dispatching tool calls until the model answers.

    When trace_ctx is provided (dict with 'session_id' and 'turn_id'), every
    model response and tool result is recorded to agent_trace.

    Returns (answer_text, full_history, step_count).
    """
    history = list(history)
    history.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
    step = 0

    for _ in range(MAX_TOOL_ROUNDS):
        step += 1
        response = client.models.generate_content(
            model=model, contents=history, config=_config()
        )
        content = response.candidates[0].content
        history.append(content)

        calls = [p.function_call for p in content.parts if p.function_call]
        if not calls:
            text = "".join(p.text for p in content.parts if p.text)
            if trace_ctx:
                trace.save_step(
                    trace_ctx["session_id"],
                    trace_ctx["turn_id"],
                    step,
                    {"kind": "answer", "text": text},
                )
            return text, history, step

        # Persist tool calls + results as one trace step
        tool_info = []
        result_parts = []
        for call in calls:
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

        history.append(types.Content(role="user", parts=result_parts))

    if trace_ctx:
        trace.save_step(
            trace_ctx["session_id"],
            trace_ctx["turn_id"],
            step + 1,
            {"kind": "limit_exceeded", "rounds": MAX_TOOL_ROUNDS},
        )
    return "I could not finish within the tool-call limit.", history, step + 1
