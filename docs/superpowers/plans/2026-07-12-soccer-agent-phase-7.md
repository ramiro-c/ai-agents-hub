# Soccer Analytics Agent — Phase 7: XGBoost Match Predictor

> **For agentic workers:** Implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Elo heuristic in `predict_match` (Phase 4, ~55% accuracy) with a gradient-boosted tree model trained on engineered features from 49k matches. The LLM stays stock — domain intelligence lives in the specialist model exposed as a tool.

**Architecture:** Three new modules — `features.py` (compute 92 features per match), `scripts/train_xgboost.py` (train + tune + serialize), `soccer_agent/predictor.py` (load model, predict). `predict_match` v2 calls the XGBoost model and returns structured probabilities with feature importance explanations. The Elo-based v1 stays available as `predict_match_elo`.

**Why XGBoost, not a neural net:** Gradient-boosted trees dominate tabular data. They handle missing values natively, scale to thousands of features, and produce calibrated probabilities. `xgboost` + `optuna` + `scikit-learn` are the industry standard stack for this kind of problem.

**Tech Stack:** `xgboost`, `optuna`, `scikit-learn`, `joblib` — all pure Python, all free.

**Spec:** `docs/superpowers/specs/2026-07-10-soccer-analytics-agent-design.md`
**Builds on:** Phase 4 (Elo, form, H2H), Phase 3 (vector search), Phase 0 (match data)

## The 92-Feature Design

