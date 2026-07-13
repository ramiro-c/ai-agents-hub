# Soccer Analytics Agent — Phase 5: Observability (Step Trace)

> **For agentic workers:** Implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the agent a memory of its own reasoning. Persist every step of every LLM turn — user input, model reasoning, tool calls, tool results, and final answer — so we can debug what happened, when, and why.

**Architecture:** Add a thin `trace.py` module with a `save_step()` function and an `agent_trace` table. Hook it into the existing `respond()` wrapper and `run_turn()` loop. The trace is a write-only audit log; it never affects the agent's behavior. `run_turn()` stays functionally unchanged — tracing is a side effect.

**Why this matters:** An LLM agent is a black box. When it gives a wrong answer, you need to know: did it call the right tool? Did the tool return bad data? Did the model misinterpret the result? Without a step trace, you're guessing. With it, you replay the turn.

**Tech Stack:** Same as Phase 2–4. Zero new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-10-soccer-analytics-agent-design.md`
**Builds on:** `docs/superpowers/plans/2026-07-12-soccer-agent-phase-4.md`

## What we trace (and what we don't)

A single `respond()` call produces this sequence:

```
1. USER_MESSAGE       "Who won the 2022 World Cup?"
2. TOOL_CALL          model calls sql_query("SELECT ...")
3. TOOL_RESULT        {"columns": [...], "rows": [[...]]}
4. MODEL_RESPONSE     "Argentina won the 2022 World Cup..."
5. MEMORY_STORE       persisted to working, episodic, semantic
```

We trace steps 1-4. Step 5 (memory persistence) is not traced — it's deterministic storage, not reasoning.

If the model makes multiple tool calls in one turn (parallel or sequential), each gets its own step. The `step_number` increments within the turn.

## Schema

```sql
CREATE TABLE IF NOT EXISTS agent_trace (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id BIGINT NOT NULL,        -- increments each respond() call
    step_number INT NOT NULL,       -- 1, 2, 3... within a turn
    step_type TEXT NOT NULL,        -- user_message, tool_call, tool_result, model_response
    content JSONB NOT NULL,         -- the actual data (message text, tool args, tool result, etc.)
    model TEXT,                     -- which model processed this turn (gemini-2.5-flash, etc.)
    latency_ms INT,                 -- how long this step took (NULL for user_message)
    tool_name TEXT,                 -- only for tool_call / tool_result
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_trace_session ON agent_trace (session_id, turn_id, step_number);
```

### content JSONB shapes

```jsonc
// user_message
{"text": "Who won the 2022 World Cup?"}

// tool_call
{"tool": "sql_query", "args": {"sql": "SELECT winner FROM ..."}}

// tool_result
{"tool": "sql_query", "result": {"columns": ["winner"], "rows": [["Argentina"]]}}

// model_response
{"text": "Argentina won the 2022 World Cup final against France.", "turn_final": true}
```

## Task 1: trace.py module

**File:** `soccer_agent/trace.py`

Thin storage-only module. No genai, no business logic.

```python
"""Persistent step trace for agent observability."""

import json
import time

from soccer_agent import db


def save_step(
    session_id: str,
    turn_id: int,
    step_number: int,
    step_type: str,
    content: dict,
    *,
    model: str | None = None,
    latency_ms: int | None = None,
    tool_name: str | None = None,
) -> None:
    """Persist one reasoning step to the trace table.

    Args:
        session_id: REPL session identifier
        turn_id: Monotonic counter, increments each respond() call
        step_number: 1-based step index within this turn
        step_type: 'user_message', 'tool_call', 'tool_result', 'model_response'
        content: The step's payload (text, args, result, etc.)
        model: LLM model name (for model_response steps)
        latency_ms: Step duration in milliseconds
        tool_name: Tool name (for tool_call / tool_result steps)
    """
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO agent_trace
               (session_id, turn_id, step_number, step_type,
                content, model, latency_ms, tool_name)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                session_id,
                turn_id,
                step_number,
                step_type,
                json.dumps(content),
                model,
                latency_ms,
                tool_name,
            ),
        )


