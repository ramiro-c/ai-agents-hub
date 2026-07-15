# Phase 7 — XGBoost Match Predictor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Supersedes** `docs/superpowers/plans/2026-07-12-soccer-agent-phase-7.md` (drafted before we inspected the Oracle workshop; that file's binary-target + Optuna + precompute assumptions are obsolete).

**Goal:** Replace the Elo heuristic in `predict_match` with a multiclass XGBoost model trained on named feature families from ~49k matches, served by live in-process inference with an Elo fallback.

**Architecture:** Three new modules mirroring the existing framework-free style. `soccer_agent/features.py` holds pure feature functions (no DB import) used by both training and serving, so there is one feature definition and no train/serve skew. `scripts/train_xgboost.py` runs a one-shot offline training pass with online-Elo updates (leakage-free), a per-family ablation study, an XGBoost-vs-LightGBM comparison, and serializes the model + feature order + label map to `data/`. `soccer_agent/predictor.py` loads the model once and predicts a single matchup live. `soccer_agent/tools.py` `predict_match` tries XGBoost first and falls back to the Phase 4 Elo logic (kept as `predict_match_elo`).

**Tech Stack:** `xgboost`, `lightgbm`, `scikit-learn`, `pandas`, `joblib` (added via `uv add`); existing `psycopg`, `numpy`.

## Global Constraints

- Python 3.12+, `uv` only. Never `pip install`. Add deps with `uv add`, run with `uv run ...`. (Copied verbatim from CONTEXT.md conventions.)
- English for all code, comments, docstrings, docs.
- Behavior-first testing, not strict TDD: assert on meaningful outcomes, not "non-empty". Unit tests inject fakes and run offline; integration tests are marked `@pytest.mark.integration` and skip cleanly when the DB is down (`from tests.test_db import requires_db`).
- Tools return structured JSON and **never raise**; errors become `{"error": ...}` so the agent loop can self-correct. `dispatch()` never raises.
- Read-only DB access from tools/serving: SELECT only.
- Exclude rows with NULL `home_score`/`away_score` everywhere (Phase 4 gotcha).
- `data/` is gitignored — the trained model artifact is NOT committed.
- Conventional commits, no AI attribution / no Co-Authored-By. Commit at the end of each task.
- Ruff pre-commit hook runs on commit (E501 max line length 88); let it fix, `git add` again, re-commit.
- Repo root for git is the monorepo `/Users/ramiro/Desktop/personal/ai-agents-hub`; run Python from `soccer-analytics-agent/`.

## Feature families (v1 — concrete list)

Every match becomes one training row from the **home team's perspective**; target
`result ∈ {"Win","Draw","Loss"}`. Features are computed from **pre-match** state only.

