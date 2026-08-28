"""Backfill matches.stage from the FIFA calendar API.

Calendar endpoint: idCompetition=17, idSeason=285023.
"""

from typing import Any

TEAM_MAP = {
    "USA": "United States",
    "Türkiye": "Turkey",
    "Côte d'Ivoire": "Ivory Coast",
    "IR Iran": "Iran",
    "Korea Republic": "South Korea",
    "Congo DR": "DR Congo",
    "Cabo Verde": "Cape Verde",
    "Czechia": "Czech Republic",
}

STAGE_MAP = {
    "First Stage": "Group stage",
    "Round of 32": "Round of 32",
    "Round of 16": "Round of 16",
    "Quarter-final": "Quarter-finals",
    "Semi-final": "Semi-finals",
    "Bronze final": "Third-place playoff",
    "Final": "Final",
}


def parse_fifa_stages(payload: dict[str, Any]) -> list[tuple]:
    raise NotImplementedError


def apply_stages(conn, rows) -> None:
    raise NotImplementedError


def fetch_fifa_matches() -> dict[str, Any]:
    raise NotImplementedError
