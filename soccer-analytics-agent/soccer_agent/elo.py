"""Elo rating system for international football teams.

Pure math — compute expected scores, update ratings, produce the ranked table.
The heavy lifting (iterating 49k matches) lives in scripts/compute_elos.py.
This module is the formula library.

Elo is a relative rating system:
- Expected score: E_A = 1 / (1 + 10^((R_B - R_A) / 400))
- Rating update: R_A_new = R_A + K * (actual - expected)
- Home advantage: +100 Elo for the home team in expected-score calc only
"""

import math

BASE_ELO = 1500
K_DEFAULT = 30
K_TOURNAMENT = 60
HOME_ADVANTAGE = 100

IMPORTANT_TOURNAMENTS = {
    "FIFA World Cup",
    "UEFA Euro",
    "Copa América",
    "AFC Asian Cup",
    "Africa Cup of Nations",
    "CONCACAF Gold Cup",
}


def expected_score(rating_a: float, rating_b: float) -> float:
    """Probability that team A beats team B, given their ratings."""
    return 1.0 / (1.0 + math.pow(10, (rating_b - rating_a) / 400.0))


def k_factor(tournament: str | None) -> int:
    """Higher K for important tournaments — bigger rating swings."""
    if tournament and tournament in IMPORTANT_TOURNAMENTS:
        return K_TOURNAMENT
    return K_DEFAULT