def get_turn_trace(session_id: str, turn_id: int) -> list[dict]:
    """Return all steps for a specific turn, ordered by step_number.

    Returns a list of dicts ready for display or debugging.
    """
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT step_number, step_type, content, model,
                      latency_ms, tool_name, created_at
               FROM agent_trace
               WHERE session_id = %s AND turn_id = %s
               ORDER BY step_number""",
            (session_id, turn_id),
        ).fetchall()

    return [
        {
            "step": r[0],
            "type": r[1],
            "content": r[2],  # already JSON from psycopg
            "model": r[3],
            "latency_ms": r[4],
            "tool_name": r[5],
            "timestamp": str(r[6]),
        }
        for r in rows
    ]


def get_session_trace(session_id: str, limit: int = 50) -> list[dict]:
    """Return the last N turns for a session, summarized.

    Each turn is summarized as: turn_id, user_message (first 120 chars),
    tool count, final response length, total latency.
    """
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT turn_id,
                      MIN(created_at) AS started_at,
                      MAX(created_at) AS ended_at,
                      COUNT(*) FILTER (WHERE step_type = 'tool_call') AS tool_calls,
                      COUNT(*) FILTER (WHERE step_type = 'tool_result') AS tool_results,
                      SUM(latency_ms) AS total_latency_ms,
                      MAX(CASE WHEN step_type = 'user_message'
                          THEN content->>'text' END) AS user_message,
                      MAX(CASE WHEN step_type = 'model_response'
                          THEN content->>'text' END) AS model_response
               FROM agent_trace
               WHERE session_id = %s
               GROUP BY turn_id
               ORDER BY turn_id DESC
               LIMIT %s""",
            (session_id, limit),
        ).fetchall()

    return [
        {
            "turn": r[0],
            "started": str(r[1]),
            "ended": str(r[2]),
            "tool_calls": r[3],
            "tool_results": r[4],
            "latency_ms": r[5],
            "user_message": (r[6] or "")[:120],
            "model_response": (r[7] or "")[:120],
        }
        for r in rows
    ]
```

**Design notes:**
- `latency_ms` is measured by the caller (respond/run_turn), not by trace.py. Trace is a pure storage layer.
- `turn_id` is a monotonic counter managed by `respond()` — stored in a session-level variable, NOT derived from the DB.
- `content` is stored as `json.dumps()` but psycopg's native JSONB handling means it comes back as a Python dict — no manual parsing needed.

- [ ] **Step 1: Create `soccer_agent/trace.py`**

## Task 2: Add agent_trace to schema

**File:** `soccer-analytics-agent/db/schema.sql`

Append the `agent_trace` table definition (from the Schema section above) to the end of `schema.sql`.

- [ ] **Step 2a: Add agent_trace table to schema.sql**
- [ ] **Step 2b: Apply schema:** `uv run python -c "from soccer_agent import db; db.apply_schema()"`

**Verify:** `docker compose exec db psql -U soccer -d soccer -c "\d agent_trace"` shows the table with all columns.

## Task 3: Wire tracing into respond() and run_turn()

This is the main integration task. We hook `save_step()` at three points:

1. **Before `run_turn()`** — save `user_message` step
2. **Inside `run_turn()`** — save `tool_call` and `tool_result` steps (at the dispatch boundary)
3. **After `run_turn()`** — save `model_response` step

### 3a. Modify `chat.py` — respond()

The `respond()` function gets a `_turn_counter` (or we pass `turn_id` explicitly).

```python
# In respond(), add:
import time
from soccer_agent import trace

_turn_counters: dict[str, int] = {}  # session_id -> next turn_id

def respond(client, session_id: str, user_message: str, *, model: str = "gemini-2.5-flash") -> str:
    from soccer_agent import memory, trace
    import time

    # --- turn counter ---
    turn_id = _turn_counters.get(session_id, 0) + 1
    _turn_counters[session_id] = turn_id

    step = 0

    # --- step 1: user message ---
    step += 1
    trace.save_step(session_id, turn_id, step, "user_message",
                    {"text": user_message}, model=model)

    # --- seed working memory ---
    prior = memory.load_working(session_id)

    # --- episodic recall & grounding ---
    episodes = memory.recall_episodes(session_id, user_message)
    grounding = ""
    if episodes:
        grounding = (
            "Relevant past conversations with this user:\n" +
            "\n".join(
                f"- Q: {e['user_message']}\n  A: {e['agent_response']}"
                for e in reversed(episodes)
            )
        )
        user_message = f"User: {user_message}\n\n---\n\n{grounding}\n\n---\n\nRespond to the user's message above."

    # --- history from prior turns ---
    history = []
    for role, content in prior:
        history.append({"role": role, "parts": [{"text": content}]})

    history.append({"role": "user", "parts": [{"text": user_message}]})

    # --- run the agent loop (run_turn handles trace steps 2-N internally) ---
    t0 = time.monotonic()
    # We need to pass session_id, turn_id, step counter, model to run_turn
    # run_turn will increment step and call trace.save_step for tool calls/results
    # and return the final model text + updated step number + final text
    final_text, final_step = run_turn(
        client, history, model=model,
        session_id=session_id, turn_id=turn_id, step=step,
    )
    elapsed = int((time.monotonic() - t0) * 1000)

    # --- step N+1: model_response ---
    final_step += 1
    trace.save_step(
        session_id, turn_id, final_step, "model_response",
        {"text": final_text, "turn_final": True},
        model=model, latency_ms=elapsed,
    )

    # --- persist to memory (unchanged) ---
    memory.append_working(session_id, "user", user_message.split("\n---\n")[0] if grounding else user_message)
    memory.append_working(session_id, "model", final_text)
    memory.save_episode(session_id, user_message.split("\n---\n")[0] if grounding else user_message, final_text)

    return final_text
