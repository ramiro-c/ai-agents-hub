import pytest
from soccer_agent.tools import dispatch, sql_query, validate_sql

from tests.test_db import requires_db


def test_validate_accepts_select():
    assert validate_sql("SELECT 1") == "SELECT 1"


def test_validate_accepts_with_cte():
    assert validate_sql("WITH x AS (SELECT 1) SELECT * FROM x").startswith("WITH")


def test_validate_strips_trailing_semicolon():
    assert validate_sql("SELECT 1;") == "SELECT 1"


@pytest.mark.parametrize(
    "bad",
    [
        "DELETE FROM matches",
        "INSERT INTO matches VALUES (1)",
        "DROP TABLE matches",
        "SELECT 1; DELETE FROM matches",
        "UPDATE matches SET home_score = 9",
    ],
)
def test_validate_rejects_writes(bad):
    with pytest.raises(ValueError):
        validate_sql(bad)


@pytest.mark.integration
@requires_db
def test_sql_query_caps_rows():
    result = sql_query("SELECT generate_series(1, 1000)")
    assert len(result["rows"]) == 50


@pytest.mark.integration
@requires_db
def test_sql_query_returns_error_instead_of_raising():
    result = sql_query("SELECT nope FROM nowhere")
    assert "error" in result


def test_dispatch_unknown_tool():
    assert "error" in dispatch("no_such_tool", {})


@pytest.mark.integration
@requires_db
def test_remember_then_recall_via_dispatch():
    from soccer_agent import db

    with db.connect() as conn:
        conn.execute("DELETE FROM semantic_memory")
    assert dispatch("remember", {"fact": "The user is a Boca Juniors fan"}) == {
        "status": "remembered"
    }
    result = dispatch("recall", {"query": "what club does the user follow?"})
    assert any("Boca" in f["fact"] for f in result["facts"])


@pytest.mark.integration
@requires_db
def test_vector_search_returns_results():
    from soccer_agent.tools import vector_search

    result = vector_search("World Cup final Argentina")
    assert "results" in result
    assert len(result["results"]) > 0
    for r in result["results"]:
        assert "content" in r
        assert "score" in r
        assert "teams" in r


@pytest.mark.integration
@requires_db
def test_hybrid_retrieve_returns_fused_results():
    from soccer_agent.tools import hybrid_retrieve

    result = hybrid_retrieve("World Cup final Argentina")
    assert "results" in result
    assert len(result["results"]) > 0
    for r in result["results"]:
        assert "content" in r
        assert "rrf_score" in r
        assert "sources" in r
        assert len(r["sources"]) >= 1


@pytest.mark.integration
@requires_db
def test_vector_search_ranks_seeded_document():
    """Seed known documents and verify retrieval ranks the relevant one."""
    from soccer_agent import db, embeddings
    from soccer_agent.memory import render_vector
    from soccer_agent.tools import vector_search

    # Seed a distinctive document among the 49k existing ones.
    seed = "Quantum unicorns played football against AI robots in a test match."
    vec = render_vector(embeddings.embed(seed))
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO match_documents
               (match_date, home_team, away_team, content, embedding)
               VALUES (%s, %s, %s, %s, %s::vector)""",
            ("2099-01-01", "Unicorns", "Robots", seed, vec),
        )
        conn.commit()

    result = vector_search("quantum unicorns football")
    assert len(result["results"]) > 0
    first_content = result["results"][0]["content"]
    assert "quantum" in first_content.lower()


@pytest.mark.integration
@requires_db
def test_hybrid_retrieve_fuses_vector_and_text():
    """Hybrid should find a document that matches in both dimensions."""
    from soccer_agent import db, embeddings
    from soccer_agent.memory import render_vector
    from soccer_agent.tools import hybrid_retrieve

    content = "Olympique Marsella defeated Intergalactic Milan 3-2."
    vec = render_vector(embeddings.embed(content))
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO match_documents
               (match_date, home_team, away_team, content, embedding)
               VALUES (%s, %s, %s, %s, %s::vector)""",
            ("2099-01-02", "Olympique Marsella", "Intergalactic Milan", content, vec),
        )
        conn.commit()

    result = hybrid_retrieve("Olympique Marsella won")
    assert len(result["results"]) > 0
    # The seeded doc should appear — check via content match
    contents = [r["content"] for r in result["results"]]
    assert any("Olympique Marsella" in c for c in contents)