| # | Feature | Family | Formula (pre-match) |
|---|---|---|---|
| 1 | `elo_home` | Elo | home Elo before match |
| 2 | `elo_away` | Elo | away Elo before match |
| 3 | `elo_diff` | Elo | `elo_home - elo_away` |
| 4 | `elo_sum` | Elo | `elo_home + elo_away` |
| 5 | `home_expected` | Elo | `expected_score(elo_home + (0 if neutral else 100), elo_away)` |
| 6 | `home_form_5` | Form | avg points (W=1,D=0.5,L=0) over home team's last 5 |
| 7 | `home_form_10` | Form | same, last 10 |
| 8 | `home_form_20` | Form | same, last 20 |
| 9 | `away_form_5` | Form | away team's last 5 |
| 10 | `away_form_10` | Form | away team's last 10 |
| 11 | `away_form_20` | Form | away team's last 20 |
| 12 | `form_diff_5` | Form | `home_form_5 - away_form_5` |
| 13 | `form_diff_10` | Form | `home_form_10 - away_form_10` |
| 14 | `home_gs_avg_10` | Goals | home avg goals scored, last 10 |
| 15 | `home_gc_avg_10` | Goals | home avg goals conceded, last 10 |
| 16 | `away_gs_avg_10` | Goals | away avg goals scored, last 10 |
| 17 | `away_gc_avg_10` | Goals | away avg goals conceded, last 10 |
| 18 | `home_gd_avg_10` | Goals | `home_gs_avg_10 - home_gc_avg_10` |
| 19 | `away_gd_avg_10` | Goals | `away_gs_avg_10 - away_gc_avg_10` |
| 20 | `gd_differential` | Goals | `home_gd_avg_10 - away_gd_avg_10` |
| 21 | `h2h_matches` | H2H | count of prior meetings |
| 22 | `h2h_home_win_rate` | H2H | home wins / h2h_matches (0 if none) |
| 23 | `h2h_goal_diff` | H2H | avg (home_goals - away_goals) in meetings (0 if none) |
| 24 | `is_neutral` | Tournament | 1 if neutral venue |
| 25 | `is_world_cup` | Tournament | 1 if tournament == "FIFA World Cup" |
| 26 | `is_continental` | Tournament | 1 if tournament in continental championships set |
| 27 | `is_friendly` | Tournament | 1 if tournament == "Friendly" |
| 28 | `is_qualifier` | Tournament | 1 if "qualification" in tournament (case-insensitive) |
| 29 | `tournament_importance` | Tournament | 5 WC, 3 continental, 2 qualifier, 1 friendly, 2 otherwise |
| 30 | `home_days_rest` | Rest | days since home team's last match (capped 365, 365 if none) |
| 31 | `away_days_rest` | Rest | days since away team's last match |
| 32 | `rest_diff` | Rest | `home_days_rest - away_days_rest` |
| 33 | `home_streak` | Momentum | consecutive wins into match (0+) |
| 34 | `away_streak` | Momentum | away consecutive wins |
| 35 | `home_unbeaten` | Momentum | consecutive matches without loss |
| 36 | `away_unbeaten` | Momentum | away consecutive unbeaten |
| 37 | `home_clean_sheet_pct` | Momentum | % of last 10 with 0 conceded |
| 38 | `away_clean_sheet_pct` | Momentum | away % of last 10 with 0 conceded |
| 39 | `home_draw_tendency` | Momentum | fraction of last 10 that were draws |
| 40 | `away_draw_tendency` | Momentum | away fraction of last 10 draws |
| 41 | `draw_tendency_sum` | Momentum | `home_draw_tendency + away_draw_tendency` |
| 42 | `home_lambda` | Poisson | home avg goals scored last 10 (attack rate) |
| 43 | `away_lambda` | Poisson | away avg goals scored last 10 |
| 44 | `home_poisson_win` | Poisson | P(home > away) from Poisson(home_lambda),Poisson(away_lambda) |
| 45 | `home_poisson_draw` | Poisson | P(home == away) from same |
| 46 | `home_scoring_depth` | Goalscorer | distinct scorers / matches, home last 10 (from `goalscorers`) |
| 47 | `away_scoring_depth` | Goalscorer | away distinct scorers / matches last 10 |
| 48 | `home_penalty_ratio` | Goalscorer | penalty goals / total goals, home last 10 |
| 49 | `away_penalty_ratio` | Goalscorer | away penalty goals / total goals last 10 |
| 50 | `home_late_goal_ratio` | Goalscorer | goals at minute ≥ 75 / total, home last 10 |
| 51 | `away_late_goal_ratio` | Goalscorer | away late-goal ratio last 10 |

`FEATURE_COLUMNS` is the ordered list of these 51 names. Families for the ablation
study: `ELO`, `FORM`, `GOALS`, `H2H`, `TOURNAMENT`, `REST`, `MOMENTUM`, `POISSON`,
`GOALSCORER` — each a list of the names above. This is a concrete, achievable v1;
the ablation prints per-family accuracy so we can see which earn their place.

**Continental championships set** (for `is_continental`): `{"UEFA Euro",
"Copa América", "AFC Asian Cup", "African Cup of Nations", "CONCACAF Gold Cup",
"Gold Cup", "Oceania Nations Cup"}`.

---

## Task 1: Dependencies + package skeleton

**Files:**
- Modify: `pyproject.toml` (dependencies)
- Create: `data/.gitkeep` (ensure the gitignored dir exists locally; not committed)

- [ ] **Step 1: Add ML dependencies**

Run:
```bash
cd /Users/ramiro/Desktop/personal/ai-agents-hub/soccer-analytics-agent
uv add xgboost lightgbm scikit-learn pandas joblib
```
Expected: `pyproject.toml` gains the five packages under `dependencies`; `uv.lock` updates.

- [ ] **Step 2: Verify imports resolve**

