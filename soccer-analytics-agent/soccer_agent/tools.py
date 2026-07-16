"""Agent tools: schemas, guards, and dispatch."""

import re

from soccer_agent import db, embeddings, memory
from soccer_agent.team_names import translate

MAX_ROWS = 50
TIMEOUT_MS = 5000
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|vacuum)\b",
    re.IGNORECASE,
)


def validate_sql(sql: str) -> str:
    """Allow a single read-only SELECT/WITH statement; raise ValueError otherwise."""
    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        raise ValueError("only a single statement is allowed")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise ValueError("only SELECT/WITH queries are allowed")
    if FORBIDDEN.search(cleaned):
        raise ValueError("write/DDL keywords are not allowed")
    return cleaned


def sql_query(sql: str) -> dict:
    """Run a read-only PostgreSQL query with a timeout and row cap."""
    try:
        cleaned = validate_sql(sql)
        with db.connect() as conn:
            conn.execute(f"SET statement_timeout = {TIMEOUT_MS}")
            cur = conn.execute(cleaned)
            columns = [d.name for d in cur.description]
            rows = [
                [str(v) if v is not None else None for v in r]
                for r in cur.fetchmany(MAX_ROWS)
            ]
        return {"columns": columns, "rows": rows}
    except Exception as exc:  # surfaced to the model as a tool result
        return {"error": str(exc)}


def remember(fact: str) -> dict:
    """Store a durable fact in semantic memory."""
    try:
        memory.remember_fact(fact)
        return {"status": "remembered"}
    except Exception as exc:
        return {"error": str(exc)}


def recall(query: str) -> dict:
    """Search durable facts in semantic memory."""
    try:
        return {"facts": memory.search_semantic(query, k=3)}
    except Exception as exc:
        return {"error": str(exc)}


def get_team_elo(teams: str) -> dict:
    """Return current Elo ratings for one or two teams (comma-separated)."""
    try:
        raw_names = [t.strip() for t in teams.split(",")]
        team_list = [translate(t) for t in raw_names]
        with db.connect() as conn:
            elos = {}
            not_found = []
            for team in team_list:
                row = conn.execute(
                    "SELECT elo, matches_played FROM team_elo WHERE team = %s",
                    (team,),
                ).fetchone()
                if row:
                    elos[team] = {"elo": round(float(row[0]), 1), "matches": row[1]}
                else:
                    not_found.append(team)
        result: dict = {"elos": elos, "not_found": not_found or None}
        renamed = {r: t for r, t in zip(raw_names, team_list) if r != t}
        if renamed:
            result["queried_names"] = renamed
        return result
    except Exception as exc:
        return {"error": str(exc)}


def get_team_form(team: str, n: int = 5) -> dict:
    """Return a team's last N match results (W/D/L)."""
    try:
        team_raw = team.strip()
        team = translate(team)
        with db.connect() as conn:
            rows = conn.execute(
                """SELECT match_date, home_team, away_team,
                      home_score, away_score, tournament
               FROM matches
               WHERE (home_team = %s OR away_team = %s)
                 AND home_score IS NOT NULL AND away_score IS NOT NULL
               ORDER BY match_date DESC
               LIMIT %s""",
                (team, team, n),
            ).fetchall()
            form = []
            for row in rows:
                date, home, away, h_score, a_score, tournament = row
                is_home = home == team
                opponent = away if is_home else home
                scored = h_score if is_home else a_score
                conceded = a_score if is_home else h_score
                if scored > conceded:
                    result = "W"
                elif scored < conceded:
                    result = "L"
                else:
                    result = "D"
                    # Check if draw was resolved by penalty shootout
                    shoot = conn.execute(
                        "SELECT winner FROM shootouts "
                        "WHERE match_date = %s AND home_team = %s "
                        "AND away_team = %s",
                        (date, home, away),
                    ).fetchone()
                    if shoot:
                        result = "W" if shoot[0] == team else "L"
                form.append(
                    {
                        "date": str(date),
                        "opponent": opponent,
                        "result": result,
                        "score": f"{scored}-{conceded}",
                        "venue": "home" if is_home else "away",
                        "tournament": tournament or "Friendly",
                    }
                )
        result: dict = {"team": team, "form": form, "last_n": n}
        if team_raw != team:
            result["queried_name"] = team_raw
        return result
    except Exception as exc:
        return {"error": str(exc)}


