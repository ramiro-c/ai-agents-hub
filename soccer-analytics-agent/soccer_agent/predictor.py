"""Live, in-process serving for the Phase 7 XGBoost predictor.

Loads the model once (module cache) and predicts a single matchup by rebuilding
each team's rolling state from recent matches and calling the SAME
`compute_features` used in training. Never raises — returns {"error": ...}.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import joblib
import numpy as np

from soccer_agent import db
from soccer_agent.features import TeamHistory, compute_features

MODEL_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "xgboost_match_predictor.joblib"
)
_RECENT = 20  # matches of history to rebuild rolling state

_MODEL: dict | None = None


def _load() -> dict | None:
    global _MODEL
    if _MODEL is None and MODEL_PATH.exists():
        _MODEL = joblib.load(MODEL_PATH)
    return _MODEL


def _goalscorer_row(conn, md, home, away, team) -> tuple[int, int, int, int]:
    row = conn.execute(
        """SELECT COUNT(DISTINCT scorer), COUNT(*) FILTER (WHERE penalty),
                  COUNT(*) FILTER (WHERE minute >= 75), COUNT(*)
           FROM goalscorers
           WHERE match_date = %s AND home_team = %s AND away_team = %s
                 AND team = %s AND own_goal = false""",
        (md, home, away, team),
    ).fetchone()
    if not row:
        return (0, 0, 0, 0)
    return (int(row[0] or 0), int(row[1] or 0), int(row[2] or 0), int(row[3] or 0))


def _build_team_state(conn, team: str, before: date) -> TeamHistory:
    rows = conn.execute(
        """SELECT match_date, home_team, away_team, home_score, away_score
           FROM matches
           WHERE (home_team = %s OR away_team = %s)
                 AND home_score IS NOT NULL AND away_score IS NOT NULL
                 AND match_date < %s
           ORDER BY match_date DESC
           LIMIT %s""",
        (team, team, before, _RECENT),
    ).fetchall()
    state = TeamHistory()
    for md, home, away, hs, ascore in reversed(rows):  # oldest first
        is_home = home == team
        gs, gc = (hs, ascore) if is_home else (ascore, hs)
        g = _goalscorer_row(conn, md, home, away, team)
        state.add_match(gs > gc, gs == gc, gs, gc, md, *g)
    return state


def _h2h(conn, home: str, away: str) -> dict:
    rows = conn.execute(
        """SELECT home_team, home_score, away_score
           FROM matches
           WHERE ((home_team = %s AND away_team = %s)
                  OR (home_team = %s AND away_team = %s))
                 AND home_score IS NOT NULL AND away_score IS NOT NULL""",
        (home, away, away, home),
    ).fetchall()
    if not rows:
        return {"matches": 0, "home_win_rate": 0.0, "goal_diff": 0.0}
    wins = gd = 0.0
    for h_team, hs, ascore in rows:
        home_gs, home_gc = (hs, ascore) if h_team == home else (ascore, hs)
        gd += home_gs - home_gc
        if home_gs > home_gc:
            wins += 1
        elif home_gs == home_gc:
            wins += 0.5
    n = len(rows)
    return {"matches": n, "home_win_rate": wins / n, "goal_diff": gd / n}


def predict_match_xgb(
    home_team: str, away_team: str, tournament: str = "Friendly", neutral: bool = False
) -> dict:
    """Predict a single matchup with the trained model. Never raises."""
    try:
        bundle = _load()
        if bundle is None:
            return {
                "error": "Model not trained yet. Run scripts/train_xgboost.py first."
            }

        with db.connect() as conn:
            r1 = conn.execute(
                "SELECT elo FROM team_elo WHERE team = %s", (home_team,)
            ).fetchone()
            r2 = conn.execute(
                "SELECT elo FROM team_elo WHERE team = %s", (away_team,)
            ).fetchone()
            if r1 is None or r2 is None:
                missing = [
                    t for t, r in [(home_team, r1), (away_team, r2)] if r is None
                ]
                return {"error": f"Unknown team(s): {', '.join(missing)}"}

            today = (
                conn.execute("SELECT max(match_date) FROM matches").fetchone()[0]
                or date.today()
            )
            home_state = _build_team_state(conn, home_team, today)
            away_state = _build_team_state(conn, away_team, today)
            h2h = _h2h(conn, home_team, away_team)

        feats = compute_features(
            home_state,
            away_state,
            elo_home=float(r1[0]),
            elo_away=float(r2[0]),
            neutral=neutral,
            tournament=tournament,
            h2h=h2h,
            match_date=today,
        )
        cols = bundle["feature_columns"]
        model = bundle["model"]
        vec = np.array([[feats[c] for c in cols]], dtype=float)
        proba = model.predict_proba(vec)[0]
        prob_by_class = dict(zip(bundle["classes"], proba))  # keys: Draw/Loss/Win

        return {
            "model": "xgboost_v1",
            "features_used": len(cols),
            "probabilities": {
                f"{home_team}_win": round(float(prob_by_class.get("Win", 0.0)), 4),
                "draw": round(float(prob_by_class.get("Draw", 0.0)), 4),
                f"{away_team}_win": round(float(prob_by_class.get("Loss", 0.0)), 4),
            },
            "home_win_probability": round(float(prob_by_class.get("Win", 0.0)), 4),
        }
    except Exception as exc:  # noqa: BLE001 - tools never raise
        return {"error": str(exc)}
