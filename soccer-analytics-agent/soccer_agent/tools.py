"""Agent tools: schemas, guards, and dispatch."""

import re

from soccer_agent import db, embeddings, memory

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
    """Run a read-only query with a timeout and row cap."""
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
            "Run a read-only SQL SELECT against the soccer database. Tables: "
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
                    "description": "A single SELECT or WITH statement.",
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
            "Search long-term memory for durable facts relevant to a query. "
            "Use when the user refers to something they may have told you before."
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
]

_HANDLERS = {
    "sql_query": lambda args: sql_query(args["sql"]),
    "remember": lambda args: remember(args["fact"]),
    "recall": lambda args: recall(args["query"]),
    "vector_search": lambda args: vector_search(args["query"]),
    "hybrid_retrieve": lambda args: hybrid_retrieve(args["query"]),
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
