# Challenge Detection Production Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Challenge-nudge only a previous answer, and score the raw user utterance rather than the memory-augmented prompt.

**Architecture:** `run_turn_events` snapshots whether incoming history already contains a model turn *before* appending the current user message (the current model attempt is appended later and must not count). Challenge classification and grounding checks use an optional `classify_as` text that `chat.py` sets to the raw utterance while still sending the augmented prompt to Gemini. Working memory stays text-only; do not reconstruct `function_call` parts.

**Tech Stack:** Python 3.12, `uv`, pytest, `google.genai` types, existing FakeModels test doubles.

## Global Constraints

- Python 3.12+, `uv` only. Run tests with `uv run pytest ...` from `soccer-analytics-agent/`.
- English for all code, comments, docstrings, and docs.
- Behavior-first testing per CONTEXT.md: implement, then run behavior tests. Do not require a red-green TDD ritual. Tests must assert meaningful outcomes (nudge present/absent, call count), not "non-empty".
- Do **not** change grounding-nudge behavior (`_needs_grounding` still runs on first-turn factual questions with empty history).
- Do **not** persist tool calls into working memory. `chat.py` `_to_history` stays text-only `(role, content)` pairs.
- The challenge gate is **prior `role=="model"` in the incoming `history` argument**, snapshotted at turn start. Do **not** require `function_call` / `function_response` parts — production history from `chat.py` never has them, and requiring them would silently disable the challenge nudge in production.
- Snapshot the gate **before** `history.append` of the current user message. By the time the challenge check runs, the current model attempt is already in `history` and would make a naive scan always true.
- Leave `_is_challenge` layers unchanged: lexical `_CHALLENGE_HINTS` first, then MiniLM cosine vs exemplars at threshold `0.80`. Do not add numpy, FastAPI MiniLM warmup, or merge the two existing `run_turn` challenge e2e tests.
- Conventional commits: `fix(agent): ...`. Work only under `soccer-analytics-agent/`. Do not commit `.gitignore` or secrets.
- `classify_as` is keyword-only on `run_turn` and `run_turn_events`. When omitted (`None`), classifiers use `user_message` (existing tests keep working).

---

## File Structure

- Modify: `soccer-analytics-agent/soccer_agent/loop.py` — `_has_prior_model_turn`, snapshot, `classify_as` passthrough
- Modify: `soccer-analytics-agent/soccer_agent/chat.py` — pass `classify_as=user_message` into `run_turn` / `run_turn_events`
- Modify: `soccer-analytics-agent/tests/test_loop.py` — gate tests + `classify_as` tests
- Modify: `soccer-analytics-agent/tests/test_chat.py` — assert raw utterance is what gets classified

---

### Task 1: Gate challenge nudge on a prior model turn

**Files:**
- Modify: `soccer-analytics-agent/soccer_agent/loop.py` (`run_turn_events`, add `_has_prior_model_turn` next to `_is_challenge`)
- Test: `soccer-analytics-agent/tests/test_loop.py`

**Interfaces:**
- Consumes: existing `_is_challenge(message: str) -> bool`, `CHALLENGE_REASK`, `run_turn(...)`
- Produces: `_has_prior_model_turn(history: list) -> bool`; `run_turn_events` reads a boolean snapshotted at turn start. No new public parameters yet (`classify_as` is Task 2).

- [ ] **Step 1: Add the failing tests** in `tests/test_loop.py` after `test_run_turn_challenge_nudge_never_fires_for_chit_chat`.

Reuse existing helpers `_response`, `_model_call_text`, `FakeModels`, `CHALLENGE_REASK`. Do not import `_has_prior_model_turn` in tests — assert through `run_turn` behavior.

```python
def test_run_turn_challenge_nudge_skipped_without_prior_answer():
    """A first-turn lexical challenge must not inject CHALLENGE_REASK."""
    fake = SimpleNamespace(models=FakeModels([_response([types.Part(text="Ok")])]))
    answer, history, steps = run_turn(fake, [], "como?", model="test")
    assert answer == "Ok"
    assert len(fake.models.calls) == 1
    assert CHALLENGE_REASK not in _model_call_text(fake, 0)


def test_run_turn_challenge_nudge_fires_after_text_only_prior_answer():
    """Working memory is text-only; a prior model turn is enough to challenge."""
    fake = SimpleNamespace(
        models=FakeModels(
            [
                _response([types.Part(text="No se ha jugado.")]),
                _response([types.Part(text="España 1-0 Argentina.")]),
            ]
        )
    )
    prior = [
        types.Content(role="user", parts=[types.Part(text="hola")]),
        types.Content(role="model", parts=[types.Part(text="hola!")]),
    ]
    answer, history, steps = run_turn(fake, prior, "como?", model="test")
    assert CHALLENGE_REASK in _model_call_text(fake, 1)
    assert len(fake.models.calls) == 2
    assert "España" in answer
```

