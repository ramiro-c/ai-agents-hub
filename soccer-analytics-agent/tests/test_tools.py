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


# --- Phase 4: Elo-based analytical tools ---


@pytest.mark.integration
@requires_db
def test_get_team_elo_single():
    from soccer_agent.tools import get_team_elo

    result = get_team_elo("Argentina")
    assert "elos" in result
    assert "Argentina" in result["elos"]
    assert isinstance(result["elos"]["Argentina"]["elo"], float)


@pytest.mark.integration
@requires_db
def test_get_team_elo_two_teams():
    from soccer_agent.tools import get_team_elo

    result = get_team_elo("Argentina,Brazil")
    assert len(result["elos"]) == 2
    assert "Argentina" in result["elos"]
    assert "Brazil" in result["elos"]


@pytest.mark.integration
@requires_db
def test_get_team_elo_unknown():
    from soccer_agent.tools import get_team_elo

    result = get_team_elo("FakeTeam")
    assert result["not_found"] == ["FakeTeam"]


@pytest.mark.integration
@requires_db
def test_get_team_form():
    from soccer_agent.tools import get_team_form

    result = get_team_form("Argentina", 3)
    assert result["team"] == "Argentina"
    assert len(result["form"]) <= 3
    for m in result["form"]:
        assert m["result"] in ("W", "L", "D")
        assert "opponent" in m
        assert "score" in m


@pytest.mark.integration
@requires_db
def test_get_h2h():
    from soccer_agent.tools import get_h2h

    result = get_h2h("Argentina", "Brazil")
    assert "record" in result
    assert result["record"]["draws"] >= 0
    assert result["total"] > 0


@pytest.mark.integration
@requires_db
def test_get_h2h_with_draws_does_not_error():
    """Regression: draws trigger a shootout lookup that must run on a live
    connection, not one already closed by the surrounding `with` block."""
    from soccer_agent.tools import get_h2h

    # Argentina vs Germany has drawn matches in the record, exercising the
    # shootout-resolution branch.
    result = get_h2h("Argentina", "Germany")
    assert "error" not in result, result
    assert result["record"]["draws"] > 0


@pytest.mark.integration
@requires_db
def test_get_team_form_with_draws_does_not_error():
    """Regression: a drawn result triggers the shootout lookup, which must
    run before the DB connection is closed."""
    from soccer_agent.tools import get_team_form

    result = get_team_form("Germany", 20)
    assert "error" not in result, result


@pytest.mark.integration
@requires_db
def test_predict_match():
    from soccer_agent.tools import predict_match

    result = predict_match("Argentina", "France")
    assert "probabilities" in result
    probs = result["probabilities"]
    assert "Argentina_win" in probs
    assert "France_win" in probs
    assert "draw" in probs
    total = sum(probs.values())
    assert abs(total - 1.0) < 0.01
    # "prediction_note" is Elo-specific; predict_match may now serve the
    # XGBoost path instead, which does not include it. Not part of the
    # documented tool contract (only the probabilities keys are).


@pytest.mark.integration
@requires_db
def test_predict_match_via_dispatch():
    from soccer_agent.tools import dispatch

    result = dispatch("predict_match", {"team1": "Argentina", "team2": "Brazil"})
    assert "probabilities" in result


@pytest.mark.integration
@requires_db
def test_predict_match_contract_has_probability_keys():
    from soccer_agent.tools import predict_match

    result = predict_match("Argentina", "France")
    assert "probabilities" in result, result
    probs = result["probabilities"]
    assert "Argentina_win" in probs
    assert "France_win" in probs
    assert "draw" in probs
    assert abs(sum(probs.values()) - 1.0) < 0.01
    # Top-level team1/team2 are part of the contract the frontend ProbabilityBar
    # and analytics panel depend on to build the {team}_win keys. The XGBoost
    # path must include them, not just the Elo fallback (regression guard).
    assert result["team1"] == "Argentina"
    assert result["team2"] == "France"


@pytest.mark.integration
@requires_db
def test_predict_match_elo_still_available():
    from soccer_agent.tools import predict_match_elo

    result = predict_match_elo("Argentina", "Brazil")
    assert "probabilities" in result
    assert abs(sum(result["probabilities"].values()) - 1.0) < 0.01