Run:
```bash
uv run python -c "import xgboost, lightgbm, sklearn, pandas, joblib; print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 3: Create the local model directory**

Run:
```bash
mkdir -p data && touch data/.gitkeep
```
(`data/` is gitignored; this only guarantees the path exists for training output.)

- [ ] **Step 4: Commit**

```bash
cd /Users/ramiro/Desktop/personal/ai-agents-hub
git add soccer-analytics-agent/pyproject.toml soccer-analytics-agent/uv.lock
git commit -m "chore(soccer-agent): add ML deps for Phase 7 (xgboost, lightgbm, sklearn)"
```

---

## Task 2: Feature computation module

**Files:**
- Create: `soccer_agent/features.py`
- Test: `tests/test_features.py`

**Interfaces:**
- Produces:
  - `FEATURE_COLUMNS: list[str]` — the 51 ordered feature names.
  - `FEATURE_FAMILIES: dict[str, list[str]]` — family name → feature names.
  - `CONTINENTAL: set[str]` — continental championship tournament names.
  - `TeamHistory` — a lightweight per-team rolling-state accumulator with:
    - `results: list[float]` (1/0.5/0 W/D/L, most recent last)
    - `scored: list[int]`, `conceded: list[int]`
    - `last_date: date | None`
    - `scorers/penalties/late/goals` rolling counters per match (lists aligned to matches)
    - `add_match(is_win, is_draw, gs, gc, match_date, n_scorers, n_penalty_goals, n_late_goals, n_goals) -> None`
  - `compute_features(home_state, away_state, elo_home, elo_away, neutral, tournament, h2h, match_date) -> dict[str, float]` — returns one dict keyed by `FEATURE_COLUMNS`; pure, no DB.
  - `poisson_win_draw(lam_home: float, lam_away: float) -> tuple[float, float]` — `(P(home>away), P(home==away))` over goal grids 0..10.
- Consumes: `soccer_agent.elo.expected_score`, `HOME_ADVANTAGE`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_features.py
import math
from datetime import date

from soccer_agent.features import (
    FEATURE_COLUMNS,
    FEATURE_FAMILIES,
    TeamHistory,
    compute_features,
    poisson_win_draw,
)


def _blank_state():
    return TeamHistory()


def test_feature_columns_are_unique_and_families_cover_them():
    assert len(FEATURE_COLUMNS) == len(set(FEATURE_COLUMNS))
    covered = {f for names in FEATURE_FAMILIES.values() for f in names}
    assert covered == set(FEATURE_COLUMNS)


def test_compute_features_returns_all_columns():
    feats = compute_features(
        _blank_state(), _blank_state(),
        elo_home=1500, elo_away=1500, neutral=False,
        tournament="Friendly", h2h={"matches": 0, "home_win_rate": 0.0, "goal_diff": 0.0},
        match_date=date(2020, 1, 1),
    )
    assert set(feats) == set(FEATURE_COLUMNS)
    assert all(isinstance(v, (int, float)) for v in feats.values())


def test_compute_features_is_deterministic():
    args = dict(
        elo_home=1800, elo_away=1500, neutral=False, tournament="FIFA World Cup",
        h2h={"matches": 3, "home_win_rate": 0.66, "goal_diff": 1.2},
        match_date=date(2021, 6, 1),
    )
    a = compute_features(_blank_state(), _blank_state(), **args)
    b = compute_features(_blank_state(), _blank_state(), **args)
    assert a == b


def test_elo_features_reflect_ratings():
    feats = compute_features(
        _blank_state(), _blank_state(),
        elo_home=1900, elo_away=1600, neutral=False, tournament="Friendly",
        h2h={"matches": 0, "home_win_rate": 0.0, "goal_diff": 0.0},
        match_date=date(2020, 1, 1),
    )
    assert feats["elo_home"] == 1900
    assert feats["elo_diff"] == 300
    assert feats["home_expected"] > 0.5  # stronger + home advantage


def test_h2h_features_zero_when_no_history():
    feats = compute_features(
        _blank_state(), _blank_state(),
        elo_home=1500, elo_away=1500, neutral=True, tournament="Friendly",
        h2h={"matches": 0, "home_win_rate": 0.0, "goal_diff": 0.0},
        match_date=date(2020, 1, 1),
    )
    assert feats["h2h_matches"] == 0
    assert feats["h2h_home_win_rate"] == 0.0


def test_form_features_count_correctly():
    h = TeamHistory()
    # three wins: gs/gc, no goalscorer detail needed for form
    for _ in range(3):
        h.add_match(is_win=True, is_draw=False, gs=2, gc=0,
                    match_date=date(2019, 1, 1), n_scorers=2, n_penalty_goals=0,
                    n_late_goals=0, n_goals=2)
    feats = compute_features(
        h, TeamHistory(), elo_home=1500, elo_away=1500, neutral=False,
        tournament="Friendly",
        h2h={"matches": 0, "home_win_rate": 0.0, "goal_diff": 0.0},
        match_date=date(2019, 2, 1),
    )
    assert feats["home_form_5"] == 1.0  # all wins
    assert feats["home_clean_sheet_pct"] == 1.0  # conceded 0 each


def test_goalscorer_features_use_minute_and_penalty():
    h = TeamHistory()
    # one match: 2 goals, 1 penalty, 1 late (min>=75)
    h.add_match(is_win=True, is_draw=False, gs=2, gc=1,
                match_date=date(2019, 1, 1), n_scorers=2, n_penalty_goals=1,
                n_late_goals=1, n_goals=2)
    feats = compute_features(
        h, TeamHistory(), elo_home=1500, elo_away=1500, neutral=False,
        tournament="Friendly",
        h2h={"matches": 0, "home_win_rate": 0.0, "goal_diff": 0.0},
        match_date=date(2019, 2, 1),
    )
    assert feats["home_penalty_ratio"] == 0.5
    assert feats["home_late_goal_ratio"] == 0.5


def test_poisson_win_draw_sums_below_one_and_favors_stronger():
    p_win, p_draw = poisson_win_draw(2.0, 0.5)
    assert 0 <= p_draw <= 1
    assert p_win > 0.5
    assert p_win + p_draw <= 1.0 + 1e-9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_features.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'soccer_agent.features'`.

