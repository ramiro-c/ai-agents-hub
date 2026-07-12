# Soccer Analytics Agent — Phase 2: Three-Tier Memory

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the agent three distinct kinds of memory backed by pgvector, so it remembers the current conversation, recalls relevant past moments, and can store/retrieve durable facts.

**Architecture:** Add a local embeddings module (`sentence-transformers`, `all-MiniLM-L6-v2`, 384 dims), three memory tables in Postgres, a storage-only `memory.py` module, two new agent tools (`remember`/`recall`), and a thin `respond()` wrapper that wires memory around the existing pure `run_turn` loop. `run_turn` stays untouched and framework-free.

**Tech Stack:** Same as Phase 0+1, plus `sentence-transformers` and `numpy`.

**Spec:** `docs/superpowers/specs/2026-07-10-soccer-analytics-agent-design.md`
**Builds on:** `docs/superpowers/plans/2026-07-11-soccer-agent-phase-0-1.md`

## The three tiers (read this first — it's the whole point)

| Tier | Question it answers | Scope | Retrieval | How it's wired |
|---|---|---|---|---|
| **Working** | "What are we talking about right now?" | This session | Recency (last N turns) | Auto-seeded into `history` by `respond()` |
| **Episodic** | "Have we touched something like this before?" | This session | Similarity (vector) | Auto-recalled and injected as grounding by `respond()` |
| **Semantic** | "What durable facts do I know?" | Global | Similarity (vector) | Model-controlled via `remember`/`recall` tools |

The distinction that trips people up: **episodic is events ("on turn 5 the user asked about Messi"), semantic is distilled knowledge ("the user supports Argentina")**. Working is just short-term recency. Each tier has a different scope, a different retrieval strategy, and a different owner (the runtime vs. the model). Keeping them separate is the lesson.

## Global Constraints

- Everything from Phase 0+1 applies (Python 3.12+, `uv` only, English, read-only `sql_query`, `DATABASE_URL`/`GEMINI_MODEL` env, conventional commits, run from `soccer-analytics-agent/`).
- Embedding model: `all-MiniLM-L6-v2`, 384 dims, normalized (so cosine = inner product).
- Vectors are sent to Postgres as string literals cast with `::vector` — no extra driver package.
- `memory.py` is storage-only: it must NOT import `google.genai`. Type conversion to genai `Content` lives in `chat.py`.
- `run_turn` signature and behavior stay exactly as in Phase 0+1.

## Testing Approach

Behavior-first (same as Phase 0+1): implement first, then run the behavior tests included in each task. Skip the "verify it fails" steps. Unit tests inject a fake embedder so they're fast and offline; one integration test per task marked `@pytest.mark.integration` exercises the real model/DB.

---

### Task 1: Embeddings module

**Files:**
- Modify: `soccer-analytics-agent/pyproject.toml` (add deps)
- Create: `soccer-analytics-agent/soccer_agent/embeddings.py`
- Test: `soccer-analytics-agent/tests/test_embeddings.py`

**Interfaces:**
- Produces: `embeddings.embed(text: str) -> list[float]` (length 384, normalized) and `embeddings.DIM = 384`.

- [ ] **Step 1: Add dependencies**

In `pyproject.toml`, add to `dependencies`:

```toml
    "sentence-transformers>=3.0",
    "numpy>=1.26",
```

Run: `uv sync`
Expected: resolves and installs (pulls torch; first run is slow).

- [ ] **Step 2: Implement embeddings.py**

`soccer_agent/embeddings.py`:

```python
"""Local text embeddings via sentence-transformers (all-MiniLM-L6-v2, 384 dims)."""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
DIM = 384


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    """Load the model once per process (first call downloads it)."""
    return SentenceTransformer(MODEL_NAME)


def embed(text: str) -> list[float]:
    """Return a 384-dim L2-normalized embedding for the given text."""
    vec = _model().encode(text, normalize_embeddings=True)
    return vec.tolist()
```

- [ ] **Step 3: Write the behavior test**

`tests/test_embeddings.py`:

```python
import math

import pytest


@pytest.mark.integration
def test_embed_dimension_and_normalization():
    from soccer_agent.embeddings import DIM, embed

    vec = embed("Argentina won the World Cup")
    assert len(vec) == DIM
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-3  # normalized


@pytest.mark.integration
def test_embed_similar_texts_closer_than_unrelated():
    from soccer_agent.embeddings import embed

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b))

    goal = embed("Messi scored a goal")
    similar = embed("Messi found the net")
    unrelated = embed("The stadium roof needs repairs")
    assert cosine(goal, similar) > cosine(goal, unrelated)
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_embeddings.py -v`
Expected: PASS (first run downloads the model, ~90 MB).

- [ ] **Step 5: Commit**

```bash
git add soccer-analytics-agent
git commit -m "feat(soccer-agent): local sentence-transformers embeddings"
```

---

### Task 2: Memory schema

**Files:**
- Modify: `soccer-analytics-agent/db/schema.sql`

**Interfaces:**
- Produces: tables `working_memory`, `episodic_memory`, `semantic_memory` with `vector(384)` columns and cosine HNSW indexes. `db.apply_schema()` already applies this file idempotently.

- [ ] **Step 1: Append the memory tables to schema.sql**

Add to the end of `db/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS working_memory (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_working_session
    ON working_memory (session_id, created_at);

CREATE TABLE IF NOT EXISTS episodic_memory (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_message TEXT NOT NULL,
    agent_response TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_episodic_embedding
    ON episodic_memory USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS semantic_memory (
    id BIGSERIAL PRIMARY KEY,
    fact TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_semantic_embedding
    ON semantic_memory USING hnsw (embedding vector_cosine_ops);
```

- [ ] **Step 2: Apply the schema**

Run: `uv run python -c "from soccer_agent import db; db.apply_schema(); print('applied')"`
Expected: `applied`.

- [ ] **Step 3: Verify the tables and vector columns exist**

Run:
```bash
uv run python -c "
from soccer_agent import db
rows = db.connect().execute(
    \"SELECT table_name FROM information_schema.tables \"
    \"WHERE table_name LIKE '%_memory'\"
).fetchall()
print(sorted(r[0] for r in rows))
"
```
Expected: `['episodic_memory', 'semantic_memory', 'working_memory']`.

- [ ] **Step 4: Commit**

```bash
git add soccer-analytics-agent
git commit -m "feat(soccer-agent): memory schema (working/episodic/semantic)"
```

---

### Task 3: Memory module (storage layer)

**Files:**
- Create: `soccer-analytics-agent/soccer_agent/memory.py`
- Test: `soccer-analytics-agent/tests/test_memory.py`

**Interfaces:**
- Consumes: `db.connect()` (Task 2), `embeddings.embed` (Task 1).
- Produces (all storage-only, no genai imports):
  - `append_working(session_id: str, role: str, content: str) -> None`
  - `load_working(session_id: str, limit: int = 10) -> list[tuple[str, str]]` — `(role, content)` oldest→newest
  - `save_episode(session_id: str, user_message: str, agent_response: str) -> None`
  - `recall_episodes(session_id: str, query: str, k: int = 3) -> list[dict]` — `{"user_message", "agent_response", "score"}`
  - `remember_fact(fact: str) -> None`
  - `search_semantic(query: str, k: int = 3) -> list[dict]` — `{"fact", "score"}`

- [ ] **Step 1: Implement memory.py**

`soccer_agent/memory.py`:

```python
"""Storage layer for the three memory tiers. No genai imports — storage only."""

from soccer_agent import db
from soccer_agent.embeddings import embed


def _vec(values: list[float]) -> str:
    """Render an embedding as a pgvector string literal."""
    return "[" + ",".join(repr(x) for x in values) + "]"


# --- Working memory: recency, session-scoped ---

def append_working(session_id: str, role: str, content: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO working_memory (session_id, role, content) VALUES (%s, %s, %s)",
            (session_id, role, content),
        )


def load_working(session_id: str, limit: int = 10) -> list[tuple[str, str]]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM working_memory WHERE session_id = %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (session_id, limit),
        ).fetchall()
    return [(r[0], r[1]) for r in reversed(rows)]  # oldest -> newest


# --- Episodic memory: similarity, session-scoped ---

def save_episode(session_id: str, user_message: str, agent_response: str) -> None:
    vec = _vec(embed(f"{user_message}\n{agent_response}"))
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO episodic_memory "
            "(session_id, user_message, agent_response, embedding) "
            "VALUES (%s, %s, %s, %s::vector)",
            (session_id, user_message, agent_response, vec),
        )


def recall_episodes(session_id: str, query: str, k: int = 3) -> list[dict]:
    vec = _vec(embed(query))
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT user_message, agent_response, 1 - (embedding <=> %s::vector) AS score "
            "FROM episodic_memory WHERE session_id = %s "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (vec, session_id, vec, k),
        ).fetchall()
    return [{"user_message": r[0], "agent_response": r[1], "score": float(r[2])} for r in rows]


# --- Semantic memory: similarity, global facts ---

def remember_fact(fact: str) -> None:
    vec = _vec(embed(fact))
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO semantic_memory (fact, embedding) VALUES (%s, %s::vector)",
            (fact, vec),
        )


def search_semantic(query: str, k: int = 3) -> list[dict]:
    vec = _vec(embed(query))
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT fact, 1 - (embedding <=> %s::vector) AS score "
            "FROM semantic_memory ORDER BY embedding <=> %s::vector LIMIT %s",
            (vec, vec, k),
        ).fetchall()
    return [{"fact": r[0], "score": float(r[1])} for r in rows]
```

- [ ] **Step 2: Write the behavior test (real DB, real embedder — the payoff is seeing recall work)**

`tests/test_memory.py`:

```python
import pytest

from soccer_agent import memory
from tests.test_db import requires_db


@pytest.mark.integration
@requires_db
def test_working_memory_roundtrip_is_ordered():
    from soccer_agent import db

    session = "test-working"
    with db.connect() as conn:
        conn.execute("DELETE FROM working_memory WHERE session_id = %s", (session,))
    memory.append_working(session, "user", "first")
    memory.append_working(session, "model", "second")
    assert memory.load_working(session) == [("user", "first"), ("model", "second")]


@pytest.mark.integration
@requires_db
def test_semantic_recall_ranks_relevant_fact_first():
    from soccer_agent import db

    with db.connect() as conn:
        conn.execute("DELETE FROM semantic_memory")
    memory.remember_fact("The user supports Argentina")
    memory.remember_fact("The office coffee machine is broken")
    top = memory.search_semantic("which national team does the user like?", k=1)
    assert top[0]["fact"] == "The user supports Argentina"


@pytest.mark.integration
@requires_db
def test_episodic_recall_finds_similar_past_turn():
    from soccer_agent import db

    session = "test-episodic"
    with db.connect() as conn:
        conn.execute("DELETE FROM episodic_memory WHERE session_id = %s", (session,))
    memory.save_episode(session, "Who won the 1986 World Cup?", "Argentina, led by Maradona.")
    memory.save_episode(session, "What's the offside rule?", "A player is offside if...")
    hits = memory.recall_episodes(session, "tell me about Maradona's World Cup", k=1)
    assert "Maradona" in hits[0]["agent_response"]
```

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/test_memory.py -v`
Expected: PASS (3 passed).

- [ ] **Step 4: Commit**

```bash
git add soccer-analytics-agent
git commit -m "feat(soccer-agent): three-tier memory storage layer"
```

---

### Task 4: `remember` and `recall` tools

**Files:**
- Modify: `soccer-analytics-agent/soccer_agent/tools.py`
- Test: `soccer-analytics-agent/tests/test_tools.py` (add cases)

**Interfaces:**
- Consumes: `memory.remember_fact`, `memory.search_semantic` (Task 3).
- Produces: two new entries in `TOOL_DECLARATIONS` and `_HANDLERS`:
  - `remember(fact)` → `{"status": "remembered"}`
  - `recall(query)` → `{"facts": [{"fact", "score"}, ...]}`

- [ ] **Step 1: Add the tools to tools.py**

Add near the top of `tools.py` (after the existing `from soccer_agent import db`):

```python
from soccer_agent import memory
```

Add these two functions (after `sql_query`):

```python
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
```

Add two entries to the `TOOL_DECLARATIONS` list:

```python
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
                "fact": {"type": "string", "description": "The fact to store, as a short sentence."}
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
```

Extend `_HANDLERS`:

```python
_HANDLERS = {
    "sql_query": lambda args: sql_query(args["sql"]),
    "remember": lambda args: remember(args["fact"]),
    "recall": lambda args: recall(args["query"]),
}
```

- [ ] **Step 2: Add behavior tests to test_tools.py**

Append to `tests/test_tools.py`:

```python
@pytest.mark.integration
@requires_db
def test_remember_then_recall_via_dispatch():
    from soccer_agent import db

    with db.connect() as conn:
        conn.execute("DELETE FROM semantic_memory")
    assert dispatch("remember", {"fact": "The user is a Boca Juniors fan"}) == {
        "status": "remembered"
    }
    result = dispatch("recall", {"query": "what club does the user follow?"})
    assert any("Boca" in f["fact"] for f in result["facts"])
