"""Terminal REPL for the soccer agent."""

import os
import uuid

from dotenv import load_dotenv
from google import genai

from soccer_agent.chat import respond


def main() -> None:
    load_dotenv()
    client = genai.Client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    session_id = f"cli-{uuid.uuid4().hex[:8]}"
    print(f"Soccer agent ready (session {session_id}). Type 'exit' to quit.")
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user or user.lower() in {"exit", "quit"}:
            break
        answer = respond(client, session_id, user, model=model)
        print(f"agent> {answer}\n")


if __name__ == "__main__":
    main()