- [ ] **Step 3: Implement `soccer_agent/features.py`**

```python
"""Pure feature computation for the Phase 7 XGBoost predictor.

No DB imports — training (batch) and serving (single matchup) both call
`compute_features`, so there is exactly one definition of every feature and no
train/serve skew. All features use pre-match state only (no lookahead).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from soccer_agent.elo import HOME_ADVANTAGE, expected_score

CONTINENTAL = {
    "UEFA Euro",
    "Copa América",
    "AFC Asian Cup",
    "African Cup of Nations",
    "CONCACAF Gold Cup",
    "Gold Cup",
    "Oceania Nations Cup",
}

FEATURE_FAMILIES: dict[str, list[str]] = {
    "ELO": ["elo_home", "elo_away", "elo_diff", "elo_sum", "home_expected"],
    "FORM": [
        "home_form_5", "home_form_10", "home_form_20",
        "away_form_5", "away_form_10", "away_form_20",
        "form_diff_5", "form_diff_10",
    ],
    "GOALS": [
        "home_gs_avg_10", "home_gc_avg_10", "away_gs_avg_10", "away_gc_avg_10",
        "home_gd_avg_10", "away_gd_avg_10", "gd_differential",
    ],
    "H2H": ["h2h_matches", "h2h_home_win_rate", "h2h_goal_diff"],
    "TOURNAMENT": [
        "is_neutral", "is_world_cup", "is_continental", "is_friendly",
        "is_qualifier", "tournament_importance",
    ],
    "REST": ["home_days_rest", "away_days_rest", "rest_diff"],
    "MOMENTUM": [
        "home_streak", "away_streak", "home_unbeaten", "away_unbeaten",
        "home_clean_sheet_pct", "away_clean_sheet_pct",
        "home_draw_tendency", "away_draw_tendency", "draw_tendency_sum",
    ],
    "POISSON": ["home_lambda", "away_lambda", "home_poisson_win", "home_poisson_draw"],
    "GOALSCORER": [
        "home_scoring_depth", "away_scoring_depth",
        "home_penalty_ratio", "away_penalty_ratio",
        "home_late_goal_ratio", "away_late_goal_ratio",
    ],
}

FEATURE_COLUMNS: list[str] = [f for names in FEATURE_FAMILIES.values() for f in names]


@dataclass
class TeamHistory:
    """Rolling pre-match state for one team, updated chronologically."""

    results: list[float] = field(default_factory=list)  # 1 win / 0.5 draw / 0 loss
    scored: list[int] = field(default_factory=list)
    conceded: list[int] = field(default_factory=list)
    scorers: list[int] = field(default_factory=list)          # distinct scorers/match
    penalty_goals: list[int] = field(default_factory=list)
    late_goals: list[int] = field(default_factory=list)
    total_goals: list[int] = field(default_factory=list)
    last_date: date | None = None

    def add_match(
        self, is_win: bool, is_draw: bool, gs: int, gc: int, match_date: date,
        n_scorers: int, n_penalty_goals: int, n_late_goals: int, n_goals: int,
    ) -> None:
        self.results.append(1.0 if is_win else 0.5 if is_draw else 0.0)
        self.scored.append(gs)
        self.conceded.append(gc)
        self.scorers.append(n_scorers)
        self.penalty_goals.append(n_penalty_goals)
        self.late_goals.append(n_late_goals)
        self.total_goals.append(n_goals)
        self.last_date = match_date


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _last(xs: list, n: int) -> list:
    return xs[-n:] if xs else []


def _streak(results: list[float], predicate) -> int:
    count = 0
    for r in reversed(results):
        if predicate(r):
            count += 1
        else:
            break
    return count


def poisson_win_draw(lam_home: float, lam_away: float) -> tuple[float, float]:
    """P(home > away), P(home == away) over Poisson goal grids 0..10."""
    lam_home = max(lam_home, 1e-6)
    lam_away = max(lam_away, 1e-6)

    def pmf(lam: float, k: int) -> float:
        return math.exp(-lam) * lam**k / math.factorial(k)

    ph = [pmf(lam_home, k) for k in range(11)]
    pa = [pmf(lam_away, k) for k in range(11)]
    p_win = sum(ph[i] * pa[j] for i in range(11) for j in range(i))
    p_draw = sum(ph[k] * pa[k] for k in range(11))
    return p_win, p_draw


def _days_rest(state: TeamHistory, match_date: date) -> float:
    if state.last_date is None:
        return 365.0
    return float(min((match_date - state.last_date).days, 365))


def _clean_sheet_pct(conceded: list[int]) -> float:
    last = _last(conceded, 10)
    return sum(1 for c in last if c == 0) / len(last) if last else 0.0


def _draw_tendency(results: list[float]) -> float:
    last = _last(results, 10)
    return sum(1 for r in last if r == 0.5) / len(last) if last else 0.0


def _ratio(nums: list[int], dens: list[int]) -> float:
    total_num = sum(_last(nums, 10))
    total_den = sum(_last(dens, 10))
    return total_num / total_den if total_den else 0.0


def compute_features(
    home_state: TeamHistory,
    away_state: TeamHistory,
    *,
    elo_home: float,
    elo_away: float,
    neutral: bool,
    tournament: str | None,
    h2h: dict,
    match_date: date,
) -> dict[str, float]:
    """Compute all FEATURE_COLUMNS for one matchup from pre-match state."""
    t = (tournament or "").strip()
    t_lower = t.lower()

    home_gs10 = _avg(_last(home_state.scored, 10))
    home_gc10 = _avg(_last(home_state.conceded, 10))
    away_gs10 = _avg(_last(away_state.scored, 10))
    away_gc10 = _avg(_last(away_state.conceded, 10))

    p_win, p_draw = poisson_win_draw(home_gs10, away_gs10)

    is_world_cup = 1.0 if t == "FIFA World Cup" else 0.0
    is_continental = 1.0 if t in CONTINENTAL else 0.0
    is_friendly = 1.0 if t == "Friendly" else 0.0
    is_qualifier = 1.0 if "qualification" in t_lower or "qualifier" in t_lower else 0.0
    if is_world_cup:
        importance = 5.0
    elif is_continental:
        importance = 3.0
    elif is_qualifier:
        importance = 2.0
    elif is_friendly:
        importance = 1.0
    else:
        importance = 2.0

    home_rest = _days_rest(home_state, match_date)
    away_rest = _days_rest(away_state, match_date)

    home_dt = _draw_tendency(home_state.results)
    away_dt = _draw_tendency(away_state.results)

    return {
        # ELO
        "elo_home": float(elo_home),
        "elo_away": float(elo_away),
        "elo_diff": float(elo_home - elo_away),
        "elo_sum": float(elo_home + elo_away),
        "home_expected": expected_score(
            elo_home + (0 if neutral else HOME_ADVANTAGE), elo_away
        ),
        # FORM
        "home_form_5": _avg(_last(home_state.results, 5)),
        "home_form_10": _avg(_last(home_state.results, 10)),
        "home_form_20": _avg(_last(home_state.results, 20)),
        "away_form_5": _avg(_last(away_state.results, 5)),
        "away_form_10": _avg(_last(away_state.results, 10)),
        "away_form_20": _avg(_last(away_state.results, 20)),
        "form_diff_5": _avg(_last(home_state.results, 5)) - _avg(_last(away_state.results, 5)),
        "form_diff_10": _avg(_last(home_state.results, 10)) - _avg(_last(away_state.results, 10)),
        # GOALS
        "home_gs_avg_10": home_gs10,
        "home_gc_avg_10": home_gc10,
        "away_gs_avg_10": away_gs10,
        "away_gc_avg_10": away_gc10,
        "home_gd_avg_10": home_gs10 - home_gc10,
        "away_gd_avg_10": away_gs10 - away_gc10,
        "gd_differential": (home_gs10 - home_gc10) - (away_gs10 - away_gc10),
        # H2H
        "h2h_matches": float(h2h.get("matches", 0)),
        "h2h_home_win_rate": float(h2h.get("home_win_rate", 0.0)),
        "h2h_goal_diff": float(h2h.get("goal_diff", 0.0)),
        # TOURNAMENT
        "is_neutral": 1.0 if neutral else 0.0,
        "is_world_cup": is_world_cup,
        "is_continental": is_continental,
        "is_friendly": is_friendly,
        "is_qualifier": is_qualifier,
        "tournament_importance": importance,
        # REST
        "home_days_rest": home_rest,
        "away_days_rest": away_rest,
        "rest_diff": home_rest - away_rest,
        # MOMENTUM
        "home_streak": float(_streak(home_state.results, lambda r: r == 1.0)),
        "away_streak": float(_streak(away_state.results, lambda r: r == 1.0)),
        "home_unbeaten": float(_streak(home_state.results, lambda r: r >= 0.5)),
        "away_unbeaten": float(_streak(away_state.results, lambda r: r >= 0.5)),
        "home_clean_sheet_pct": _clean_sheet_pct(home_state.conceded),
        "away_clean_sheet_pct": _clean_sheet_pct(away_state.conceded),
        "home_draw_tendency": home_dt,
        "away_draw_tendency": away_dt,
        "draw_tendency_sum": home_dt + away_dt,
        # POISSON
        "home_lambda": home_gs10,
        "away_lambda": away_gs10,
        "home_poisson_win": p_win,
        "home_poisson_draw": p_draw,
        # GOALSCORER
        "home_scoring_depth": _avg(_last(home_state.scorers, 10)),
        "away_scoring_depth": _avg(_last(away_state.scorers, 10)),
        "home_penalty_ratio": _ratio(home_state.penalty_goals, home_state.total_goals),
        "away_penalty_ratio": _ratio(away_state.penalty_goals, away_state.total_goals),
        "home_late_goal_ratio": _ratio(home_state.late_goals, home_state.total_goals),
        "away_late_goal_ratio": _ratio(away_state.late_goals, away_state.total_goals),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_features.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/ramiro/Desktop/personal/ai-agents-hub
git add soccer-analytics-agent/soccer_agent/features.py soccer-analytics-agent/tests/test_features.py
git commit -m "feat(soccer-agent): pure feature module for XGBoost predictor (Phase 7)"
```

