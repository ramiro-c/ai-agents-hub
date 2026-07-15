"""Storage layer for the three memory tiers. No genai imports — storage only."""

from soccer_agent import db
from soccer_agent.embeddings import embed


def render_vector(values: list[float]) -> str:
    """Render an embedding as a pgvector string literal.

    Public — shared with tools.py and scripts that insert vectors into
    the DB. Prefer this over manual string construction.
    """
    return "[" + ",".join(repr(x) for x in values) + "]"


# --- Working memory: recency, session-scoped ---


def append_working(session_id: str, role: str, content: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO working_memory (session_id, role, content) "
            "VALUES (%s, %s, %s)",
            (session_id, role, content),
        )


def load_working(session_id: str, limit: int = 10) -> list[tuple[str, str]]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM working_memory WHERE session_id = %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (session_id, limit),
        ).fetchall()
    return [(r[0], r[1]) for r in reversed(rows)]  # oldest -> newest


# --- Episodic memory: similarity, session-scoped ---

# Cosine-similarity floor for episodic recall. Contentless follow-ups
# ("show me the last 5 ones") score ~0.1-0.25 against any specific episode,
# while a genuine recall lands ~0.6+; 0.45 sits in that gap. Below it, we
# recall nothing rather than inject the nearest topically-wrong episode as
# grounding — which used to steer the model onto the wrong matchup.
MIN_EPISODE_SCORE = 0.45


def save_episode(session_id: str, user_message: str, agent_response: str) -> None:
    vec = render_vector(embed(f"{user_message}\n{agent_response}"))
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO episodic_memory "
            "(session_id, user_message, agent_response, embedding) "
            "VALUES (%s, %s, %s, %s::vector)",
            (session_id, user_message, agent_response, vec),
        )


def recall_episodes(
    session_id: str,
    query: str,
    k: int = 3,
    min_score: float = MIN_EPISODE_SCORE,
) -> list[dict]:
    vec = render_vector(embed(query))
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT user_message, agent_response, "
            "1 - (embedding <=> %s::vector) AS score "
            "FROM episodic_memory WHERE session_id = %s "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (vec, session_id, vec, k),
        ).fetchall()
    return [
        {"user_message": r[0], "agent_response": r[1], "score": float(r[2])}
        for r in rows
        if float(r[2]) >= min_score
    ]


# --- Semantic memory: similarity, global facts ---


def remember_fact(fact: str) -> None:
    vec = render_vector(embed(fact))
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO semantic_memory (fact, embedding) VALUES (%s, %s::vector)",
            (fact, vec),
        )


def search_semantic(query: str, k: int = 3) -> list[dict]:
    vec = render_vector(embed(query))
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT fact, 1 - (embedding <=> %s::vector) AS score "
            "FROM semantic_memory ORDER BY embedding <=> %s::vector LIMIT %s",
            (vec, vec, k),
        ).fetchall()
    return [{"fact": r[0], "score": float(r[1])} for r in rows]
