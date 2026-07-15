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
        _blank_state(),
        _blank_state(),
        elo_home=1500,
        elo_away=1500,
        neutral=False,
        tournament="Friendly",
        h2h={"matches": 0, "home_win_rate": 0.0, "goal_diff": 0.0},
        match_date=date(2020, 1, 1),
    )
    assert set(feats) == set(FEATURE_COLUMNS)
    assert all(isinstance(v, (int, float)) for v in feats.values())


def test_compute_features_is_deterministic():
    args = dict(
        elo_home=1800,
        elo_away=1500,
        neutral=False,
        tournament="FIFA World Cup",
        h2h={"matches": 3, "home_win_rate": 0.66, "goal_diff": 1.2},
        match_date=date(2021, 6, 1),
    )
    a = compute_features(_blank_state(), _blank_state(), **args)
    b = compute_features(_blank_state(), _blank_state(), **args)
    assert a == b


def test_elo_features_reflect_ratings():
    feats = compute_features(
        _blank_state(),
        _blank_state(),
        elo_home=1900,
        elo_away=1600,
        neutral=False,
        tournament="Friendly",
        h2h={"matches": 0, "home_win_rate": 0.0, "goal_diff": 0.0},
        match_date=date(2020, 1, 1),
    )
    assert feats["elo_home"] == 1900
    assert feats["elo_diff"] == 300
    assert feats["home_expected"] > 0.5  # stronger + home advantage


def test_h2h_features_zero_when_no_history():
    feats = compute_features(
        _blank_state(),
        _blank_state(),
        elo_home=1500,
        elo_away=1500,
        neutral=True,
        tournament="Friendly",
        h2h={"matches": 0, "home_win_rate": 0.0, "goal_diff": 0.0},
        match_date=date(2020, 1, 1),
    )
    assert feats["h2h_matches"] == 0
    assert feats["h2h_home_win_rate"] == 0.0


def test_form_features_count_correctly():
    h = TeamHistory()
    # three wins: gs/gc, no goalscorer detail needed for form
    for _ in range(3):
        h.add_match(
            is_win=True,
            is_draw=False,
            gs=2,
            gc=0,
            match_date=date(2019, 1, 1),
            n_scorers=2,
            n_penalty_goals=0,
            n_late_goals=0,
            n_goals=2,
        )
    feats = compute_features(
        h,
        TeamHistory(),
        elo_home=1500,
        elo_away=1500,
        neutral=False,
        tournament="Friendly",
        h2h={"matches": 0, "home_win_rate": 0.0, "goal_diff": 0.0},
        match_date=date(2019, 2, 1),
    )
    assert feats["home_form_5"] == 1.0  # all wins
    assert feats["home_clean_sheet_pct"] == 1.0  # conceded 0 each


def test_goalscorer_features_use_minute_and_penalty():
    h = TeamHistory()
    # one match: 2 goals, 1 penalty, 1 late (min>=75)
    h.add_match(
        is_win=True,
        is_draw=False,
        gs=2,
        gc=1,
        match_date=date(2019, 1, 1),
        n_scorers=2,
        n_penalty_goals=1,
        n_late_goals=1,
        n_goals=2,
    )
    feats = compute_features(
        h,
        TeamHistory(),
        elo_home=1500,
        elo_away=1500,
        neutral=False,
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