def get_h2h(team1: str, team2: str, n: int = 10) -> dict:
    """Return the head-to-head record between two teams."""
    try:
        team1_raw = team1.strip()
        team2_raw = team2.strip()
        team1 = translate(team1)
        team2 = translate(team2)
        with db.connect() as conn:
            rows = conn.execute(
                """SELECT match_date, home_team, away_team,
                          home_score, away_score, tournament
                   FROM matches
                   WHERE ((home_team = %s AND away_team = %s)
                      OR (home_team = %s AND away_team = %s))
                     AND home_score IS NOT NULL AND away_score IS NOT NULL
                   ORDER BY match_date DESC
                   LIMIT %s""",
                (team1, team2, team2, team1, n),
            ).fetchall()
            wins1, wins2, draws = 0, 0, 0
            matches = []
            for row in rows:
                date, home, away, h_score, a_score, tournament = row
                if h_score > a_score:
                    winner = home
                elif h_score < a_score:
                    winner = away
                else:
                    winner = None
                    # Check if draw was resolved by penalty shootout
                    shoot = conn.execute(
                        "SELECT winner FROM shootouts "
                        "WHERE match_date = %s AND home_team = %s "
                        "AND away_team = %s",
                        (date, home, away),
                    ).fetchone()
                    if shoot:
                        winner = shoot[0]
                if winner == team1:
                    wins1 += 1
                elif winner == team2:
                    wins2 += 1
                else:
                    draws += 1
                matches.append(
                    {
                        "date": str(date),
                        "home": home,
                        "away": away,
                        "score": f"{h_score}-{a_score}",
                        "tournament": tournament or "Friendly",
                    }
                )
        result: dict = {
            "team1": team1,
            "team2": team2,
            "record": {team1: wins1, team2: wins2, "draws": draws},
            "total": len(matches),
            "last_matches": matches,
        }
        if team1_raw != team1:
            result["team1_queried"] = team1_raw
        if team2_raw != team2:
            result["team2_queried"] = team2_raw
        return result
    except Exception as exc:
        return {"error": str(exc)}


def predict_match_elo(team1: str, team2: str) -> dict:
    """Predict match outcome using Elo-based probabilities.

    Treats team1 as home (adds home advantage).
    """
    try:
        team1_raw = team1.strip()
        team2_raw = team2.strip()
        team1 = translate(team1)
        team2 = translate(team2)
        from soccer_agent.elo import HOME_ADVANTAGE, expected_score

        with db.connect() as conn:
            r1 = conn.execute(
                "SELECT elo FROM team_elo WHERE team = %s", (team1,)
            ).fetchone()
            r2 = conn.execute(
                "SELECT elo FROM team_elo WHERE team = %s", (team2,)
            ).fetchone()

        if r1 is None or r2 is None:
            missing = [t for t, r in [(team1, r1), (team2, r2)] if r is None]
            return {"error": f"Unknown team(s): {', '.join(missing)}"}

        elo1, elo2 = float(r1[0]), float(r2[0])

        effective1 = elo1 + HOME_ADVANTAGE
        effective2 = elo2

        p1_win = expected_score(effective1, effective2)
        p2_win = expected_score(effective2, effective1)

        elo_diff = abs(elo1 - elo2)
        draw_factor = max(0, 0.26 - 0.0004 * elo_diff)
        p_draw = min(draw_factor, 1 - max(p1_win, p2_win))

        total = p1_win + p2_win + p_draw
        p1_win /= total
        p2_win /= total
        p_draw /= total

        result: dict = {
            "team1": team1,
            "team2": team2,
            "ratings": {team1: round(elo1, 1), team2: round(elo2, 1)},
            "elo_diff": round(elo1 - elo2, 1),
            "home_advantage_applied": True,
            "probabilities": {
                f"{team1}_win": round(p1_win, 4),
                f"{team2}_win": round(p2_win, 4),
                "draw": round(p_draw, 4),
            },
            "prediction_note": (
                f"{team1} has a {p1_win * 100:.1f}% chance to win, "
                f"{team2} {p2_win * 100:.1f}%, "
                f"draw {p_draw * 100:.1f}%"
            ),
        }
        if team1_raw != team1:
            result["team1_queried"] = team1_raw
        if team2_raw != team2:
            result["team2_queried"] = team2_raw
        return result
    except Exception as exc:
        return {"error": str(exc)}


