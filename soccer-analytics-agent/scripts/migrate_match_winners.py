"""Idempotent matches.winner backfill. Needs ALTER/UPDATE on matches.

soccer_app is SELECT-only, and Cloud Run does not apply_schema at boot, so
production has to run this as postgres through the Cloud SQL Auth Proxy:

    DATABASE_URL=postgresql://postgres:...@127.0.0.1:15432/soccer \\
        uv run python scripts/migrate_match_winners.py
"""

from soccer_agent import db


def main() -> None:
    with db.connect() as conn:
        conn.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS winner TEXT")
        db.populate_match_winners(conn)
        filled, total = conn.execute(
            "SELECT COUNT(*) FILTER (WHERE winner IS NOT NULL), COUNT(*) FROM matches"
        ).fetchone()
        last = conn.execute(
            """
            SELECT match_date, home_team, away_team, home_score, away_score, winner
            FROM matches
            WHERE tournament = 'FIFA World Cup'
              AND EXTRACT(YEAR FROM match_date) = 2026
            ORDER BY match_date DESC
            LIMIT 1
            """
        ).fetchone()
    print(f"matches.winner populated: {filled}/{total} rows")
    print(f"2026 WC last scored row: {last}")


if __name__ == "__main__":
    main()
