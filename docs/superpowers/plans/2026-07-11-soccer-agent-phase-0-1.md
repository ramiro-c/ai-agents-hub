# Soccer Analytics Agent — Phase 0+1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the data layer (Postgres+pgvector with 49k Kaggle matches) and a minimal hand-written agent loop (Gemini + `sql_query` tool + CLI REPL) that answers soccer questions from the database.

**Architecture:** A standalone `uv` project at `soccer-analytics-agent/`. Postgres 16 + pgvector runs in Docker; a loader script ingests the Kaggle CSVs. The agent is a hand-written loop over the raw `google-genai` SDK: build request with tool declarations → detect `function_call` parts → dispatch → feed `function_response` back → repeat until the model answers in text.

**Tech Stack:** Python 3.12, uv, psycopg 3, Docker (pgvector/pgvector:pg16), google-genai, kagglehub, pytest.

**Spec:** `docs/superpowers/specs/2026-07-10-soccer-analytics-agent-design.md`

## Testing Approach

Behavior-first, not strict TDD. For each task: implement first, then run the behavior tests included in the task. Skip every "run test to verify it fails" step — those are optional. Do not add tests beyond the ones written here; the included ones (SQL guard, loop with fake client, smoke test) are the safety net for later phases.

## Global Constraints

- Python 3.12+; dependency management with `uv` only (no pip installs).
- All code, comments, and docstrings in English.
- `sql_query` is read-only: SELECT/WITH only, single statement, 5s timeout, 50-row cap.
- DB connection string comes from env `DATABASE_URL`, default `postgresql://soccer:soccer@localhost:5433/soccer`.
- Gemini model from env `GEMINI_MODEL`, default `gemini-2.5-flash`. Client auth via standard `google-genai` env vars (API key or Vertex).
- Tests that need the DB are marked `@pytest.mark.integration` and skip cleanly when the DB is down.
- Conventional commits, no AI attribution.
- All commands below run from `soccer-analytics-agent/` unless noted.

---



### Task 1: Project scaffold

**Files:**

- Create: `soccer-analytics-agent/pyproject.toml`
- Create: `soccer-analytics-agent/.env.example`
- Create: `soccer-analytics-agent/.gitignore`
- Create: `soccer-analytics-agent/soccer_agent/__init__.py`
- Create: `soccer-analytics-agent/README.md`

**Interfaces:**

- Consumes: nothing.
- Produces: installable package `soccer_agent`; env conventions used by every later task.

- [x] **Step 1: Create the project**

`soccer-analytics-agent/pyproject.toml`:

```toml
[project]
name = "soccer-agent"
version = "0.1.0"
description = "Soccer analytics agent with a hand-written LLM tool loop"
requires-python = ">=3.12"
dependencies = [
    "google-genai>=1.16",
    "psycopg[binary]>=3.2",
    "python-dotenv>=1.0",
    "kagglehub>=0.3",
]

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
markers = ["integration: requires the local Postgres container"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["soccer_agent"]
```

`soccer-analytics-agent/.env.example`:

```bash
DATABASE_URL=postgresql://soccer:soccer@localhost:5433/soccer
GEMINI_MODEL=gemini-2.5-flash
# Option A — AI Studio key:
GOOGLE_API_KEY=your-key
# Option B — Vertex AI (burns GCP credits):
# GOOGLE_GENAI_USE_VERTEXAI=true
# GOOGLE_CLOUD_PROJECT=your-project
# GOOGLE_CLOUD_LOCATION=us-central1
```

`soccer-analytics-agent/.gitignore`:

```
data/
.env
__pycache__/
.venv/
```

`soccer_agent/__init__.py`: empty file.

`README.md`: title, one-paragraph description, quickstart (`uv sync`, `docker compose up -d`, `uv run python scripts/load_data.py`, `uv run python -m soccer_agent.cli`).

- [x] **Step 2: Verify it installs**

Run: `cd soccer-analytics-agent && uv sync --all-groups && uv run python -c "import soccer_agent; print('ok')"`
Expected: `ok`

- [x] **Step 3: Commit**

