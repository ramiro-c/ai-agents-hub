"""Agent tools: schemas, guards, and dispatch."""

import re

from soccer_agent import db

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
]

_HANDLERS = {"sql_query": lambda args: sql_query(args["sql"])}


def dispatch(name: str, args: dict) -> dict:
    """Route a model function call to its handler; never raise."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return handler(args)
    except Exception as exc:
        return {"error": str(exc)}
