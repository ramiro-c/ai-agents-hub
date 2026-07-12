import csv
from pathlib import Path

import pytest
from scripts.load_data import load_csv
from soccer_agent import db

from tests.test_db import requires_db


@pytest.mark.integration
@requires_db
def test_load_csv_inserts_rows_and_converts_na(tmp_path: Path):
    db.apply_schema()
    p = tmp_path / "mini.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "date",
                "home_team",
                "away_team",
                "home_score",
                "away_score",
                "tournament",
                "city",
                "country",
                "neutral",
            ]
        )
        w.writerow(
            [
                "1872-11-30",
                "Scotland",
                "England",
                "0",
                "0",
                "Friendly",
                "Glasgow",
                "Scotland",
                "FALSE",
            ]
        )
        w.writerow(["2099-01-01", "A", "B", "NA", "NA", "Friendly", "X", "Y", "TRUE"])

    # Load into a session-local TEMP table so the real `matches` data is never
    # touched. The temp table is dropped automatically when the connection closes.
    with db.connect() as conn:
        conn.execute("CREATE TEMP TABLE matches_test (LIKE matches INCLUDING ALL)")
        n = load_csv(
            conn,
            "matches_test",
            [
                "match_date",
                "home_team",
                "away_team",
                "home_score",
                "away_score",
                "tournament",
                "city",
                "country",
                "neutral",
            ],
            p,
        )
        assert n == 2
        null_scores = conn.execute(
            "SELECT count(*) FROM matches_test WHERE home_score IS NULL"
        ).fetchone()[0]
    assert null_scores == 1
