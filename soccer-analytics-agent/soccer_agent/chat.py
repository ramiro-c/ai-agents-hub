"""Memory-aware turn wrapper around the pure run_turn loop."""

from google.genai import types

from soccer_agent import memory, trace
from soccer_agent.loop import run_turn


def _to_history(turns: list[tuple[str, str]]) -> list:
    """Convert stored (role, content) working-memory turns into genai Content."""
    return [
        types.Content(role=role, parts=[types.Part(text=content)])
        for role, content in turns
    ]


def _augment(user_message: str, episodes: list[dict]) -> str:
    """Prepend relevant past episodes to the user message as grounding context."""
    if not episodes:
        return user_message
    lines = "\n".join(
        f"- Earlier you asked: {e['user_message']!r} -> {e['agent_response']!r}"
        for e in episodes
    )
    return (
        f"Relevant context from earlier in this session:\n{lines}\n\n"
        f"Current question: {user_message}"
    )


def respond(client, session_id: str, user_message: str, model: str) -> str:
    """Run one memory-aware turn: seed + ground -> answer -> persist."""
    prior = _to_history(memory.load_working(session_id))
    episodes = memory.recall_episodes(session_id, user_message, k=3)
    augmented = _augment(user_message, episodes)

    turn_id = trace.get_last_turn_id(session_id) + 1
    trace_ctx = {"session_id": session_id, "turn_id": turn_id}

    answer, _, _ = run_turn(client, prior, augmented, model=model, trace_ctx=trace_ctx)

    memory.append_working(session_id, "user", user_message)  # store raw, not augmented
    memory.append_working(session_id, "model", answer)
    memory.save_episode(session_id, user_message, answer)
    return answer
