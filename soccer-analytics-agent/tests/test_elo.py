"""Unit tests for Elo rating math."""

import math

from soccer_agent.elo import BASE_ELO, HOME_ADVANTAGE, expected_score, k_factor


def test_expected_score_equal_teams():
    p = expected_score(1500, 1500)
    assert math.isclose(p, 0.5)


def test_expected_score_400_point_gap():
    p = expected_score(1900, 1500)
    assert math.isclose(p, 0.909, rel_tol=0.01)


def test_expected_score_weaker_side():
    p = expected_score(1500, 1900)
    assert math.isclose(p, 0.091, rel_tol=0.01)


def test_base_elo_is_1500():
    assert BASE_ELO == 1500


def test_home_advantage_is_100():
    assert HOME_ADVANTAGE == 100


def test_k_factor_default():
    assert k_factor(None) == 30
    assert k_factor("Friendly") == 30


def test_k_factor_tournament():
    assert k_factor("FIFA World Cup") == 60
    assert k_factor("Copa América") == 60
    assert k_factor("UEFA Euro") == 60
