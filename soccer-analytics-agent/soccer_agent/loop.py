"""Hand-written agent loop: model -> tool calls -> tool results -> model."""

from google.genai import types

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


def run_turn(client, history: list, user_message: str, model: str) -> tuple[str, list]:
    """Run one conversational turn, dispatching tool calls until the model answers."""
    history = list(history)
    history.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.models.generate_content(
            model=model, contents=history, config=_config()
        )
        content = response.candidates[0].content
        history.append(content)

        calls = [p.function_call for p in content.parts if p.function_call]
        if not calls:
            text = "".join(p.text for p in content.parts if p.text)
            return text, history

        result_parts = [
            types.Part.from_function_response(
                name=call.name,
                response={"result": dispatch(call.name, dict(call.args))},
            )
            for call in calls
        ]
        history.append(types.Content(role="user", parts=result_parts))

    return "I could not finish within the tool-call limit.", history