```

- [ ] **Step 3: Run the tests**

Run: `uv run pytest tests/test_tools.py -v`
Expected: PASS (all, including the new case).

- [ ] **Step 4: Commit**

```bash
git add soccer-analytics-agent
git commit -m "feat(soccer-agent): remember/recall semantic-memory tools"
```

---

### Task 5: `respond()` — wire working + episodic memory around the loop

**Files:**
- Create: `soccer-analytics-agent/soccer_agent/chat.py`
- Modify: `soccer-analytics-agent/soccer_agent/cli.py`
- Test: `soccer-analytics-agent/tests/test_chat.py`

**Interfaces:**
- Consumes: `loop.run_turn` (Phase 0+1), `memory.*` (Task 3), `google.genai.types`.
- Produces: `chat.respond(client, session_id: str, user_message: str, model: str) -> str`.

**Design:** `run_turn` stays pure. `respond()` is the memory-aware wrapper: it seeds the loop with working memory (recency), injects episodic recall (similarity) as grounding, runs the turn, then persists the new turn to both working and episodic memory. Semantic memory is handled by the model itself through the Task 4 tools.

- [ ] **Step 1: Implement chat.py**

`soccer_agent/chat.py`:

```python
"""Memory-aware turn wrapper around the pure run_turn loop."""

from google.genai import types

from soccer_agent import memory
from soccer_agent.loop import run_turn


def _to_history(turns: list[tuple[str, str]]) -> list:
    """Convert stored (role, content) working-memory turns into genai Content."""
    return [
        types.Content(role=role, parts=[types.Part(text=content)])
        for role, content in turns
    ]


def _augment(user_message: str, episodes: list[dict]) -> str:
    """Prepend relevant past episodes to the user message as grounding context."""
    if not episodes:
        return user_message
    lines = "\n".join(
        f"- Earlier you asked: {e['user_message']!r} -> {e['agent_response']!r}"
        for e in episodes
    )
    return (
        f"Relevant context from earlier in this session:\n{lines}\n\n"
        f"Current question: {user_message}"
    )


def respond(client, session_id: str, user_message: str, model: str) -> str:
    """Run one memory-aware turn: seed + ground -> answer -> persist."""
    prior = _to_history(memory.load_working(session_id))
    episodes = memory.recall_episodes(session_id, user_message, k=3)
    augmented = _augment(user_message, episodes)

    answer, _ = run_turn(client, prior, augmented, model=model)

    memory.append_working(session_id, "user", user_message)  # store raw, not augmented
    memory.append_working(session_id, "model", answer)
    memory.save_episode(session_id, user_message, answer)
    return answer
```

- [ ] **Step 2: Update the CLI to use respond() with a session**

Replace the body of `soccer_agent/cli.py` `main()` loop with a session-based version:

```python
"""Terminal REPL for the soccer agent."""