---

## Task 3: Training pipeline

**Files:**
- Create: `scripts/train_xgboost.py`
- (Output, gitignored: `data/xgboost_match_predictor.joblib`)

**Interfaces:**
- Consumes: `soccer_agent.features` (`FEATURE_COLUMNS`, `FEATURE_FAMILIES`, `TeamHistory`, `compute_features`), `soccer_agent.elo` (`BASE_ELO`, `HOME_ADVANTAGE`, `expected_score`, `k_factor`), `soccer_agent.db`.
- Produces: a serialized dict at `data/xgboost_match_predictor.joblib`:
  `{"model": XGBClassifier, "feature_columns": list[str], "classes": list[str]}`
  where `classes` is the `LabelEncoder`-decoded order aligned to `predict_proba` columns.

The script does a single chronological pass (like `compute_elos.py`), building the
feature matrix with **online** Elo, form, H2H, and goalscorer state — every row uses
only matches strictly before it. Goalscorer aggregates per match are pulled once and
joined by `(match_date, home_team, away_team)`.

- [ ] **Step 1: Implement `scripts/train_xgboost.py`**

```python
"""Train the Phase 7 multiclass match predictor. One-shot, offline.

Single chronological pass builds a leakage-free feature matrix (online Elo +
rolling state), then trains multiclass XGBoost, runs a per-family ablation, and
compares against LightGBM. Serializes model + feature order + class labels.

Run: uv run python scripts/train_xgboost.py
"""

from collections import defaultdict
from datetime import date
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

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "xgboost_match_predictor.joblib"
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
            states[home], states[away],
            elo_home=eh, elo_away=ea, neutral=neutral,
            tournament=tournament, h2h=h2h_feats, match_date=md,
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
        print(f"  {fam:<11} ({len(names):>2} feats): {accuracy_score(y_enc[test], pred):.3f}")

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
            n_estimators=600, max_depth=6, learning_rate=0.04,
            subsample=0.85, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.5,
            random_state=42, n_jobs=4, verbose=-1,
        )
        lgb.fit(X[train], y_enc[train])
        lgb_acc = accuracy_score(y_enc[test], lgb.predict(X[test]))
        print(f"LightGBM   — test accuracy: {lgb_acc:.3f}")
    except Exception as exc:  # noqa: BLE001 - comparison is informational only
        print(f"LightGBM comparison skipped: {exc}")

    # --- top features ---
    importance = sorted(
        zip(FEATURE_COLUMNS, model.feature_importances_),
        key=lambda kv: kv[1], reverse=True,
    )
    print("\nTop 15 features:")
    for name, imp in importance[:15]:
        print(f"  {name:<22} {imp:.4f}")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "feature_columns": FEATURE_COLUMNS, "classes": list(le.classes_)},
        MODEL_PATH,
    )
    print(f"\nSaved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run training end-to-end**

Run:
```bash
cd /Users/ramiro/Desktop/personal/ai-agents-hub/soccer-analytics-agent
docker compose up -d           # ensure Postgres on 5433 is up
uv run python scripts/train_xgboost.py
```
Expected: prints row counts, class order `['Draw', 'Loss', 'Win']`, per-family
ablation accuracies, a full-model test accuracy **above ~0.55** (beats the Elo
baseline), a LightGBM line, top-15 features, and `Saved model to .../data/xgboost_match_predictor.joblib`. Runtime: a few minutes.

- [ ] **Step 3: Commit the script** (model artifact is gitignored)

```bash
cd /Users/ramiro/Desktop/personal/ai-agents-hub
git add soccer-analytics-agent/scripts/train_xgboost.py
git commit -m "feat(soccer-agent): XGBoost training pipeline with family ablation (Phase 7)"
```

---

## Task 4: Model serving module

**Files:**
- Create: `soccer_agent/predictor.py`
- Test: `tests/test_predictor.py`

**Interfaces:**
- Consumes: `soccer_agent.features`, `soccer_agent.db`, `soccer_agent.elo`, the artifact from Task 3.
- Produces:
  - `MODEL_PATH: Path`
  - `predict_match_xgb(home_team: str, away_team: str, tournament: str = "Friendly", neutral: bool = False) -> dict` — returns
    `{"model": "xgboost_v1", "features_used": int, "probabilities": {f"{home}_win": p, "draw": p, f"{away}_win": p}, "home_win_probability": p}`
    or `{"error": ...}`. Never raises.
  - `_build_team_state(conn, team: str, before: date) -> TeamHistory` (internal).

The serving path rebuilds each team's rolling state from its recent matches, reads
current Elo from `team_elo`, computes H2H from `matches`, then calls the **same**
`compute_features` used in training, ordered by the saved `feature_columns`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_predictor.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_predictor.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'soccer_agent.predictor'`.

