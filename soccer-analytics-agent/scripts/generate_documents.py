"""Generate rich text documents for each match and store them with embeddings.

One-shot script — run after load_data.py via `uv run`. Idempotent (clears
existing docs). Embeds ~49k documents with MiniLM; takes ~8 min on a modern Mac.
"""

from soccer_agent import db, embeddings, memory


def main() -> None:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT match_date, home_team, away_team, home_score, away_score,
                   tournament, city, country, neutral
            FROM matches
            WHERE match_date IS NOT NULL
            ORDER BY match_date
            """
        ).fetchall()

        conn.execute("TRUNCATE match_documents RESTART IDENTITY")

        for i, row in enumerate(rows, 1):
            match_date = row[0]
            home_team = row[1]
            away_team = row[2]
            home_score = row[3]
            away_score = row[4]
            tournament = row[5]
            city = row[6]
            country = row[7]
            neutral = row[8]

            content = (
                f"On {match_date}, {home_team} played {away_team} "
                f"in the {tournament or 'friendly'} "
                f"at {city or 'unknown city'}, {country or 'unknown country'}"
                f"{' (neutral venue)' if neutral else ''}. "
                f"Final score: {home_team} {home_score}"
                f" - {away_score} {away_team}."
            )
            vec = embeddings.embed(content)
            conn.execute(
                """INSERT INTO match_documents
                   (match_date, home_team, away_team, content, embedding)
                   VALUES (%s, %s, %s, %s, %s::vector)""",
                (match_date, home_team, away_team, content, memory.render_vector(vec)),
            )

            if i % 5000 == 0:
                conn.commit()
                print(f"  {i}/{len(rows)}...")

        conn.commit()
        count = conn.execute("SELECT count(*) FROM match_documents").fetchone()[0]
        print(f"Generated {count} documents.")


if __name__ == "__main__":
    main()