```bash
git add soccer-analytics-agent
git commit -m "feat(soccer-agent): scaffold uv project"
```

---



### Task 2: Postgres + pgvector in Docker, schema

**Files:**

- Create: `soccer-analytics-agent/docker-compose.yml`
- Create: `soccer-analytics-agent/db/schema.sql`
- Create: `soccer-analytics-agent/soccer_agent/db.py`
- Test: `soccer-analytics-agent/tests/test_db.py`

**Interfaces:**

- Consumes: `DATABASE_URL` env convention from Task 1.
- Produces: `soccer_agent.db.connect() -> psycopg.Connection` (caller closes; use as context manager) and `soccer_agent.db.apply_schema() -> None`.

- [x] **Step 1: Write docker-compose and schema**

`docker-compose.yml`:

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: soccer
      POSTGRES_PASSWORD: soccer
      POSTGRES_DB: soccer
    ports:
      - "5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

`db/schema.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY,
    match_date DATE NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_score INT,
    away_score INT,
    tournament TEXT,
    city TEXT,
    country TEXT,
    neutral BOOLEAN
);

CREATE TABLE IF NOT EXISTS goalscorers (
    id BIGSERIAL PRIMARY KEY,
    match_date DATE NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    team TEXT,
    scorer TEXT,
    minute INT,
    own_goal BOOLEAN,
    penalty BOOLEAN
);

CREATE TABLE IF NOT EXISTS shootouts (
    id BIGSERIAL PRIMARY KEY,
    match_date DATE NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    winner TEXT,
    first_shooter TEXT
);

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches (match_date);
CREATE INDEX IF NOT EXISTS idx_matches_home ON matches (home_team);
CREATE INDEX IF NOT EXISTS idx_matches_away ON matches (away_team);
CREATE INDEX IF NOT EXISTS idx_goalscorers_scorer ON goalscorers (scorer);
```

- [x] **Step 2: Write the failing test**

`tests/test_db.py`:

```python
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
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    names = {r[0] for r in rows}
    assert {"matches", "goalscorers", "shootouts"} <= names
```

- [x] **Step 3: Run test to verify it fails**

Run: `docker compose up -d && sleep 5 && uv run pytest tests/test_db.py -v`
Expected: FAIL with `AttributeError` / import error (`db.connect` not defined).

- [x] **Step 4: Implement db.py**

`soccer_agent/db.py`:

```python
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
```

- [x] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (1 passed).

- [x] **Step 6: Commit**

```bash
git add soccer-analytics-agent
git commit -m "feat(soccer-agent): postgres+pgvector compose, schema and db helpers"
```

---



### Task 3: Kaggle data download + load

**Files:**

- Create: `soccer-analytics-agent/scripts/load_data.py`
- Test: `soccer-analytics-agent/tests/test_load_data.py`

**Interfaces:**

- Consumes: `db.connect()`, `db.apply_schema()` from Task 2.
- Produces: populated `matches`, `goalscorers`, `shootouts` tables; helper `load_csv(conn, table: str, columns: list[str], csv_path: Path) -> int` (returns row count).

- [x] **Step 1: Write the failing test**

`tests/test_load_data.py`:

```python
import csv
from pathlib import Path

import pytest

from soccer_agent import db
from tests.test_db import requires_db

from scripts.load_data import load_csv


@pytest.mark.integration
@requires_db
def test_load_csv_inserts_rows_and_converts_na(tmp_path: Path):
    db.apply_schema()
    p = tmp_path / "mini.csv"
    with p.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "home_team", "away_team", "home_score", "away_score",
                    "tournament", "city", "country", "neutral"])
        w.writerow(["1872-11-30", "Scotland", "England", "0", "0",
                    "Friendly", "Glasgow", "Scotland", "FALSE"])
        w.writerow(["2099-01-01", "A", "B", "NA", "NA", "Friendly", "X", "Y", "TRUE"])

    with db.connect() as conn:
        conn.execute("TRUNCATE matches")
        n = load_csv(conn, "matches",
                     ["match_date", "home_team", "away_team", "home_score",
                      "away_score", "tournament", "city", "country", "neutral"], p)
        assert n == 2
        null_scores = conn.execute(
            "SELECT count(*) FROM matches WHERE home_score IS NULL"
        ).fetchone()[0]
    assert null_scores == 1
```

