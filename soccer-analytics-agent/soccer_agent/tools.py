"""Agent tools: schemas, guards, and dispatch."""

import re

from soccer_agent import db, memory

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
]

_HANDLERS = {
    "sql_query": lambda args: sql_query(args["sql"]),
    "remember": lambda args: remember(args["fact"]),
    "recall": lambda args: recall(args["query"]),
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
