"""Memory-aware turn wrapper around the pure run_turn loop."""

from google.genai import types

from soccer_agent import memory, trace
from soccer_agent.loop import run_turn, run_turn_events


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


def respond(client, session_id: str, user_message: str, model: str) -> tuple[str, int]:
    """Run one memory-aware turn: seed + ground -> answer -> persist.

    Returns ``(answer, turn_id)`` so callers can associate the persisted trace
    (which is keyed by ``turn_id``) with this exact turn instead of guessing it.
    """
    prior = _to_history(memory.load_working(session_id))
    episodes = memory.recall_episodes(session_id, user_message, k=3)
    augmented = _augment(user_message, episodes)

    turn_id = trace.get_last_turn_id(session_id) + 1
    trace_ctx = {"session_id": session_id, "turn_id": turn_id}

    answer, _, _ = run_turn(client, prior, augmented, model=model, trace_ctx=trace_ctx)

    memory.append_working(session_id, "user", user_message)  # store raw, not augmented
    memory.append_working(session_id, "model", answer)
    memory.save_episode(session_id, user_message, answer)
    return answer, turn_id


def respond_stream(client, session_id: str, user_message: str, model: str):
    """Streaming twin of ``respond``: same seed/ground/turn_id, live events.

    Forwards ``tool_call`` and ``delta`` events as they arrive, then persists
    working memory + episode only once the turn reaches ``done`` (so a stream
    that errors mid-flight never stores a partial answer). The ``done`` event is
    enriched with ``session_id`` and ``turn_id`` for the client to reconcile.
    """
    prior = _to_history(memory.load_working(session_id))
    episodes = memory.recall_episodes(session_id, user_message, k=3)
    augmented = _augment(user_message, episodes)

    turn_id = trace.get_last_turn_id(session_id) + 1
    trace_ctx = {"session_id": session_id, "turn_id": turn_id}

    gen = run_turn_events(client, prior, augmented, model=model, trace_ctx=trace_ctx)
    try:
        while True:
            event = next(gen)
            if event["type"] == "done":
                answer = event["answer"]
                memory.append_working(session_id, "user", user_message)  # raw
                memory.append_working(session_id, "model", answer)
                memory.save_episode(session_id, user_message, answer)
                yield {
                    "type": "done",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "answer": answer,
                }
            else:
                yield event
    except StopIteration:
        pass