- [ ] **Step 2: Run the new tests (expect fail on the skip case)**

Run from `soccer-analytics-agent/`:

```bash
uv run pytest tests/test_loop.py::test_run_turn_challenge_nudge_skipped_without_prior_answer tests/test_loop.py::test_run_turn_challenge_nudge_fires_after_text_only_prior_answer tests/test_loop.py::test_run_turn_challenge_nudge_forces_reverification -q
```

Expected before the gate exists: `test_run_turn_challenge_nudge_skipped_without_prior_answer` **FAILS** (nudge fires on empty history; `len(fake.models.calls) != 1` or `CHALLENGE_REASK` appears). The text-only prior-answer test should already **PASS** (current code fires on any `_is_challenge` match). The existing `_grounded_history` test must still **PASS**.

- [ ] **Step 3: Implement the gate**

Add this helper in `soccer_agent/loop.py` immediately after `_is_challenge`:

```python
def _has_prior_model_turn(history: list) -> bool:
    """True when incoming history already contains a model answer to challenge."""
    return any(getattr(content, "role", None) == "model" for content in history)
```

At the start of `run_turn_events`, snapshot **before** appending the current user message:

```python
    history = list(history)
    prior_model_turn = _has_prior_model_turn(history)
    history.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
```

Change the challenge-nudge condition from:

```python
            if (
                not challenge_nudge_used
                and not any_tool_calls_this_turn
                and _is_challenge(user_message)
            ):
```

to:

```python
            if (
                not challenge_nudge_used
                and not any_tool_calls_this_turn
                and prior_model_turn
                and _is_challenge(user_message)
            ):
```

Do not touch the grounding-nudge `if` above it.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_loop.py -q -m "not integration"
```

Expected: all selected `test_loop` tests PASS, including the two new ones and `test_run_turn_challenge_nudge_forces_reverification`. Grounding tests (`test_run_turn_grounding_nudge_forces_tool_on_factual_question`) still PASS with empty prior history.

- [ ] **Step 5: Commit**

```bash
git add soccer-analytics-agent/soccer_agent/loop.py soccer-analytics-agent/tests/test_loop.py
git commit -m "$(cat <<'EOF'
fix(agent): skip challenge nudge when there is no prior answer

EOF
)"
```

If the repo root is `ai-agents-hub`, `git add` those two paths from the repo root (or `cd soccer-analytics-agent` and add the relative paths if this worktree's cwd is the project). Include only these files.

---

### Task 2: Classify the raw utterance, not the augmented prompt

**Files:**
- Modify: `soccer-analytics-agent/soccer_agent/loop.py` (`run_turn_events`, `run_turn`)
- Modify: `soccer-analytics-agent/soccer_agent/chat.py` (`respond`, `respond_stream`)
- Test: `soccer-analytics-agent/tests/test_loop.py`
- Test: `soccer-analytics-agent/tests/test_chat.py`

**Interfaces:**
- Consumes: Task 1's `prior_model_turn` snapshot and challenge condition
- Produces:

```python
def run_turn_events(
    client, history: list, user_message: str, model: str, trace_ctx: dict | None = None,
    *,
    classify_as: str | None = None,
):
    ...

def run_turn(
    client, history: list, user_message: str, model: str, trace_ctx: dict | None = None,
    *,
    classify_as: str | None = None,
) -> tuple[str, list, int]:
    ...
```

`classifier_text = user_message if classify_as is None else classify_as` is used for `_is_challenge` and `_needs_grounding` only. The content appended to history and sent to Gemini remains `user_message` (the augmented prompt in production).

- [ ] **Step 1: Add the failing tests**

In `tests/test_loop.py`:

```python
def test_run_turn_challenge_uses_classify_as_not_user_message():
    """Lexical hints in episodic context must not trigger the challenge nudge."""
    fake = SimpleNamespace(
        models=FakeModels([_response([types.Part(text="He plays for Inter Miami.")])])
    )
    prior = [
        types.Content(role="user", parts=[types.Part(text="hola")]),
        types.Content(role="model", parts=[types.Part(text="hola!")]),
    ]
    augmented = (
        "Relevant context from earlier in this session:\n"
        "- Earlier you asked: 'who won?' -> 'that is wrong, Spain won'\n\n"
        "Current question: Where does Messi play now?"
    )
    answer, history, steps = run_turn(
        fake,
        prior,
        augmented,
        model="test",
        classify_as="Where does Messi play now?",
    )
    assert answer == "He plays for Inter Miami."
    assert len(fake.models.calls) == 1
    assert CHALLENGE_REASK not in _model_call_text(fake, 0)