def predict_match(team1: str, team2: str) -> dict:
    """Predict match outcome: XGBoost model first, Elo heuristic as fallback.

    team1 is treated as home. Transparent to the model — same contract as v1.
    """
    try:
        team1_raw = team1.strip()
        team2_raw = team2.strip()
        team1 = translate(team1)
        team2 = translate(team2)
        from soccer_agent.predictor import predict_match_xgb

        result = predict_match_xgb(team1, team2)
        if "error" not in result:
            # Normalize to the shared contract: the frontend ProbabilityBar and
            # the analytics panel read top-level team1/team2 (the Elo fallback
            # already includes them); the XGBoost result does not.
            result = {**result, "team1": team1, "team2": team2}
            if team1_raw != team1:
                result["team1_queried"] = team1_raw
            if team2_raw != team2:
                result["team2_queried"] = team2_raw
            return result
    except Exception as e:  # noqa: BLE001 - never let serving break the tool
        print(f"Error predicting match: {e}")
        pass
    return predict_match_elo(team1_raw, team2_raw)


def vector_search(query: str) -> dict:
    """Semantic-only search over match documents (for comparison with hybrid)."""
    try:
        vec = embeddings.embed(query)
        vec_str = memory.render_vector(vec)
        with db.connect() as conn:
            rows = conn.execute(
                """SELECT id, content, match_date, home_team, away_team,
                   1 - (embedding <=> %s::vector) AS score
                   FROM match_documents
                   ORDER BY embedding <=> %s::vector
                   LIMIT 5""",
                (vec_str, vec_str),
            ).fetchall()
        return {
            "results": [
                {
                    "id": r[0],
                    "content": r[1],
                    "date": str(r[2]),
                    "teams": f"{r[3]} vs {r[4]}",
                    "score": round(float(r[5]), 4),
                }
                for r in rows
            ]
        }
    except Exception as exc:
        return {"error": str(exc)}


def hybrid_retrieve(query: str) -> dict:
    """Search match documents with hybrid retrieval (vector + full-text, RRF-fused)."""
    try:
        from soccer_agent.retrieval import rrf_fuse

        vec = embeddings.embed(query)
        vec_str = memory.render_vector(vec)

        with db.connect() as conn:
            vec_rows = conn.execute(
                """SELECT id, content, match_date, home_team, away_team,
                   1 - (embedding <=> %s::vector) AS score
                   FROM match_documents
                   ORDER BY embedding <=> %s::vector
                   LIMIT 20""",
                (vec_str, vec_str),
            ).fetchall()

            ts_rows = conn.execute(
                """SELECT id, content, match_date, home_team, away_team,
                   ts_rank(tsv, websearch_to_tsquery('english', %s)) AS score
                   FROM match_documents
                   WHERE tsv @@ websearch_to_tsquery('english', %s)
                   ORDER BY score DESC
                   LIMIT 20""",
                (query, query),
            ).fetchall()

        vec_ranked = [
            {
                "id": r[0],
                "content": r[1],
                "date": str(r[2]),
                "teams": f"{r[3]} vs {r[4]}",
                "source": "vector",
            }
            for r in vec_rows
        ]
        ts_ranked = [
            {
                "id": r[0],
                "content": r[1],
                "date": str(r[2]),
                "teams": f"{r[3]} vs {r[4]}",
                "source": "fulltext",
            }
            for r in ts_rows
        ]

        fused = rrf_fuse(vec_ranked, ts_ranked, k=60, top_n=5)
        vec_ids = {v["id"] for v in vec_ranked}
        ts_ids = {t["id"] for t in ts_ranked}
        for item in fused:
            sources = []
            if item["id"] in vec_ids:
                sources.append("vector")
            if item["id"] in ts_ids:
                sources.append("fulltext")
            item["sources"] = sources
        return {"results": fused}
    except Exception as exc:
        return {"error": str(exc)}