Note: `scripts/` needs an empty `scripts/__init__.py` so the test can import it.

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_load_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.load_data'`.

- [x] **Step 3: Implement the loader**

`scripts/__init__.py`: empty. `scripts/load_data.py`:

```python
"""Download the Kaggle international results dataset and load it into Postgres."""

import csv
from pathlib import Path

import kagglehub
import psycopg

from soccer_agent import db

DATASET = "martj42/international-football-results-from-1872-to-2017"

TABLES = {
    "results.csv": ("matches", ["match_date", "home_team", "away_team", "home_score",
                                "away_score", "tournament", "city", "country", "neutral"]),
    "goalscorers.csv": ("goalscorers", ["match_date", "home_team", "away_team", "team",
                                        "scorer", "minute", "own_goal", "penalty"]),
    "shootouts.csv": ("shootouts", ["match_date", "home_team", "away_team", "winner",
                                    "first_shooter"]),
}


def load_csv(conn: psycopg.Connection, table: str, columns: list[str], csv_path: Path) -> int:
    """Stream a CSV into a table, mapping 'NA' and '' to NULL. Returns rows loaded."""
    cols = ", ".join(columns)
    count = 0
    with csv_path.open(newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header
        with conn.cursor() as cur, cur.copy(f"COPY {table} ({cols}) FROM STDIN") as copy:
            for row in reader:
                copy.write_row([None if v in ("", "NA") else v for v in row])
                count += 1
    return count


def main() -> None:
    db.apply_schema()
    dataset_dir = Path(kagglehub.dataset_download(DATASET))
    with db.connect() as conn:
        for filename, (table, columns) in TABLES.items():
            conn.execute(f"TRUNCATE {table}")
            n = load_csv(conn, table, columns, dataset_dir / filename)
            print(f"{table}: {n} rows")


if __name__ == "__main__":
    main()
```

Note: the Kaggle slug keeps its historical name but the dataset is updated through 2024+. If `minute` arrives as a float string like `"90.0"`, Postgres COPY will reject it — in that case convert in `load_csv`: `v = str(int(float(v)))` for the minute column. Only add this if the real load fails.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_load_data.py -v`
Expected: PASS.

- [x] **Step 5: Run the real load**

Run: `uv run python scripts/load_data.py`
Expected: three lines printing row counts; `matches` around 49,000, `goalscorers` around 47,000, `shootouts` around 650.

- [x] **Step 6: Sanity-check the data**

Run: `uv run python -c "from soccer_agent import db; print(db.connect().execute('SELECT max(match_date) FROM matches').fetchone())"`
Expected: a date in 2024 or later.

- [x] **Step 7: Commit**

```bash
git add soccer-analytics-agent
git commit -m "feat(soccer-agent): kaggle dataset loader"
```

---



### Task 4: Read-only `sql_query` tool

**Files:**

- Create: `soccer-analytics-agent/soccer_agent/tools.py`
- Test: `soccer-analytics-agent/tests/test_tools.py`

**Interfaces:**

- Consumes: `db.connect()` from Task 2.
- Produces:
  - `validate_sql(sql: str) -> str` — returns the cleaned SQL or raises `ValueError`.
  - `sql_query(sql: str) -> dict` — `{"columns": [...], "rows": [[...], ...]}` or `{"error": "..."}`.
  - `TOOL_DECLARATIONS: list[dict]` and `dispatch(name: str, args: dict) -> dict` for the loop.

- [x] **Step 1: Write the failing tests (pure validation first — no DB needed)**

`tests/test_tools.py`:

```python
import pytest

from soccer_agent.tools import dispatch, sql_query, validate_sql
from tests.test_db import requires_db


def test_validate_accepts_select():
    assert validate_sql("SELECT 1") == "SELECT 1"


def test_validate_accepts_with_cte():
    assert validate_sql("WITH x AS (SELECT 1) SELECT * FROM x").startswith("WITH")