```

Wait, this changes `run_turn()` to return `(text, step)`. That's a signature change.

### Better approach: minimal signature change

Instead of modifying `run_turn()` to return step numbers, let's keep the tracing logic self-contained within `run_turn()` and just pass the trace context as optional parameters.

```python
# In run_turn(), add optional trace params:
def run_turn(
    client,
    history: list[dict],
    *,
    model: str = "gemini-2.5-flash",
    session_id: str | None = None,   # NEW: optional — for tracing
    turn_id: int | None = None,      # NEW: optional — for tracing
    step: int = 0,                   # NEW: optional — starting step number
) -> tuple[str, int]:                # CHANGED: returns (text, final_step)
```

Inside `run_turn()`, at the dispatch point:

```python
# Before calling dispatch():
if session_id is not None and turn_id is not None:
    step += 1
    trace.save_step(
        session_id, turn_id, step, "tool_call",
        {"tool": name, "args": args},
        model=model, tool_name=name,
    )

result = dispatch(name, args)

if session_id is not None and turn_id is not None:
    step += 1
    trace.save_step(
        session_id, turn_id, step, "tool_result",
        {"tool": name, "result": result},
        model=model, tool_name=name,
    )
```

This way:
- Existing code that calls `run_turn(client, history)` still works (returns `(text, step)`)
- `respond()` passes trace params and receives the final step count
- The `step` counter flows through the loop naturally

- [ ] **Step 3a: Modify `run_turn()` in `loop.py`** — accept optional `session_id`, `turn_id`, `step` params; trace tool calls/results; return `(text, final_step)` tuple
- [ ] **Step 3b: Modify `respond()` in `chat.py`** — manage turn counter, trace user_message and model_response, pass trace context to `run_turn()`
- [ ] **Step 3c: Update `cli.py`** if it calls `run_turn()` directly (check — it calls `respond()` now, so probably no change needed)

**Verify:** Run the CLI, have a short conversation, then `docker compose exec db psql -U soccer -d soccer -c "SELECT turn_id, step_number, step_type, tool_name FROM agent_trace ORDER BY id;"` shows traced steps.

## Task 4: Tests

**Files:** `tests/test_trace.py`, `tests/test_chat.py` (amend)

### 4a. Trace unit tests (`tests/test_trace.py`)

```python
"""Unit tests for trace persistence."""
import pytest
from soccer_agent import trace

# conftest.py already has @requires_db and @pytest.mark.integration


@pytest.mark.integration
@pytest.mark.usefixtures("db_session")
def test_save_and_retrieve_turn():
    """Save steps for one turn and retrieve them in order."""
    sid, tid = "trace-test", 1

    trace.save_step(sid, tid, 1, "user_message", {"text": "hello"})
    trace.save_step(sid, tid, 2, "tool_call",
                    {"tool": "sql_query", "args": {"sql": "SELECT 1"}},
                    tool_name="sql_query")
    trace.save_step(sid, tid, 3, "tool_result",
                    {"tool": "sql_query", "result": {"rows": [[1]]}},
                    tool_name="sql_query")
    trace.save_step(sid, tid, 4, "model_response",
                    {"text": "The answer is 1."},
                    model="test-model", latency_ms=500)

    steps = trace.get_turn_trace(sid, tid)
    assert len(steps) == 4
    assert steps[0]["type"] == "user_message"
    assert steps[1]["type"] == "tool_call"
    assert steps[2]["type"] == "tool_result"
    assert steps[3]["type"] == "model_response"
    assert steps[3]["latency_ms"] == 500


