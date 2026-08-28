"""Download the Kaggle international results dataset and load it into Postgres.

Truncates matches and repopulates winner only; matches.stage (2026 WC) is not
restored — run scripts/migrate_match_stages.py after load for stage backfill.
"""

import csv
from pathlib import Path

import kagglehub
import psycopg
from soccer_agent import db

DATASET = "martj42/international-football-results-from-1872-to-2017"

TABLES = {
    "results.csv": (
        "matches",
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
    ),
    "goalscorers.csv": (
        "goalscorers",
        [
            "match_date",
            "home_team",
            "away_team",
            "team",
            "scorer",
            "minute",
            "own_goal",
            "penalty",
        ],
    ),
    "shootouts.csv": (
        "shootouts",
        ["match_date", "home_team", "away_team", "winner", "first_shooter"],
    ),
}


def load_csv(
    conn: psycopg.Connection, table: str, columns: list[str], csv_path: Path
) -> int:
    """Stream a CSV into a table, mapping 'NA' and '' to NULL. Returns rows loaded."""
    cols = ", ".join(columns)
    count = 0
    with csv_path.open(newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header
        with (
            conn.cursor() as cur,
            cur.copy(f"COPY {table} ({cols}) FROM STDIN") as copy,
        ):
            for row in reader:
                copy.write_row([None if v in ("", "NA") else v for v in row])
                count += 1
    return count


def main() -> None:
    db.apply_schema()
    dataset_dir = Path(kagglehub.dataset_download(DATASET))
    with db.connect() as conn:
        for filename, (table, columns) in TABLES.items():
            conn.execute(f"TRUNCATE {table}")
            n = load_csv(conn, table, columns, dataset_dir / filename)
            print(f"{table}: {n} rows")
        db.populate_match_winners(conn)
        print("matches.winner: populated from scores and shootouts")
        print(
            "matches.stage: not loaded (Kaggle CSV has no stage). "
            "Run scripts/migrate_match_stages.py to backfill 2026 WC stages."
        )


if __name__ == "__main__":
    main()
