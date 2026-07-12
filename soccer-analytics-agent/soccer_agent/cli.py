"""Terminal REPL for the soccer agent."""

import os

from dotenv import load_dotenv
from google import genai

from soccer_agent.loop import run_turn


def main() -> None:
    load_dotenv()
    client = genai.Client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    history: list = []
    print("Soccer agent ready. Type 'exit' to quit.")
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user or user.lower() in {"exit", "quit"}:
            break
        answer, history = run_turn(client, history, user, model=model)
        print(f"agent> {answer}\n")


if __name__ == "__main__":
    main()