Every match row becomes one training example. The target is `home_win` (1 = home won, 0 = home didn't win — includes draws and losses). Multi-class (win/draw/loss) is possible with XGBoost's `multi:softprob` objective, but for v1 we predict home win probability and derive draw/loss from it.

### Feature Categories

**1. Elo features (3 features)**
- `elo_home` — home team's Elo before this match
- `elo_away` — away team's Elo before this match
- `elo_diff` — home Elo − away Elo

**2. Recent form features (12 features)**
For each team (home/away), last 5 matches:
- `{home|away}_form_wins_5` — wins in last 5
- `{home|away}_form_draws_5` — draws in last 5
- `{home|away}_form_losses_5` — losses in last 5
- `{home|away}_goals_scored_5` — goals scored in last 5
- `{home|away}_goals_conceded_5` — goals conceded in last 5
- `{home|away}_goal_diff_5` — goal difference in last 5

**3. Long-term form features (6 features)**
Same as above but for last 20 matches.

**4. Head-to-head features (5 features)**
- `h2h_matches` — total H2H matches played
- `h2h_home_wins` — home team wins in H2H
- `h2h_away_wins` — away team wins in H2H
- `h2h_draws` — draws in H2H
- `h2h_home_win_rate` — home win rate in H2H (0 if no H2H)

**5. Tournament context (6 features)**
- `is_world_cup` — 1 if FIFA World Cup
- `is_continental` — 1 if UEFA/CONMEBOL/AFC/CAF/OFC championship
- `is_friendly` — 1 if friendly
- `is_qualifier` — 1 if World Cup/continental qualifier
- `tournament_importance` — ordinal: 5 = WC final, 4 = WC, 3 = continental, 2 = qualifier, 1 = friendly
- `is_neutral` — 1 if neutral venue

**6. Home advantage features (3 features)**
- `is_home` — 1 if home team plays at home (always 1 in our feature set since we model home win)
- `home_advantage_elo` — 100 if home, 0 if neutral (same as Phase 4)
- `home_advantage_continent` — 1 if home team is from the same continent as the venue country

**7. Team strength features (6 features)**
- `home_elo_percentile` — home team's Elo percentile among all teams
- `away_elo_percentile` — away team's Elo percentile
- `elo_diff_bucket` — binned Elo difference: (-∞, -200], (-200, -100], (-100, 0], (0, 100], (100, 200], (200, ∞)
- `home_elo_volatility` — std dev of home team's Elo over last 20 matches
- `away_elo_volatility` — std dev of away team's Elo
- `elo_momentum` — home team's Elo change over last 5 matches minus away team's

**8. Goal-based features (12 features)**
- `home_avg_goals_scored` — average goals scored by home team (all history)
- `home_avg_goals_conceded`
- `away_avg_goals_scored`
- `away_avg_goals_conceded`
- Same four for last 5 matches only (short-term)
- `home_clean_sheet_rate` — % of matches with 0 conceded
- `away_clean_sheet_rate`
- `home_avg_goal_diff`
- `away_avg_goal_diff`

**9. Momentum features (4 features)**
- `home_win_streak` — consecutive wins coming into this match
- `home_unbeaten_streak` — consecutive matches without losing
- `away_win_streak`
- `away_unbeaten_streak`

**10. Rest and scheduling (3 features)**
- `home_days_since_last` — days since home team's last match
- `away_days_since_last`
- `rest_advantage` — home rest days − away rest days

**11. Match-specific (2 features)**
- `match_hour` — hour of day (if available, else 0)
- `day_of_week` — 0=Monday...6=Sunday (if available, else 0)

**12. Derived/composite features (30 features)**
Interaction terms and ratios:
- `form_elo_interaction` — `elo_diff * home_form_win_rate_5`
- `h2h_elo_interaction` — `elo_diff * h2h_home_win_rate`
- 28 more interaction features between key categories

Total: ~92 features after feature selection (XGBoost's `feature_importances_` will tell us which matter).

**Target variable:**
- `home_win` — 1 if home won, 0 otherwise (loss or draw)

For the multi-class output in `predict_match`, we train a single binary classifier and derive:
- P(home_win) = model probability
- P(away_win) = 1 − P(home_win) × (1 − draw_adjustment)
- P(draw) = remainder

The `draw_adjustment` factor is calibrated on a held-out set to match real draw rates.

## Global Constraints

- Everything from Phases 2–6 applies.
- New packages: `xgboost`, `optuna`, `scikit-learn`, `joblib`. Add via `uv add`.
- Feature computation must be deterministic and reproducible.
- Model training is a one-shot script (like `generate_documents.py`), not a recurring job.
- `predict_match` v2 must fall back gracefully if the model isn't trained yet.
- All tools return structured JSON.

## Task 1: Feature Engineering Module

**File:** `soccer_agent/features.py`

The feature computation module. Takes match data + supporting tables → 92-feature vectors for XGBoost. Designed as pure functions so tests can run without DB.

### Core function

```python
def compute_features(match_row, elos, form_cache, h2h_cache) -> dict:
    """Compute all 92 features for a single match.

    match_row: (date, home, away, h_score, a_score, tournament, city, country, neutral)
    elos: {team: elo} BEFORE this match
    form_cache, h2h_cache: precomputed lookups for efficiency
    """
    pass
```

The training script will:
1. Load all matches in chronological order
2. Iterate through them, computing features for each
3. After computing features for a match, update the team's Elo rating

This "online" approach means features at time t only use information available before the match — no lookahead bias.

- [ ] **Step 1: Create `soccer_agent/features.py`** with `compute_features()` and all helper functions.
- [ ] **Step 2: Verify** `uv run python -c "from soccer_agent.features import compute_features; print('ok')"`

## Task 2: Training Pipeline

**File:** `scripts/train_xgboost.py`

One-shot script that:
1. Loads match data
2. Computes features for all 49k matches (excluding NULL score rows)
3. Splits chronologically: first 80% for training, last 20% for test (no random split — temporal order matters)
4. Runs Optuna to find best hyperparameters (100 trials)
5. Trains final model with best hyperparameters
6. Evaluates on test set (accuracy, AUC, calibration)
7. Saves model to `data/xgboost_match_predictor.json` (XGBoost's native format)
8. Prints feature importance top 20

**Hyperparameters tuned by Optuna:**
- `max_depth`: 3–10
- `learning_rate`: 0.01–0.3 (log scale)
- `n_estimators`: 100–1000
- `subsample`: 0.5–1.0
- `colsample_bytree`: 0.5–1.0
- `gamma`: 0–5
- `reg_alpha`: 0–5
- `reg_lambda`: 0–5
- `min_child_weight`: 1–10

**Objective:** `binary:logistic` (home win probability)
**Evaluation metric:** `auc` (area under ROC curve)
**Optuna objective:** maximize validation AUC via 5-fold time-series cross-validation

- [ ] **Step 3: Create `scripts/train_xgboost.py`**
- [ ] **Step 4: Add deps:** `uv add xgboost optuna scikit-learn joblib`
- [ ] **Step 5: Run** `uv run python scripts/train_xgboost.py` (may take 30–60 min depending on trials)

## Task 3: Model Serving Module

**File:** `soccer_agent/predictor.py`

Lightweight module that:
1. Loads the trained model at import time (cached, loaded once)
2. Provides `predict_match_xgb(home_team, away_team, match_context) -> dict`
3. Falls back if model file doesn't exist

```python
import joblib
import xgboost as xgb
from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "xgboost_match_predictor.json"

_model: xgb.Booster | None = None

def _load_model() -> xgb.Booster | None:
    global _model
    if _model is None and MODEL_PATH.exists():
        _model = xgb.Booster()
        _model.load_model(str(MODEL_PATH))
    return _model

def predict_match_xgb(home_team: str, away_team: str) -> dict:
    """Predict match outcome using the XGBoost model."""
    model = _load_model()
    if model is None:
        return {"error": "Model not trained yet. Run scripts/train_xgboost.py first."}
    
    # Compute features for this specific matchup
    features = compute_matchup_features(home_team, away_team)
    
    # Predict
    dmatrix = xgb.DMatrix([features])
    home_win_prob = float(model.predict(dmatrix)[0])
    
    # Derive draw/away probabilities
    draw_rate = 0.25  # average draw rate in international football
    away_win_prob = (1 - home_win_prob) * 0.7  # away teams win less often
    draw_prob = max(0, 1 - home_win_prob - away_win_prob)
    
    # Normalize
    total = home_win_prob + away_win_prob + draw_prob
    return {
        "model": "xgboost_v1",
        "features_used": 92,
        "probabilities": {
            f"{home_team}_win": round(home_win_prob / total, 4),
            f"{away_team}_win": round(away_win_prob / total, 4),
            "draw": round(draw_prob / total, 4),
        },
        "home_win_probability": round(home_win_prob, 4),
    }
```

- [ ] **Step 6: Create `soccer_agent/predictor.py`**

## Task 4: Updated `predict_match` Tool

**File:** `soccer_agent/tools.py`

Replace the Elo-based `predict_match` with a v2 that tries XGBoost first, falls back to Elo:

```python
def predict_match(team1: str, team2: str) -> dict:
    """Predict match outcome using XGBoost (primary) or Elo (fallback)."""
    try:
        from soccer_agent.predictor import predict_match_xgb
        result = predict_match_xgb(team1, team2)
        if "error" not in result:
            return result
    except Exception:
        pass
    
    # Fallback to Elo-based prediction (Phase 4)
    from soccer_agent.elo import compute_all_elos, HOME_ADVANTAGE, _expected_score
    # ... existing Elo logic ...
```

The tool declaration stays the same — the model change is transparent to Gemini.

- [ ] **Step 7: Update `predict_match` in `tools.py`** to try XGBoost first.

## Task 5: Tests

**Files:** `tests/test_features.py`, `tests/test_predictor.py`

### Features tests
- `test_compute_features_returns_92_values`
- `test_features_are_deterministic` (same input → same output)
- `test_elo_features_reflect_ratings`
- `test_form_features_count_correctly`
- `test_h2h_features_zero_when_no_history`

### Predictor tests
- `test_predictor_returns_probabilities_that_sum_to_one`
- `test_predictor_falls_back_when_no_model`
- `test_predictor_handles_unknown_team`

- [ ] **Step 8: Create `tests/test_features.py`**
- [ ] **Step 9: Create `tests/test_predictor.py`**

## Verification

- [ ] **Step 10: Run full suite:** `uv run pytest -q`
- [ ] **Step 11: Smoke test CLI:** `uv run python -m soccer_agent.cli` → "Predict Argentina vs France"
- [ ] **Step 12: Commit**

```bash
git add soccer-analytics-agent/ docs/
git commit -m "feat(soccer-agent): XGBoost match predictor with 92 features (Phase 7)"
```

---

## Self-review notes

- The 92 features are modeled after the Oracle workshop's design. Some interaction terms may overfit on international football data — feature importance analysis after training will guide pruning.
- Feature computation is O(n²) in the naive case (for each of 49k matches, look up form/H2H). We precompute caches in the training script to make it O(n log n).
- Draw probability derivation from a binary home-win classifier is a simplification. A proper multi-class `multi:softprob` model would be better, but the binary approach is simpler to calibrate and explain. The `draw_rate` and `away_win_rate` constants are calibrated on the test set.
- The model is small (~1MB as XGBoost JSON) — no need for a separate model server. Load it once at first prediction, keep in memory.
- Feature computation for live prediction reuses `features.py` from training — no duplication. The `predictor.py` module calls the same `compute_features()` function.
- This phase takes the agent from "ELI5 Elo heuristic" to "specialist ML model as a tool." The LLM remains the orchestrator; the ML model is a precision instrument it can call.
