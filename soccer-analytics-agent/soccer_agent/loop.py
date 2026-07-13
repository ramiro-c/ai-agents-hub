"""Hand-written agent loop: model -> tool calls -> tool results -> model."""

from google.genai import types

from soccer_agent import trace
from soccer_agent.tools import TOOL_DECLARATIONS, dispatch

MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = (
    "You are a soccer analytics assistant with access to a database of "
    "international matches from 1872 to today. Use the sql_query tool to "
    "ground every factual answer in data. Answer in the user's language. "
    "If a query returns no rows, say so honestly instead of guessing."
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