- [ ] **Step 3: Implement `soccer_agent/predictor.py`**

```python
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

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "xgboost_match_predictor.joblib"
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
            return {"error": "Model not trained yet. Run scripts/train_xgboost.py first."}

        with db.connect() as conn:
            r1 = conn.execute("SELECT elo FROM team_elo WHERE team = %s", (home_team,)).fetchone()
            r2 = conn.execute("SELECT elo FROM team_elo WHERE team = %s", (away_team,)).fetchone()
            if r1 is None or r2 is None:
                missing = [t for t, r in [(home_team, r1), (away_team, r2)] if r is None]
                return {"error": f"Unknown team(s): {', '.join(missing)}"}

            today = conn.execute("SELECT max(match_date) FROM matches").fetchone()[0] or date.today()
            home_state = _build_team_state(conn, home_team, today)
            away_state = _build_team_state(conn, away_team, today)
            h2h = _h2h(conn, home_team, away_team)

        feats = compute_features(
            home_state, away_state,
            elo_home=float(r1[0]), elo_away=float(r2[0]),
            neutral=neutral, tournament=tournament, h2h=h2h, match_date=today,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_predictor.py -q`
Expected: PASS (the `no_model` test passes; the two integration tests pass if the
DB is up and the model is trained, otherwise skip cleanly).

