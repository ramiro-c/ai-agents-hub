# Soccer Analytics Agent — Phase 7 Design: XGBoost Match Predictor

> **Design doc (spec-level).** Supersedes the design assumptions in the older
> `docs/superpowers/plans/2026-07-12-soccer-agent-phase-7.md`, which was drafted
> before we inspected the original Oracle workshop. The implementation plan will be
> regenerated from this document.

## Goal

Replace the Elo heuristic in `predict_match` (Phase 4, ~55% accuracy) with a
gradient-boosted tree model trained on engineered features from ~49k international
matches. The LLM stays stock — the domain intelligence lives in a specialist model
exposed as a tool.

**Primary deliverable is understanding, not leaderboard accuracy.** We replicate
the *logic* of the Oracle workshop, with a deliberately narrower scope.

## What the original Oracle workshop actually does (verified)

Read from `oracle-ai-developer-hub/workshops/soccer-analytics-agent/enhanced_features.py`:

1. **3-class target.** `result ∈ {Win, Draw, Loss}` from the home team's
   perspective (`get_result`, lines 44-48). `XGBClassifier` multiclass,
   `eval_metric='mlogloss'`, output via `predict_proba` → three probabilities that
   sum to 1. **No binary classifier, no hand-tuned draw constant.**
2. **Named feature families + ablation study.** ~40 "original" features (Elo, form,
   goals, H2H, rest, tournament) plus new families: goalscorer intelligence,
   momentum/psychology, Poisson expected goals, venue/geography, tournament
   context. `run_experiments()` trains each family separately and compares accuracy
   to show which family actually adds signal.
3. **Fixed hyperparameters, XGBoost vs LightGBM comparison. No Optuna.**
4. **Time-based split:** train `year < 2020`, test `year >= 2020`, filtered to
   `year >= 1990`. A random split is also run for comparison.
5. **Precomputed serving:** trains offline → dumps `predictions.parquet`
   (`home_team, away_team, prob_home_win, prob_draw, prob_away_win, model_version`)
   → bulk-loads into a table → the agent tool does a **lookup**, it does not run the
   model in-process.

## Decisions for our replication

| Dimension | Oracle | Ours | Rationale |
|---|---|---|---|
| Target | 3-class multiclass | **3-class multiclass** | Matches Oracle; correct probabilities without a hacky draw derivation. |
| Serving | Precompute + lookup | **Live inference** | Our agent is interactive and can be asked *any* matchup; a curated precomputed set can't cover that. Deliberate divergence. |
| Features | ~84 across families | **~70-75 across families, minus venue/altitude** | We keep every family our data supports; we drop altitude (no data). No generic "interaction terms." |
| Hyperparameters | Fixed + XGB vs LGBM | **Fixed + XGB vs LGBM** | Matches Oracle. |
| Optuna | none | **none** | Learning-first: 100 trials × CV is ceremony that costs 30-60 min and teaches little. Optional light demo can come later. |
| Ablation study | yes | **yes** | Best teaching artifact of the phase; shows which family earns its place. |
| Anti-leakage | online Elo + chrono split | **online Elo + chrono split** | Features at time *t* use only pre-match info. |

### Data reality (our schema, `db/schema.sql`)

- `matches(match_date, home_team, away_team, home_score, away_score, tournament, city, country, neutral)`
- `goalscorers(match_date, home_team, away_team, team, scorer, minute, own_goal, penalty)` — **`minute` and `penalty` present**, so goalscorer-intelligence features are computable.
- `shootouts(match_date, home_team, away_team, winner, first_shooter)`
- `team_elo` — materialized Elo for 336 teams.
- **Not present:** stadium altitude / geo-coordinates → the venue/altitude family is out of scope for v1.

### Feature families (v1)

| Family | Included | Source |
|---|---|---|
| Elo (home/away/diff/total, tournament-weighted, expected) | ✅ | `team_elo` + online Elo |
| Recent form (5/10/20, weighted) | ✅ | `matches` |
| Goals (scored/conceded avg, goal diff) | ✅ | `matches` |
| Head-to-head (win rate, count, goal diff) | ✅ | `matches` |
| Tournament context (WC / continental / friendly / qualifier / neutral) | ✅ | `tournament`, `neutral` |
| Rest & scheduling (days rest, rest diff) | ✅ | `match_date` |
| Goalscorer intelligence (scoring depth, star dependency, penalty ratio, late-goal ratio, first-half ratio) | ✅ | `goalscorers` (`minute`, `penalty`) |
| Momentum/psychology (streaks, unbeaten, clean-sheet %, comeback rate, draw tendency, blowout/shutout %) | ✅ | `matches` |
| Poisson expected goals (lambdas, poisson win/draw, scoring variance, over-performance) | ✅ | goals |
| Venue/altitude | ❌ | no data |

