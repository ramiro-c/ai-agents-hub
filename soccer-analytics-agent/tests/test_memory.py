import pytest
from soccer_agent import memory

from tests.test_db import requires_db


@pytest.mark.integration
@requires_db
def test_working_memory_roundtrip_is_ordered():
    from soccer_agent import db

    session = "test-working"
    with db.connect() as conn:
        conn.execute("DELETE FROM working_memory WHERE session_id = %s", (session,))
    memory.append_working(session, "user", "first")
    memory.append_working(session, "model", "second")
    assert memory.load_working(session) == [("user", "first"), ("model", "second")]


@pytest.mark.integration
@requires_db
def test_semantic_recall_ranks_relevant_fact_first():
    from soccer_agent import db

    with db.connect() as conn:
        conn.execute("DELETE FROM semantic_memory")
    memory.remember_fact("The user supports Argentina")
    memory.remember_fact("The office coffee machine is broken")
    top = memory.search_semantic("which national team does the user like?", k=1)
    assert top[0]["fact"] == "The user supports Argentina"


@pytest.mark.integration
@requires_db
def test_episodic_recall_finds_similar_past_turn():
    from soccer_agent import db

    session = "test-episodic"
    with db.connect() as conn:
        conn.execute("DELETE FROM episodic_memory WHERE session_id = %s", (session,))
    memory.save_episode(
        session, "Who won the 1986 World Cup?", "Argentina, led by Maradona."
    )
    memory.save_episode(
        session, "What's the offside rule?", "A player is offside if..."
    )
    hits = memory.recall_episodes(session, "tell me about Maradona's World Cup", k=1)
    assert "Maradona" in hits[0]["agent_response"]
