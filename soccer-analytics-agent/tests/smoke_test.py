"""One-shot end-to-end check: real Gemini + real DB."""

import os

from dotenv import load_dotenv
from google import genai
from soccer_agent.loop import run_turn


def main() -> None:
    load_dotenv()
    client = genai.Client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    question = (
        "How many official matches has Argentina played, and how many did it win?"
    )
    answer, history = run_turn(client, [], question, model=model)
    tool_rounds = sum(
        1
        for c in history
        if c.role == "user"
        and any(getattr(p, "function_response", None) for p in c.parts)
    )
    print(f"Q: {question}\nA: {answer}\n(tool rounds: {tool_rounds})")
    assert tool_rounds >= 1, "expected the model to use sql_query at least once"
    assert answer.strip(), "expected a non-empty answer"
    print("SMOKE TEST OK")


if __name__ == "__main__":
    main()