- [ ] **Step 5: Commit**

```bash
cd /Users/ramiro/Desktop/personal/ai-agents-hub
git add soccer-analytics-agent/soccer_agent/predictor.py soccer-analytics-agent/tests/test_predictor.py
git commit -m "feat(soccer-agent): live XGBoost serving with Elo state rebuild (Phase 7)"
```

---

## Task 5: Wire `predict_match` — XGBoost first, Elo fallback

**Files:**
- Modify: `soccer_agent/tools.py` (rename Phase 4 `predict_match` → `predict_match_elo`; add new `predict_match`; update the tool description text)
- Test: `tests/test_tools.py` (add contract tests)

**Interfaces:**
- Consumes: `soccer_agent.predictor.predict_match_xgb`.
- Produces: `predict_match(team1, team2) -> dict` (same handler wiring in `_HANDLERS`, unchanged signature) and `predict_match_elo(team1, team2) -> dict` (the exact Phase 4 body).

- [ ] **Step 1: Write the failing contract tests**

```python
# append to tests/test_tools.py
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


@pytest.mark.integration
@requires_db
def test_predict_match_elo_still_available():
    from soccer_agent.tools import predict_match_elo

    result = predict_match_elo("Argentina", "Brazil")
    assert "probabilities" in result
    assert abs(sum(result["probabilities"].values()) - 1.0) < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py -k "predict_match_contract or predict_match_elo_still" -q`