Final feature list (~70-75) is finalized during implementation; the ablation study
prunes families that don't add signal.

## Architecture

Three new modules, mirroring the existing framework-free style:

```
scripts/train_xgboost.py   train + evaluate + ablation + serialize (one-shot, offline)
        |  reuses
soccer_agent/features.py   pure feature computation: compute_features(match, elos, caches) -> dict
        |  loaded by
soccer_agent/predictor.py  load model once (cached), predict_match_xgb(home, away) -> 3-class probs
        |  called by
soccer_agent/tools.py      predict_match v2: XGBoost first, Elo fallback; predict_match_elo kept
```

- **`features.py`** — pure functions, no DB import, so unit tests run offline with
  injected data. Same code path is used by training (batch) and serving (single
  matchup), so there is one definition of a feature and no train/serve skew.
- **`train_xgboost.py`** — loads matches in chronological order, computes features
  with online Elo updates (no lookahead), chrono split, trains multiclass XGBoost,
  runs the family ablation, compares XGBoost vs LightGBM, prints top-20 importance,
  serializes the model + the feature-column order + the label encoding.
- **`predictor.py`** — loads the model once (module-level cache), computes features
  for the requested matchup via `features.py`, returns
  `{home_win, draw, away_win}` probabilities. Returns a structured `error` if the
  model file is absent (never raises).
- **`tools.py`** — `predict_match` tries `predict_match_xgb`; on any error or a
  missing model it falls back to the Phase 4 Elo logic (kept as
  `predict_match_elo`). The tool declaration is unchanged, so Gemini sees the same
  contract — the model swap is transparent.

## Data flow

**Training (offline, one-shot):**
matches (chrono) → per match: `compute_features()` using pre-match Elo/form/caches
→ append row + `result` label → update online Elo → chrono split → fit multiclass
XGBoost → ablation + XGB/LGBM comparison → serialize model + feature order + labels
to `data/`.

**Serving (live, per request):**
`predict_match(home, away)` → `predictor.predict_match_xgb` → `compute_features()`
for this matchup (current Elo + recent form/H2H from DB) → `model.predict_proba` →
normalized `{home_win, draw, away_win}` + brief note. On failure → Elo fallback.

## Error handling

- `predict_match` and `predict_match_xgb` never raise; they return `{"error": ...}`
  so the agent loop can self-correct (project invariant — `dispatch()` never raises).
- Missing model file → structured error → Elo fallback in the tool.
- Unknown team → structured error naming the missing team(s), same as Phase 4.
- NULL scores: training excludes rows with NULL `home_score`/`away_score`
  (documented gotcha from Phase 4).

## Testing (behavior-first, per project convention)

Unit (offline, injected data):
- `test_compute_features_is_deterministic` — same input → same output.
- `test_compute_features_no_lookahead` — features for a match use only pre-match data.
- `test_elo_features_reflect_ratings`, `test_form_features_count_correctly`,
  `test_h2h_features_zero_when_no_history`, `test_goalscorer_features_use_minute_and_penalty`.

Predictor / tool:
- `test_predict_probabilities_sum_to_one`.
- `test_predict_match_falls_back_to_elo_when_no_model`.
- `test_predict_match_handles_unknown_team`.
- `test_predict_match_tool_contract_unchanged` — same keys the Phase 4 tool returned
  that the frontend `ProbabilityBar` consumes.

Integration (`@pytest.mark.integration`, skip cleanly when DB down): a real
end-to-end prediction for a known matchup returns three probabilities summing to ~1.

## Out of scope (v1)

- Optuna hyperparameter search (optional light demo later).
- Venue/altitude feature family (no data).
- Generic interaction/composite feature terms.
- Precomputed prediction table (we serve live).
- Multi-output regression on exact scorelines (Poisson stays a *feature*, not the target).

## Success criteria

1. `predict_match` returns calibrated 3-class probabilities from the trained model,
   with an Elo fallback that keeps the tool working before/without training.
2. Test-set accuracy beats the Phase 4 Elo baseline (~55%); report the exact number.
3. The ablation study prints per-family accuracy so we can see which families earn
   their place.
4. Feature computation is deterministic and leakage-free (asserted by tests).
5. The frontend `ProbabilityBar` renders v2 output with no changes (tool contract
   preserved).