TOOL_DECLARATIONS = [
    {
        "name": "sql_query",
        "description": (
            "Use this tool ONLY when no specialized tool (get_h2h, get_team_form, "
            "predict_match, get_team_elo) covers the question. "
            "Run a read-only SQL SELECT against the PostgreSQL soccer database. "
            "Team names are stored in English — translate non-English names "
            "before writing SQL. "
            "For year filters use EXTRACT(YEAR FROM match_date); for "
            "case-insensitive text use ILIKE (e.g. tournament ILIKE '%world cup%'). "
            "Tables: "
            "matches(match_date, home_team, away_team, home_score, away_score, "
            "tournament, city, country, neutral), "
            "goalscorers(match_date, home_team, away_team, team, scorer, minute, "
            "own_goal, penalty), "
            "shootouts(match_date, home_team, away_team, winner, first_shooter). "
            "Results are capped at 50 rows, so aggregate or LIMIT accordingly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A SELECT or WITH statement (PostgreSQL).",
                }
            },
            "required": ["sql"],
        },
    },
    {
        "name": "remember",
        "description": (
            "Store a durable fact about the user or the world in long-term memory "
            "(e.g. a stated preference). Use for facts worth recalling in future "
            "conversations, not for one-off details."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The fact to store, as a short sentence.",
                }
            },
            "required": ["fact"],
        },
    },
    {
        "name": "recall",
        "description": (
            "Use this tool when the user refers to things they mentioned in "
            "previous conversations. "
            "Searches long-term memory for durable facts relevant to a query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look up in memory."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "vector_search",
        "description": (
            "Search match documents by meaning (semantic similarity). "
            "Returns the 5 most semantically relevant matches. "
            "Best for fuzzy or conceptual queries like 'high-scoring finals'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "hybrid_retrieve",
        "description": (
            "Search match documents with hybrid retrieval — combines semantic "
            "meaning (vector) with exact keywords (full-text), fused with RRF. "
            "Returns the 5 best matches across both methods. Best for queries "
            "that mix concepts with specific names like 'Argentina World Cup wins'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_team_elo",
        "description": (
            "Use this tool when the user asks about Elo ratings or relative "
            "team strength. "
            "Returns current Elo ratings for one or two teams. "
            "Accepts a single team name or two comma-separated names."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "teams": {
                    "type": "string",
                    "description": (
                        "Team name(s), comma-separated. "
                        "e.g. 'Argentina' or 'Argentina,France'"
                    ),
                }
            },
            "required": ["teams"],
        },
    },
    {
        "name": "get_team_form",
        "description": (
            "Use this tool when the user asks about a single team's recent results, "
            "last N matches, or current form. "
            "Returns date, opponent, result (W/D/L), score, venue, and tournament "
            "for each match."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "team": {"type": "string", "description": "Team name."},
                "n": {
                    "type": "integer",
                    "description": "Number of recent matches (default 5).",
                },
            },
            "required": ["team"],
        },
    },
    {
        "name": "get_h2h",
        "description": (
            "Use this tool when the user asks about head-to-head, previous meetings, "
            "or the record between two specific teams. "
            "Returns overall record (wins/draws) and recent match history."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "team1": {"type": "string", "description": "First team name."},
                "team2": {"type": "string", "description": "Second team name."},
                "n": {
                    "type": "integer",
                    "description": "Number of recent matches to show (default 10).",
                },
            },
            "required": ["team1", "team2"],
        },
    },
    {
        "name": "predict_match",
        "description": (
            "Use this tool when the user asks who will win or wants outcome "
            "probabilities between two teams. Returns win/draw/loss probabilities "
            "from a trained model (Elo-based fallback if unavailable). "
            "Treats team1 as home."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "team1": {"type": "string", "description": "Home team name."},
                "team2": {"type": "string", "description": "Away team name."},
            },
            "required": ["team1", "team2"],
        },
    },
]

_HANDLERS = {
    "sql_query": lambda args: sql_query(args["sql"]),
    "remember": lambda args: remember(args["fact"]),
    "recall": lambda args: recall(args["query"]),
    "vector_search": lambda args: vector_search(args["query"]),
    "hybrid_retrieve": lambda args: hybrid_retrieve(args["query"]),
    "get_team_elo": lambda args: get_team_elo(args["teams"]),
    "get_team_form": lambda args: get_team_form(args["team"], args.get("n", 5)),
    "get_h2h": lambda args: get_h2h(args["team1"], args["team2"], args.get("n", 10)),
    "predict_match": lambda args: predict_match(args["team1"], args["team2"]),
}


def dispatch(name: str, args: dict) -> dict:
    """Route a model function call to its handler; never raise."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return handler(args)
    except Exception as exc:
        return {"error": str(exc)}