def test_validate_strips_trailing_semicolon():
    assert validate_sql("SELECT 1;") == "SELECT 1"


@pytest.mark.parametrize("bad", [
    "DELETE FROM matches",
    "INSERT INTO matches VALUES (1)",
    "DROP TABLE matches",
    "SELECT 1; DELETE FROM matches",
    "UPDATE matches SET home_score = 9",
])
def test_validate_rejects_writes(bad):
    with pytest.raises(ValueError):
        validate_sql(bad)


@pytest.mark.integration
@requires_db
def test_sql_query_caps_rows():
    result = sql_query("SELECT generate_series(1, 1000)")
    assert len(result["rows"]) == 50


@pytest.mark.integration
@requires_db
def test_sql_query_returns_error_instead_of_raising():
    result = sql_query("SELECT nope FROM nowhere")
    assert "error" in result


def test_dispatch_unknown_tool():
    assert "error" in dispatch("no_such_tool", {})
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'soccer_agent.tools'`.

- [x] **Step 3: Implement tools.py**

`soccer_agent/tools.py`:

```python
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
            rows = [[str(v) if v is not None else None for v in r]
                    for r in cur.fetchmany(MAX_ROWS)]
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
            "properties": {"sql": {"type": "string", "description": "A single SELECT or WITH statement."}},
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
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py -v`
Expected: PASS (all).

- [x] **Step 5: Commit**

```bash
git add soccer-analytics-agent
git commit -m "feat(soccer-agent): read-only sql_query tool with guards"
```

---



### Task 5: The agent loop

**Files:**

- Create: `soccer-analytics-agent/soccer_agent/loop.py`
- Test: `soccer-analytics-agent/tests/test_loop.py`

**Interfaces:**

- Consumes: `tools.TOOL_DECLARATIONS`, `tools.dispatch` from Task 4.
- Produces: `run_turn(client, history: list, user_message: str, model: str) -> tuple[str, list]` — returns (final answer text, updated history). `client` is a `genai.Client` (or a fake with the same `models.generate_content` shape — this is the dependency-injection seam for tests).

- [x] **Step 1: Write the failing test with a fake client**

`tests/test_loop.py`:

```python
from types import SimpleNamespace

from google.genai import types

from soccer_agent.loop import run_turn


