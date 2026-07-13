"""Per-step agent trace — observability, not business logic. No genai imports."""

import json

from soccer_agent import db


def save_step(session_id: str, turn_id: int, step: int, content: dict) -> None:
    """Persist one step of the agent loop to the trace table."""
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO agent_trace (session_id, turn_id, step, content)
               VALUES (%s, %s, %s, %s::jsonb)""",
            (session_id, turn_id, step, json.dumps(content)),
        )


def get_turn_trace(session_id: str, turn_id: int) -> list[dict]:
    """Return all steps for one turn, ordered by step."""
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT step, content FROM agent_trace
               WHERE session_id = %s AND turn_id = %s
               ORDER BY step""",
            (session_id, turn_id),
        ).fetchall()
    return [{"step": r[0], "content": r[1]} for r in rows]


def get_session_trace(session_id: str) -> list[dict]:
    """Return all turns + steps for a session, ordered chronologically."""
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT turn_id, step, content FROM agent_trace
               WHERE session_id = %s
               ORDER BY turn_id, step""",
            (session_id,),
        ).fetchall()
    return [{"turn_id": r[0], "step": r[1], "content": r[2]} for r in rows]


def get_last_turn_id(session_id: str) -> int:
    """Return the highest turn_id for a session, or 0 if no trace exists."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(turn_id), 0) FROM agent_trace WHERE session_id = %s",
            (session_id,),
        ).fetchone()
    return row[0]