@pytest.mark.integration
@pytest.mark.usefixtures("db_session")
def test_get_session_trace_summarizes_turns():
    """Session trace returns one summary row per turn."""
    trace.save_step("sum-test", 1, 1, "user_message", {"text": "q1"})
    trace.save_step("sum-test", 1, 2, "model_response", {"text": "a1"})
    trace.save_step("sum-test", 2, 1, "user_message", {"text": "q2"})
    trace.save_step("sum-test", 2, 2, "tool_call",
                    {"tool": "recall", "args": {}}, tool_name="recall")
    trace.save_step("sum-test", 2, 3, "tool_result",
                    {"tool": "recall", "result": {}}, tool_name="recall")
    trace.save_step("sum-test", 2, 4, "model_response", {"text": "a2"})

    summary = trace.get_session_trace("sum-test")
    assert len(summary) == 2
    t1, t2 = summary[1], summary[0]  # most recent first
    assert t1["turn"] == 1
    assert t2["turn"] == 2
    assert t2["tool_calls"] == 1
    assert t2["tool_results"] == 1
```

- [ ] **Step 4a: Create `tests/test_trace.py`**

### 4b. Amend chat tests (`tests/test_chat.py`)

Verify that `respond()` traces correctly by checking the trace table after a call.

```python
@pytest.mark.integration
@requires_db
def test_respond_traces_user_message_and_response(monkeypatch):
    """respond() should save trace steps."""
    from soccer_agent import chat, trace

    saved = {"working": [], "episodes": []}
    monkeypatch.setattr(chat.memory, "load_working",
                        lambda s, limit=10: [])
    monkeypatch.setattr(chat.memory, "recall_episodes",
                        lambda s, q, k=3: [])
    monkeypatch.setattr(
        chat.memory, "append_working",
        lambda s, r, c: saved["working"].append((r, c)))
    monkeypatch.setattr(
        chat.memory, "save_episode",
        lambda s, u, a: saved["episodes"].append((u, a)))

    fake = SimpleNamespace(models=FakeModels("Hello back!"))
    chat._turn_counters.clear()  # reset for test
    answer = chat.respond(fake, "trace-sess", "Hi!", model="test")

    assert answer == "Hello back!"

    # Verify trace
    steps = trace.get_turn_trace("trace-sess", 1)
    assert len(steps) >= 2
    types = [s["type"] for s in steps]
    assert "user_message" in types
    assert "model_response" in types
```

**Note:** The existing `test_respond_injects_episodic_grounding_and_persists` test may need updating if the `respond()` signature or behavior changes. Check and fix if needed.

- [ ] **Step 4b: Amend `tests/test_chat.py`** — add trace test, fix existing test if needed

## Verification

- [ ] **Step 5: Run the full suite and commit**

```bash
uv run pytest -q
```

```bash
git add soccer-analytics-agent docs/
git commit -m "feat(soccer-agent): per-turn step trace for observability (Phase 5)"
```

## Smoke test

After committing, run the CLI and check the trace:

```bash
uv run python -m soccer_agent.cli
# Chat: "What's Argentina's Elo?"
# Chat: "Show me the last 3 Brazil matches"
# exit
```

```bash
docker compose exec db psql -U soccer -d soccer -c "
  SELECT turn_id, step_number, step_type, tool_name,
         substring(content::text, 1, 80) AS preview
  FROM agent_trace ORDER BY id;
"
```

---

## Self-review notes

- Spec coverage (Phase 5): step trace ✓, per-turn observability ✓, debug replay ✓.
- `run_turn()`'s trace params are optional — existing callers work unchanged, tracing is opt-in by passing `session_id`.
- Trace is write-only from the agent's perspective. Reading the trace is a debugging/CLI operation, never part of the agent loop.
- `turn_id` is managed in `chat.py`, NOT derived from the DB. This avoids a race between multiple sessions and keeps the counter simple.
- The `_turn_counters` dict is process-local. If we deploy on Cloud Run with multiple instances, each instance has its own counter. For v1 REPL usage, this is fine. Phase 8 (deploy) will need to revisit this.
- Tool latency is not individually measured in v1 — we trace only the full turn latency. Per-tool timing can be added later by wrapping `dispatch()` with a timer.
- Deferred to later phases: trace visualization UI, trace cleanup/retention policies, streaming trace (real-time step updates to a frontend).