Expected: FAIL — `ImportError: cannot import name 'predict_match_elo'`.

- [ ] **Step 3: Rename the Phase 4 function and add the v2 wrapper**

In `soccer_agent/tools.py`, rename the existing `def predict_match(team1, team2)` (currently at lines 193-248) to `def predict_match_elo(team1, team2)` — keep its body byte-for-byte. Then add directly below it:

```python
def predict_match(team1: str, team2: str) -> dict:
    """Predict match outcome: XGBoost model first, Elo heuristic as fallback.

    team1 is treated as home. Transparent to the model — same contract as v1.
    """
    try:
        from soccer_agent.predictor import predict_match_xgb

        result = predict_match_xgb(team1, team2)
        if "error" not in result:
            return result
    except Exception:  # noqa: BLE001 - never let serving break the tool
        pass
    return predict_match_elo(team1, team2)
```

- [ ] **Step 4: Update the `predict_match` tool description**

In `TOOL_DECLARATIONS` (lines ~500-506), replace the description text with:

```python
        "description": (
            "Use this tool when the user asks who will win or wants outcome "
            "probabilities between two teams. Returns win/draw/loss probabilities "
            "from a trained model (Elo-based fallback if unavailable). "
            "Treats team1 as home."
        ),
```

Leave the `parameters` block and the `_HANDLERS["predict_match"]` entry unchanged.

- [ ] **Step 5: Run the contract tests**

Run: `uv run pytest tests/test_tools.py -k "predict_match" -q`
Expected: PASS (including the existing `test_predict_match` and `test_predict_match_via_dispatch`).

- [ ] **Step 6: Commit**

```bash
cd /Users/ramiro/Desktop/personal/ai-agents-hub
git add soccer-analytics-agent/soccer_agent/tools.py soccer-analytics-agent/tests/test_tools.py
git commit -m "feat(soccer-agent): predict_match uses XGBoost with Elo fallback (Phase 7)"
```

---

## Task 6: Full verification + docs

**Files:**
- Modify: `CONTEXT.md` (mark Phase 7 done)

- [ ] **Step 1: Run the whole suite**

Run:
```bash
cd /Users/ramiro/Desktop/personal/ai-agents-hub/soccer-analytics-agent
uv run pytest -q
```
Expected: all pass (integration tests skip cleanly if DB down).

- [ ] **Step 2: Live smoke check via the CLI**

Run: `uv run python -m soccer_agent.cli`
Then ask: `Predict Argentina vs France`.
Expected: the answer cites three probabilities; the trace shows `predict_match`
returning `"model": "xgboost_v1"`.

- [ ] **Step 3: Update the roadmap in `CONTEXT.md`**

In the roadmap table (line ~174), change the Phase 7 row status from `⏳ Next` to
`✅ Done`, and change Phase 8's status from `⬜ Planned` to `⏳ Next`. Update the
Phase 7 scope cell to read: `Multiclass XGBoost predictor (51 features, live inference, Elo fallback); ablation study`.

- [ ] **Step 4: Commit**

```bash
cd /Users/ramiro/Desktop/personal/ai-agents-hub
git add soccer-analytics-agent/CONTEXT.md
git commit -m "docs(soccer-agent): mark Phase 7 complete (XGBoost predictor)"
```

---

## Self-review notes

- **Spec coverage:** target 3-class (T3), live inference (T4), named families minus venue (T2 table), ablation study (T3), Elo fallback + `predict_match_elo` kept (T5), no Optuna / no precompute / no interaction terms (absent by construction), deterministic + leakage-free features (T2 tests + online pass in T3), frontend contract preserved (T5 contract test). All covered.
- **Leakage guard:** in `build_matrix` (T3) every feature row is computed *before* the post-match state/Elo/H2H update — the ordering in the loop is the guarantee.
- **Train/serve parity:** both paths call `compute_features` with the same argument shapes; serving orders columns by the saved `feature_columns`, so a future feature reorder can't silently misalign.
- **Class-order safety:** serving maps probabilities by `LabelEncoder` class name (`Win`/`Draw`/`Loss`), never by positional index, so it is robust to XGBoost's internal class ordering.
- **Draw handling:** the draw probability comes directly from the multiclass model — no hand-tuned constant (the key improvement over the obsolete 2026-07-12 plan).
