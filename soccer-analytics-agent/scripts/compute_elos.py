"""Compute team Elo ratings from the full match history and materialize them.

One-shot script — run after load_data.py. Idempotent (rebuilds team_elo).
Iterates 49k matches in a single ordered pass; ~100ms on a modern Mac.
"""

from soccer_agent import db
from soccer_agent.elo import (
    BASE_ELO,
    HOME_ADVANTAGE,
    expected_score,
    k_factor,
)


def main() -> None:
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT home_team, away_team, home_score, away_score,
                      tournament, neutral
               FROM matches
               WHERE home_score IS NOT NULL AND away_score IS NOT NULL
               ORDER BY match_date, home_team, away_team"""
        ).fetchall()

        elos: dict[str, float] = {}
        played: dict[str, int] = {}

        for row in rows:
            home, away, h_score, a_score, tournament, neutral = row

            elos.setdefault(home, BASE_ELO)
            elos.setdefault(away, BASE_ELO)

            home_elo = elos[home]
            away_elo = elos[away]

            effective_home = home_elo
            effective_away = away_elo
            if not neutral:
                effective_home += HOME_ADVANTAGE

            e_home = expected_score(effective_home, effective_away)
            e_away = 1.0 - e_home

            if h_score > a_score:
                s_home, s_away = 1.0, 0.0
            elif h_score < a_score:
                s_home, s_away = 0.0, 1.0
            else:
                s_home, s_away = 0.5, 0.5

            k = k_factor(tournament)

            elos[home] = home_elo + k * (s_home - e_home)
            elos[away] = away_elo + k * (s_away - e_away)
            played[home] = played.get(home, 0) + 1
            played[away] = played.get(away, 0) + 1

        # Materialize
        conn.execute("DELETE FROM team_elo")
        for team, elo in elos.items():
            conn.execute(
                """INSERT INTO team_elo (team, elo, matches_played)
                   VALUES (%s, %s, %s)""",
                (team, round(elo, 1), played[team]),
            )

        conn.commit()
        count = conn.execute("SELECT count(*) FROM team_elo").fetchone()[0]
        print(f"Computed Elo ratings for {count} teams.")

        # Show top 5
        top = conn.execute(
            "SELECT team, elo, matches_played FROM team_elo ORDER BY elo DESC LIMIT 5"
        ).fetchall()
        print("\nTop 5 teams by Elo:")
        for rank, (team, elo, matches) in enumerate(top, 1):
            print(f"  {rank}. {team}: {elo:.1f} ({matches} matches)")


if __name__ == "__main__":
    main()