class FakeModels:
    """Scripted Gemini: first turn calls a tool, second turn answers."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(contents)
        return self._responses.pop(0)


def _response(parts):
    content = types.Content(role="model", parts=parts)
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)])


def test_run_turn_dispatches_tool_then_answers(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "soccer_agent.loop.dispatch",
        lambda name, args: calls.append((name, args)) or {"rows": [["49000"]]},
    )
    fake = SimpleNamespace(models=FakeModels([
        _response([types.Part.from_function_call(name="sql_query", args={"sql": "SELECT count(*) FROM matches"})]),
        _response([types.Part(text="There are 49,000 matches.")]),
    ]))

    answer, history = run_turn(fake, [], "How many matches are there?", model="test")

    assert calls == [("sql_query", {"sql": "SELECT count(*) FROM matches"})]
    assert answer == "There are 49,000 matches."
    # history: user msg, model tool call, tool response, model answer
    assert len(history) == 4


def test_run_turn_plain_answer_no_tools():
    fake = SimpleNamespace(models=FakeModels([_response([types.Part(text="Hi!")])]))
    answer, history = run_turn(fake, [], "hello", model="test")
    assert answer == "Hi!"
    assert len(history) == 2
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_loop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'soccer_agent.loop'`.

- [x] **Step 3: Implement loop.py**

`soccer_agent/loop.py`:

```python
"""Hand-written agent loop: model -> tool calls -> tool results -> model."""

from google.genai import types

from soccer_agent.tools import TOOL_DECLARATIONS, dispatch

MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = (
    "You are a soccer analytics assistant with access to a database of "
    "international matches from 1872 to today. Use the sql_query tool to "
    "ground every factual answer in data. Answer in the user's language. "
    "If a query returns no rows, say so honestly instead of guessing."
)


def _config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
    )


def run_turn(client, history: list, user_message: str, model: str) -> tuple[str, list]:
    """Run one conversational turn, dispatching tool calls until the model answers."""
    history = list(history)
    history.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.models.generate_content(
            model=model, contents=history, config=_config()
        )
        content = response.candidates[0].content
        history.append(content)

        calls = [p.function_call for p in content.parts if p.function_call]
        if not calls:
            text = "".join(p.text for p in content.parts if p.text)
            return text, history

        result_parts = [
            types.Part.from_function_response(
                name=call.name, response={"result": dispatch(call.name, dict(call.args))}
            )
            for call in calls
        ]
        history.append(types.Content(role="user", parts=result_parts))

    return "I could not finish within the tool-call limit.", history
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_loop.py -v`
Expected: PASS (2 passed).

- [x] **Step 5: Commit**

```bash
git add soccer-analytics-agent
git commit -m "feat(soccer-agent): hand-written gemini tool loop"
```

---



### Task 6: CLI REPL + end-to-end smoke test

**Files:**

- Create: `soccer-analytics-agent/soccer_agent/cli.py`
- Create: `soccer-analytics-agent/scripts/smoke_test.py`

**Interfaces:**

- Consumes: `loop.run_turn` from Task 5.
- Produces: `python -m soccer_agent.cli` interactive REPL; `scripts/smoke_test.py` non-interactive check.

- [x] **Step 1: Implement the REPL**

`soccer_agent/cli.py`:

```python
"""Terminal REPL for the soccer agent."""

import os

from dotenv import load_dotenv
from google import genai

from soccer_agent.loop import run_turn


def main() -> None:
    load_dotenv()
    client = genai.Client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    history: list = []
    print("Soccer agent ready. Type 'exit' to quit.")
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user or user.lower() in {"exit", "quit"}:
            break
        answer, history = run_turn(client, history, user, model=model)
        print(f"agent> {answer}\n")


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Implement the smoke test**

`scripts/smoke_test.py`:

```python
"""One-shot end-to-end check: real Gemini + real DB."""

import os

from dotenv import load_dotenv
from google import genai

from soccer_agent.loop import run_turn


def main() -> None:
    load_dotenv()
    client = genai.Client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    question = "How many official matches has Argentina played, and how many did it win?"
    answer, history = run_turn(client, [], question, model=model)
    tool_rounds = sum(
        1 for c in history
        if c.role == "user" and any(getattr(p, "function_response", None) for p in c.parts)
    )
    print(f"Q: {question}\nA: {answer}\n(tool rounds: {tool_rounds})")
    assert tool_rounds >= 1, "expected the model to use sql_query at least once"
    assert answer.strip(), "expected a non-empty answer"
    print("SMOKE TEST OK")


if __name__ == "__main__":
    main()
```

- [x] **Step 3: Run the smoke test (needs** `.env` **with credentials and the DB loaded)**

Run: `uv run python scripts/smoke_test.py`
Expected: a grounded answer mentioning Argentina's match/win counts, `tool rounds >= 1`, and `SMOKE TEST OK`.

- [x] **Step 4: Try the REPL interactively**

Run: `uv run python -m soccer_agent.cli`
Ask: "¿Quién le ganó a Brasil en mundiales desde 2000?" — verify the answer cites real matches.

- [x] **Step 5: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: all tests pass (integration tests run because the DB is up).

```bash
git add soccer-analytics-agent
git commit -m "feat(soccer-agent): cli repl and smoke test"
```

---



## Self-review notes

- Spec coverage (phase 0+1 only): Docker+schema ✓ (Task 2), Kaggle load ✓ (Task 3), read-only guarded `sql_query` ✓ (Task 4), hand-written loop with tool dispatch and error-as-tool-result ✓ (Tasks 4–5), CLI REPL ✓ (Task 6). Memory, retrieval, Elo, observability, API, ML, deploy are later phases with their own plans.
- Types consistent: `dispatch(name, args) -> dict`, `run_turn(client, history, user_message, model) -> (str, list)` used identically across tasks.