import os
import uuid

from dotenv import load_dotenv
from google import genai

from soccer_agent.chat import respond


def main() -> None:
    load_dotenv()
    client = genai.Client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    session_id = f"cli-{uuid.uuid4().hex[:8]}"
    print(f"Soccer agent ready (session {session_id}). Type 'exit' to quit.")
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user or user.lower() in {"exit", "quit"}:
            break
        answer = respond(client, session_id, user, model=model)
        print(f"agent> {answer}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write the behavior test (fake client + fake memory, offline)**

`tests/test_chat.py`:

```python
from types import SimpleNamespace

from google.genai import types

from soccer_agent import chat


def _answer(text):
    content = types.Content(role="model", parts=[types.Part(text=text)])
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)])


class FakeModels:
    def __init__(self, text):
        self._text = text
        self.last_contents = None

    def generate_content(self, *, model, contents, config):
        self.last_contents = contents
        return _answer(self._text)


def test_respond_injects_episodic_grounding_and_persists(monkeypatch):
    saved = {"working": [], "episodes": []}
    monkeypatch.setattr(chat.memory, "load_working", lambda s, limit=10: [("user", "hi"), ("model", "hello")])
    monkeypatch.setattr(
        chat.memory, "recall_episodes",
        lambda s, q, k=3: [{"user_message": "Who is Messi?", "agent_response": "An Argentine forward.", "score": 0.9}],
    )
    monkeypatch.setattr(chat.memory, "append_working", lambda s, r, c: saved["working"].append((r, c)))
    monkeypatch.setattr(chat.memory, "save_episode", lambda s, u, a: saved["episodes"].append((u, a)))

    fake = SimpleNamespace(models=FakeModels("He plays for Inter Miami."))
    answer = chat.respond(fake, "sess-1", "Where does he play now?", model="test")

    assert answer == "He plays for Inter Miami."
    # working memory was seeded (2 prior turns) + current user turn = 3 contents sent
    assert len(fake.models.last_contents) == 3
    # episodic grounding was injected into the current user message
    injected = fake.models.last_contents[-1].parts[0].text
    assert "Messi" in injected and "Where does he play now?" in injected
    # the raw (not augmented) turn was persisted to both tiers
    assert saved["working"] == [("user", "Where does he play now?"), ("model", "He plays for Inter Miami.")]
    assert saved["episodes"] == [("Where does he play now?", "He plays for Inter Miami.")]
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_chat.py -v`
Expected: PASS.

- [ ] **Step 5: Verify memory end-to-end in the REPL**

Run: `uv run python -m soccer_agent.cli`
- Say: "Recordá que soy hincha de Racing." (the model should call `remember`)
- Then: "¿De qué equipo soy hincha?" (the model should answer Racing, via `recall` or working memory)
- Exit, restart the REPL (new session), ask again about your club → it should still find the fact via semantic `recall` (semantic memory is global, survives sessions), even though working memory is empty.

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest -q`
Expected: all pass (unit offline + integration with DB up).

```bash
git add soccer-analytics-agent
git commit -m "feat(soccer-agent): memory-aware respond() wrapper and session-based CLI"
```

---

## Self-review notes

- Spec coverage (Phase 2): working/episodic/semantic memory ✓ (Tasks 2–3, 5), `remember`/`recall` tools ✓ (Task 4), embeddings ✓ (Task 1). Loop stays pure; memory wired via `respond()` (Task 5).
- Type consistency: `embed -> list[float]`; memory functions return plain tuples/dicts (no genai coupling); `respond(client, session_id, user_message, model) -> str`; `run_turn` unchanged from Phase 0+1.
- Tier ownership is explicit: working+episodic owned by `respond()` (has `session_id`), semantic owned by the model (via tools, no session needed) — this is why `recall`/`remember` don't need session context threaded through `dispatch`.
- Deferred to later phases: `vector_search` as a distinct semantic-only tool and hybrid retrieval land in Phase 3; hardening the loop (empty candidates / None parts) and persistent step tracing land in Phase 5.
