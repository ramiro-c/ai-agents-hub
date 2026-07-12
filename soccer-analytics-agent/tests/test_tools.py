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
