"""Train the Phase 7 multiclass match predictor. One-shot, offline.

Single chronological pass builds a leakage-free feature matrix (online Elo +
rolling state), then trains multiclass XGBoost, runs a per-family ablation, and
compares against LightGBM. Serializes model + feature order + class labels.

Run: uv run python scripts/train_xgboost.py
"""

from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, log_loss
from sklearn.preprocessing import LabelEncoder
from soccer_agent import db
from soccer_agent.elo import BASE_ELO, HOME_ADVANTAGE, expected_score, k_factor
from soccer_agent.features import (
    FEATURE_COLUMNS,
    FEATURE_FAMILIES,
    TeamHistory,
    compute_features,
)

MODEL_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "xgboost_match_predictor.joblib"
)
MIN_YEAR = 1990
TEST_FROM_YEAR = 2020

XGB_PARAMS = dict(
    objective="multi:softprob",
    num_class=3,
    n_estimators=600,
    max_depth=6,
    learning_rate=0.04,
    subsample=0.85,
    colsample_bytree=0.8,
    min_child_weight=5,
    reg_alpha=0.1,
    reg_lambda=1.5,
    eval_metric="mlogloss",
    n_jobs=4,
    random_state=42,
)


def _load_goalscorer_aggregates(conn) -> dict:
    """Map (match_date, home, away, team) -> (n_scorers, n_penalty, n_late, n_goals)."""
    rows = conn.execute(
        """SELECT match_date, home_team, away_team, team,
                  COUNT(DISTINCT scorer) AS n_scorers,
                  COUNT(*) FILTER (WHERE penalty) AS n_penalty,
                  COUNT(*) FILTER (WHERE minute >= 75) AS n_late,
                  COUNT(*) AS n_goals
           FROM goalscorers
           WHERE own_goal = false
           GROUP BY match_date, home_team, away_team, team"""
    ).fetchall()
    agg = {}
    for md, home, away, team, ns, npn, nl, ng in rows:
        agg[(md, home, away, team)] = (int(ns), int(npn or 0), int(nl or 0), int(ng))
    return agg


def _result(h_score: int, a_score: int) -> str:
    if h_score > a_score:
        return "Win"
    if h_score < a_score:
        return "Loss"
    return "Draw"


def build_matrix():
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT match_date, home_team, away_team, home_score, away_score,
                      tournament, neutral
               FROM matches
               WHERE home_score IS NOT NULL AND away_score IS NOT NULL
               ORDER BY match_date, home_team, away_team"""
        ).fetchall()
        gagg = _load_goalscorer_aggregates(conn)

    elos: dict[str, float] = defaultdict(lambda: BASE_ELO)
    states: dict[str, TeamHistory] = defaultdict(TeamHistory)
    # h2h[(a,b)] accumulates from a's perspective: matches, a_wins, goal_diff_sum
    h2h = defaultdict(lambda: [0, 0.0, 0.0])

    X, y, years = [], [], []

    for md, home, away, hs, ascore, tournament, neutral in rows:
        eh, ea = elos[home], elos[away]

        key = (home, away)
        m, wins, gdsum = h2h[key]
        h2h_feats = {
            "matches": m,
            "home_win_rate": (wins / m) if m else 0.0,
            "goal_diff": (gdsum / m) if m else 0.0,
        }

        feats = compute_features(
            states[home],
            states[away],
            elo_home=eh,
            elo_away=ea,
            neutral=neutral,
            tournament=tournament,
            h2h=h2h_feats,
            match_date=md,
        )
        X.append([feats[c] for c in FEATURE_COLUMNS])
        y.append(_result(hs, ascore))
        years.append(md.year)

        # --- update post-match state (after features are recorded) ---
        eff_home = eh + (0 if neutral else HOME_ADVANTAGE)
        e_home = expected_score(eff_home, ea)
        s_home = 1.0 if hs > ascore else 0.0 if hs < ascore else 0.5
        k = k_factor(tournament)
        elos[home] = eh + k * (s_home - e_home)
        elos[away] = ea + k * ((1.0 - s_home) - (1.0 - e_home))

        gh = gagg.get((md, home, away, home), (0, 0, 0, 0))
        ga = gagg.get((md, home, away, away), (0, 0, 0, 0))
        states[home].add_match(hs > ascore, hs == ascore, hs, ascore, md, *gh)
        states[away].add_match(ascore > hs, hs == ascore, ascore, hs, md, *ga)

        # h2h symmetric update
        h2h[(home, away)] = [m + 1, wins + s_home, gdsum + (hs - ascore)]
        rm, rwins, rgd = h2h[(away, home)]
        h2h[(away, home)] = [rm + 1, rwins + (1.0 - s_home), rgd + (ascore - hs)]

    return np.array(X, dtype=float), np.array(y), np.array(years)


def main() -> None:
    from xgboost import XGBClassifier

    X, y, years = build_matrix()
    mask = years >= MIN_YEAR
    X, y, years = X[mask], y[mask], years[mask]

    train = years < TEST_FROM_YEAR
    test = years >= TEST_FROM_YEAR
    le = LabelEncoder()
    y_enc = le.fit_transform(y)

    print(f"Rows: {len(y):,}  train: {train.sum():,}  test: {test.sum():,}")
    print(f"Classes: {list(le.classes_)}")

    # --- ablation: one family at a time ---
    print("\nAblation (per-family test accuracy):")
    col_index = {c: i for i, c in enumerate(FEATURE_COLUMNS)}
    for fam, names in FEATURE_FAMILIES.items():
        idx = [col_index[n] for n in names]
        clf = XGBClassifier(**XGB_PARAMS)
        clf.fit(X[train][:, idx], y_enc[train], verbose=False)
        pred = clf.predict(X[test][:, idx])
        fam_acc = accuracy_score(y_enc[test], pred)
        print(f"  {fam:<11} ({len(names):>2} feats): {fam_acc:.3f}")

    # --- full model ---
    model = XGBClassifier(**XGB_PARAMS)
    model.fit(X[train], y_enc[train], verbose=False)
    proba = model.predict_proba(X[test])
    pred = proba.argmax(axis=1)
    acc = accuracy_score(y_enc[test], pred)
    ll = log_loss(y_enc[test], proba)
    print(f"\nFull XGBoost — test accuracy: {acc:.3f}  log-loss: {ll:.3f}")

    # --- LightGBM comparison ---
    try:
        from lightgbm import LGBMClassifier

        lgb = LGBMClassifier(
            n_estimators=600,
            max_depth=6,
            learning_rate=0.04,
            subsample=0.85,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.5,
            random_state=42,
            n_jobs=4,
            verbose=-1,
        )
        lgb.fit(X[train], y_enc[train])
        lgb_acc = accuracy_score(y_enc[test], lgb.predict(X[test]))
        print(f"LightGBM   — test accuracy: {lgb_acc:.3f}")
    except Exception as exc:  # noqa: BLE001 - comparison is informational only
        print(f"LightGBM comparison skipped: {exc}")

    # --- top features ---
    importance = sorted(
        zip(FEATURE_COLUMNS, model.feature_importances_),
        key=lambda kv: kv[1],
        reverse=True,
    )
    print("\nTop 15 features:")
    for name, imp in importance[:15]:
        print(f"  {name:<22} {imp:.4f}")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "feature_columns": FEATURE_COLUMNS,
            "classes": list(le.classes_),
        },
        MODEL_PATH,
    )
    print(f"\nSaved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()
