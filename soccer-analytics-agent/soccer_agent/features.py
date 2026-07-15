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
        "home_form_5",
        "home_form_10",
        "home_form_20",
        "away_form_5",
        "away_form_10",
        "away_form_20",
        "form_diff_5",
        "form_diff_10",
    ],
    "GOALS": [
        "home_gs_avg_10",
        "home_gc_avg_10",
        "away_gs_avg_10",
        "away_gc_avg_10",
        "home_gd_avg_10",
        "away_gd_avg_10",
        "gd_differential",
    ],
    "H2H": ["h2h_matches", "h2h_home_win_rate", "h2h_goal_diff"],
    "TOURNAMENT": [
        "is_neutral",
        "is_world_cup",
        "is_continental",
        "is_friendly",
        "is_qualifier",
        "tournament_importance",
    ],
    "REST": ["home_days_rest", "away_days_rest", "rest_diff"],
    "MOMENTUM": [
        "home_streak",
        "away_streak",
        "home_unbeaten",
        "away_unbeaten",
        "home_clean_sheet_pct",
        "away_clean_sheet_pct",
        "home_draw_tendency",
        "away_draw_tendency",
        "draw_tendency_sum",
    ],
    "POISSON": ["home_lambda", "away_lambda", "home_poisson_win", "home_poisson_draw"],
    "GOALSCORER": [
        "home_scoring_depth",
        "away_scoring_depth",
        "home_penalty_ratio",
        "away_penalty_ratio",
        "home_late_goal_ratio",
        "away_late_goal_ratio",
    ],
}

FEATURE_COLUMNS: list[str] = [f for names in FEATURE_FAMILIES.values() for f in names]


@dataclass
class TeamHistory:
    """Rolling pre-match state for one team, updated chronologically."""

    results: list[float] = field(default_factory=list)  # 1 win / 0.5 draw / 0 loss
    scored: list[int] = field(default_factory=list)
    conceded: list[int] = field(default_factory=list)
    scorers: list[int] = field(default_factory=list)  # distinct scorers/match
    penalty_goals: list[int] = field(default_factory=list)
    late_goals: list[int] = field(default_factory=list)
    total_goals: list[int] = field(default_factory=list)
    last_date: date | None = None

    def add_match(
        self,
        is_win: bool,
        is_draw: bool,
        gs: int,
        gc: int,
        match_date: date,
        n_scorers: int,
        n_penalty_goals: int,
        n_late_goals: int,
        n_goals: int,
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
        "form_diff_5": _avg(_last(home_state.results, 5))
        - _avg(_last(away_state.results, 5)),
        "form_diff_10": _avg(_last(home_state.results, 10))
        - _avg(_last(away_state.results, 10)),
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
