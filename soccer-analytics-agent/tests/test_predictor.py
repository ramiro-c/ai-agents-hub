import pytest

from tests.test_db import requires_db


@pytest.mark.integration
@requires_db
def test_predict_probabilities_sum_to_one():
    from soccer_agent.predictor import predict_match_xgb

    result = predict_match_xgb("Argentina", "Brazil")
    if "error" in result:
        pytest.skip(f"model not trained: {result['error']}")
    probs = result["probabilities"]
    assert abs(sum(probs.values()) - 1.0) < 0.01
    assert set(probs) == {"Argentina_win", "draw", "Brazil_win"}


def test_predict_falls_back_error_when_no_model(tmp_path, monkeypatch):
    import soccer_agent.predictor as predictor

    monkeypatch.setattr(predictor, "MODEL_PATH", tmp_path / "missing.joblib")
    predictor._MODEL = None  # reset cache
    result = predictor.predict_match_xgb("Argentina", "Brazil")
    assert "error" in result


@pytest.mark.integration
@requires_db
def test_predict_handles_unknown_team():
    from soccer_agent.predictor import predict_match_xgb

    result = predict_match_xgb("Atlantis", "Wakanda")
    assert "error" in result
