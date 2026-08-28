"""Backfill matches.stage from the FIFA calendar API.

Calendar endpoint: idCompetition=17, idSeason=285023.
GET https://api.fifa.com/api/v3/calendar/matches?idCompetition=17&idSeason=285023&count=200
"""

import json
import sys
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from soccer_agent import db

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

FIFA_CALENDAR_URL = (
    "https://api.fifa.com/api/v3/calendar/matches"
    "?idCompetition=17&idSeason=285023&count=200"
)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_UPDATE_STAGE_SQL = """
UPDATE matches SET stage = %s
WHERE tournament = 'FIFA World Cup'
  AND match_date = %s
  AND (
    (home_team = %s AND away_team = %s)
    OR (home_team = %s AND away_team = %s)
  )
"""


def _map_team(name: str) -> str:
    return TEAM_MAP.get(name, name)


def parse_fifa_stages(payload: dict[str, Any]) -> list[tuple]:
    rows: list[tuple] = []
    for item in payload["Results"]:
        local_date = item["LocalDate"]
        match_day = date.fromisoformat(local_date.split("T", 1)[0])

        stage_raw = item["StageName"][0]["Description"]
        if stage_raw not in STAGE_MAP:
            raise ValueError(f"Unknown FIFA stage: {stage_raw}")
        stage = STAGE_MAP[stage_raw]

        home = _map_team(item["Home"]["TeamName"][0]["Description"])
        away = _map_team(item["Away"]["TeamName"][0]["Description"])
        rows.append((match_day, home, away, stage))
    return rows


def apply_stages(conn, rows) -> None:
    unmatched: list[tuple] = []
    for match_date, home, away, stage in rows:
        cur = conn.execute(
            _UPDATE_STAGE_SQL,
            (stage, match_date, home, away, away, home),
        )
        if cur.rowcount == 0:
            unmatched.append((match_date, home, away, stage))

    if unmatched:
        print("Unmatched FIFA calendar rows (no matching match in DB):")
        for row in unmatched:
            print(row)
        sys.exit(1)


def fetch_fifa_matches() -> dict[str, Any]:
    req = Request(FIFA_CALENDAR_URL, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req) as resp:
            body = resp.read()
    except HTTPError as exc:
        raise RuntimeError(f"FIFA calendar HTTP error: {exc}") from exc
    except URLError as exc:
        raise RuntimeError(f"FIFA calendar request failed: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"FIFA calendar returned invalid JSON: {exc}") from exc


def main() -> None:
    with db.connect() as conn:
        conn.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS stage TEXT")
        payload = fetch_fifa_matches()
        rows = parse_fifa_stages(payload)
        apply_stages(conn, rows)

        counts = conn.execute(
            """
            SELECT stage, count(*) FROM matches
            WHERE tournament = 'FIFA World Cup'
              AND EXTRACT(YEAR FROM match_date) = 2026
            GROUP BY stage ORDER BY 2 DESC
            """
        ).fetchall()

        fr_eng = conn.execute(
            """
            SELECT stage FROM matches
            WHERE tournament = 'FIFA World Cup'
              AND match_date = %s
              AND home_team = %s AND away_team = %s
            """,
            (date(2026, 7, 18), "France", "England"),
        ).fetchone()

    for stage, count in counts:
        print(f"{stage}: {count}")
    stage_val = fr_eng[0] if fr_eng else None
    print(f"France vs England 2026-07-18 stage: {stage_val}")


if __name__ == "__main__":
    main()