```

Without `classify_as` honored, `_is_challenge(augmented)` is True because `"wrong"` is in `_CHALLENGE_HINTS`, so this test FAIL (extra model call / `CHALLENGE_REASK` present).

In `tests/test_chat.py`, add a test that captures kwargs. Keep the existing `test_respond_injects_episodic_grounding_and_persists` fixtures pattern:

```python
def test_respond_passes_raw_utterance_as_classify_as(monkeypatch):
    captured = {}

    def fake_run_turn(client, history, user_message, model, trace_ctx=None, classify_as=None):
        captured["user_message"] = user_message
        captured["classify_as"] = classify_as
        return "ok", history, 1

    monkeypatch.setattr(chat, "run_turn", fake_run_turn)
    monkeypatch.setattr(chat.memory, "load_working", lambda s, limit=10: [])
    monkeypatch.setattr(
        chat.memory,
        "recall_episodes",
        lambda s, q, k=3: [
            {
                "user_message": "Who is Messi?",
                "agent_response": "An Argentine forward.",
                "score": 0.9,
            }
        ],
    )
    monkeypatch.setattr(chat.memory, "append_working", lambda s, r, c: None)
    monkeypatch.setattr(chat.memory, "save_episode", lambda s, u, a: None)
    monkeypatch.setattr(chat.trace, "get_last_turn_id", lambda s: 0)

    fake = SimpleNamespace(models=FakeModels("unused"))
    chat.respond(fake, "sess-1", "Where does he play now?", model="test")

    assert captured["classify_as"] == "Where does he play now?"
    assert "Messi" in captured["user_message"]
    assert "Where does he play now?" in captured["user_message"]
```

Also add the stream twin, stubbing `run_turn_events` as a generator that yields one `done` event:

```python
def test_respond_stream_passes_raw_utterance_as_classify_as(monkeypatch):
    captured = {}

    def fake_run_turn_events(
        client, history, user_message, model, trace_ctx=None, classify_as=None
    ):
        captured["user_message"] = user_message
        captured["classify_as"] = classify_as
        yield {"type": "done", "answer": "ok"}

    monkeypatch.setattr(chat, "run_turn_events", fake_run_turn_events)
    monkeypatch.setattr(chat.memory, "load_working", lambda s, limit=10: [])
    monkeypatch.setattr(chat.memory, "recall_episodes", lambda s, q, k=3: [])
    monkeypatch.setattr(chat.memory, "append_working", lambda s, r, c: None)
    monkeypatch.setattr(chat.memory, "save_episode", lambda s, u, a: None)
    monkeypatch.setattr(chat.trace, "get_last_turn_id", lambda s: 0)

    fake = SimpleNamespace(models=FakeModels("unused"))
    events = list(chat.respond_stream(fake, "sess-1", "hola", model="test"))

    assert captured["classify_as"] == "hola"
    assert captured["user_message"] == "hola"  # no episodes → not augmented
    assert events[-1]["type"] == "done"
```

- [ ] **Step 2: Run the new tests (expect fail)**

```bash
uv run pytest tests/test_loop.py::test_run_turn_challenge_uses_classify_as_not_user_message tests/test_chat.py::test_respond_passes_raw_utterance_as_classify_as tests/test_chat.py::test_respond_stream_passes_raw_utterance_as_classify_as -q
```

Expected: FAIL (`run_turn` TypeError on unexpected `classify_as` and/or chat tests `assert captured["classify_as"] == ...` because it is `None`).

- [ ] **Step 3: Implement**

In `soccer_agent/loop.py`, add keyword-only `classify_as: str | None = None` to both `run_turn_events` and `run_turn`. Immediately after the `prior_model_turn` snapshot:

```python
    classifier_text = user_message if classify_as is None else classify_as
```

Replace `_is_challenge(user_message)` with `_is_challenge(classifier_text)` and `_needs_grounding(user_message)` with `_needs_grounding(classifier_text)` in **both** grounding sites (the initial grounding nudge and the error-retry `_needs_grounding` check). Keep appending `user_message` to history, not `classifier_text`.

`run_turn` must forward the kwarg:

```python
    gen = run_turn_events(
        client, history, user_message, model, trace_ctx, classify_as=classify_as
    )
```

In `soccer_agent/chat.py`:

```python
    answer, _, _ = run_turn(
        client, prior, augmented, model=model, trace_ctx=trace_ctx,
        classify_as=user_message,
    )
```

and

```python
    gen = run_turn_events(
        client, prior, augmented, model=model, trace_ctx=trace_ctx,
        classify_as=user_message,
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_loop.py tests/test_chat.py -q -m "not integration"
```

Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```bash
git add soccer-analytics-agent/soccer_agent/loop.py soccer-analytics-agent/soccer_agent/chat.py soccer-analytics-agent/tests/test_loop.py soccer-analytics-agent/tests/test_chat.py
git commit -m "$(cat <<'EOF'
fix(agent): classify challenges on the raw utterance

EOF
)"
```
