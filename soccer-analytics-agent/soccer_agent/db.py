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
