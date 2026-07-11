import psycopg
import pytest
from soccer_agent import db


def _db_up() -> bool:
    try:
        with db.connect():
            return True
    except psycopg.OperationalError:
        return False


requires_db = pytest.mark.skipif(not _db_up(), reason="local Postgres is down")


@pytest.mark.integration
@requires_db
def test_schema_creates_tables():
    db.apply_schema()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        ).fetchall()
    names = {r[0] for r in rows}
    assert {"matches", "goalscorers", "shootouts"} <= names
