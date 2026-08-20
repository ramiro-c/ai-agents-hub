"""Postgres connection helpers."""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

DEFAULT_URL = "postgresql://soccer:soccer@localhost:5433/soccer"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def connect() -> psycopg.Connection:
    """Open a connection to the soccer database. Caller is responsible for closing."""
    return psycopg.connect(os.environ.get("DATABASE_URL", DEFAULT_URL))


def apply_schema() -> None:
    """Create tables and extensions if they do not exist (idempotent)."""
    with connect() as conn:
        conn.execute(SCHEMA_PATH.read_text())
        populate_match_winners(conn)


def populate_match_winners(conn) -> None:
    """Fill matches.winner from scores, then overlay shootout winners on draws."""
    conn.execute(
        """
        UPDATE matches SET winner = CASE
            WHEN home_score > away_score THEN home_team
            WHEN away_score > home_score THEN away_team
            ELSE NULL
        END
        """
    )
    conn.execute(
        """
        UPDATE matches AS m
        SET winner = s.winner
        FROM shootouts AS s
        WHERE m.match_date = s.match_date
          AND m.home_team = s.home_team
          AND m.away_team = s.away_team
        """
    )
