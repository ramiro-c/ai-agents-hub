# Soccer Analytics Agent — Phase 3: Hybrid Retrieval (RRF fusion)

> **For agentic workers:** Implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the agent a document store and two new tools — `vector_search` (semantic-only) and `hybrid_retrieve` (vector + full-text fused with RRF) — so it can answer questions that need both what words *mean* and what they *say*.

**Architecture:** Add a `match_documents` table with `tsvector` + `vector(384)` columns, a script to generate rich text descriptions from the matches table, a `retrieval.py` module with RRF fusion logic, and two new agent tools. `run_turn` stays untouched; the tools are just new entries in `TOOL_DECLARATIONS` and `_HANDLERS`.

**Why hybrid beats semantic-only:** "Argentina world cup wins" → vector search finds docs about "Argentina winning tournaments" (semantic) but might miss the literal "World Cup" phrase; full-text finds docs with "World Cup" + "Argentina" (exact) but won't understand that "they lifted the trophy in Qatar" is the same event. RRF fuses both rankings without assuming their scores are comparable — it just looks at position.

**Tech Stack:** Same as Phase 2, plus Postgres `tsvector`/`tsquery` built-ins (already available in Postgres 16; no extra package needed).

**Spec:** `docs/superpowers/specs/2026-07-10-soccer-analytics-agent-design.md`
**Builds on:** `docs/superpowers/plans/2026-07-12-soccer-agent-phase-2.md`

## How RRF works (you must understand this before implementing)

Two search methods rank the same documents differently:

```
Vector (cosine <=>):              Full-text (ts_rank):
  1. doc #42  (0.92)               1. doc #17  (0.45)
  2. doc #17  (0.88)               2. doc #88  (0.38)
  3. doc #88  (0.81)               3. doc #42  (0.30)
  4. doc #55  (0.75)               4. doc #99  (0.25)
  5. doc #99  (0.70)               5. doc #55  (0.20)
```

Averaging raw scores doesn't work (scales are incomparable: 0.92 cosine ≠ 0.45 ts_rank). RRF ignores raw scores and uses only rank position:

```
RRF(doc) = Σ 1/(k + rank)   for each retrieval method
```

Standard `k=60`. Final ranking:

```
doc #17: 1/(60+2) + 1/(60+1) = 0.0325  ← wins (top-2 in both)
doc #42: 1/(60+1) + 1/(60+3) = 0.0323
doc #88: 1/(60+3) + 1/(60+2) = 0.0320
doc #55: 1/(60+4) + 1/(60+5) = 0.0305
doc #99: 1/(60+5) + 1/(60+4) = 0.0305
```

Documents that rank consistently high across both methods surface to the top. Documents that dominate one method but rank poorly in the other drop.

## Global Constraints

- Everything from Phase 2 applies (Python 3.12+, `uv` only, English, read-only `sql_query`, `DATABASE_URL`/`GEMINI_MODEL` env, conventional commits, run from `soccer-analytics-agent/`).
- Embedding model: `all-MiniLM-L6-v2`, 384 dims, normalized — reuse `embeddings.embed()`.
- Vectors are sent to Postgres as string literals cast with `::vector` — reuse `memory._vec()` or inline.
- No new Python packages needed (tsvector is Postgres built-in, RRF is 5 lines of math).
- `run_turn` stays untouched — tools are pure new entries in the declarations/handlers.

## Task 1: Add match_documents table

**File:** `db/schema.sql`

Add after the existing memory tables (before the indexes section if there is one):

```sql
CREATE TABLE IF NOT EXISTS match_documents (
    id BIGSERIAL PRIMARY KEY,
    match_date DATE NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    content TEXT NOT NULL,
    tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_match_docs_tsv
    ON match_documents USING GIN (tsv);
CREATE INDEX IF NOT EXISTS idx_match_docs_embedding
    ON match_documents USING hnsw (embedding vector_cosine_ops);
```

GENERATED ALWAYS AS STORED means Postgres keeps the tsvector in sync automatically when `content` changes. No trigger needed.

- [ ] **Step 1: Add the table and indexes to schema.sql**

**Verify:** `uv run python -c "from soccer_agent import db; db.apply_schema()"` and then `uv run python -c "from soccer_agent import db; conn = db.connect(); conn.execute('SELECT 1 FROM match_documents LIMIT 0'); print('OK')"`

## Task 2: Script to generate documents from matches

**File:** `scripts/generate_documents.py`

This is a one-shot script (run after `load_data.py`). For each row in the `matches` table, build a natural-language sentence and embed it.

```python
"""Generate rich text documents for each match and store them with embeddings."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from soccer_agent import db, embeddings

def main():
    with db.connect() as conn:
        rows = conn.execute("""
            SELECT match_date, home_team, away_team, home_score, away_score,
                   tournament, city, country, neutral
            FROM matches
            WHERE match_date IS NOT NULL
            ORDER BY match_date
        """).fetchall()

        # Clear existing docs (idempotent re-run)
        conn.execute("TRUNCATE match_documents RESTART IDENTITY")

        for row in rows:
            d = row._mapping
            content = (
                f"On {d['match_date']}, {d['home_team']} played {d['away_team']} "
                f"in the {d['tournament'] or 'friendly'} "
                f"at {d['city'] or 'unknown city'}, {d['country'] or 'unknown country'}"
                f"{' (neutral venue)' if d['neutral'] else ''}. "
                f"Final score: {d['home_team']} {d['home_score']} - {d['away_score']} {d['away_team']}."
            )
            vec = embeddings.embed(content)
            conn.execute(
                """INSERT INTO match_documents (match_date, home_team, away_team, content, embedding)
                   VALUES (%s, %s, %s, %s, %s::vector)""",
                (d['match_date'], d['home_team'], d['away_team'], content, embeddings._vec(vec))
            )

        conn.commit()
        count = conn.execute("SELECT count(*) FROM match_documents").fetchone()[0]
        print(f"Generated {count} documents.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create `scripts/generate_documents.py` and run it**

**Verify:** `uv run python scripts/generate_documents.py` prints ~49k documents. Then `uv run python -c "from soccer_agent import db; conn = db.connect(); r = conn.execute('SELECT content FROM match_documents LIMIT 1').fetchone(); print(r[0])"` shows a well-formed sentence.

**Gotcha:** This embeds ~49k documents — ~30s on a Mac with MiniLM. It's a one-shot script; speed doesn't matter. If you interrupt it, re-run it (the TRUNCATE makes it idempotent).

## Task 3: `retrieval.py` — RRF fusion logic

**File:** `soccer_agent/retrieval.py`

Extract RRF into a pure module so both tools can use it and it's testable in isolation.

```python
"""Hybrid retrieval: RRF fusion of vector + full-text results."""


def rrf_fuse(
    vector_ranked: list[dict],
    text_ranked: list[dict],
    k: int = 60,
    top_n: int = 5,
) -> list[dict]:
    """Fuse two ranked result lists with Reciprocal Rank Fusion.

    Each item must have an 'id' key. Returns top_n items sorted by RRF score
    descending. The input order determines rank (first = rank 1).
    """
    scores: dict[int, float] = {}
    docs: dict[int, dict] = {}

    for rank, item in enumerate(vector_ranked, start=1):
        doc_id = item["id"]
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        docs[doc_id] = item

    for rank, item in enumerate(text_ranked, start=1):
        doc_id = item["id"]
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        docs[doc_id] = item  # last writer wins for metadata

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {**docs[doc_id], "rrf_score": round(score, 6)}
        for doc_id, score in ranked[:top_n]
    ]
```

- [ ] **Step 3: Create `soccer_agent/retrieval.py`**

**Verify:** `uv run pytest -q tests/test_retrieval.py` (we'll write the test in Task 5).

## Task 4: Add `vector_search` and `hybrid_retrieve` tools

**File:** `soccer_agent/tools.py`

Add vector search and hybrid retrieval functions, then register them in `TOOL_DECLARATIONS` and `_HANDLERS`.

### 4a. `vector_search` function

```python
def vector_search(query: str) -> dict:
    """Semantic-only search over match documents (for comparison)."""
    try:
        from soccer_agent import embeddings, memory

        vec = embeddings.embed(query)
        vec_str = memory._vec(vec)
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
```

### 4b. `hybrid_retrieve` function

```python
def hybrid_retrieve(query: str) -> dict:
    """Search match documents with hybrid retrieval (vector + full-text, RRF-fused)."""
    try:
        from soccer_agent import embeddings, memory
        from soccer_agent.retrieval import rrf_fuse

        vec = embeddings.embed(query)
        vec_str = memory._vec(vec)

        with db.connect() as conn:
            # Vector search: top 20 candidates
            vec_rows = conn.execute(
                """SELECT id, content, match_date, home_team, away_team,
                   1 - (embedding <=> %s::vector) AS score
                   FROM match_documents
                   ORDER BY embedding <=> %s::vector
                   LIMIT 20""",
                (vec_str, vec_str),
            ).fetchall()

            # Full-text search: top 20 candidates
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
            {"id": r[0], "content": r[1], "date": str(r[2]),
             "teams": f"{r[3]} vs {r[4]}", "source": "vector"}
            for r in vec_rows
        ]
        ts_ranked = [
            {"id": r[0], "content": r[1], "date": str(r[2]),
             "teams": f"{r[3]} vs {r[4]}", "source": "fulltext"}
            for r in ts_rows
        ]

        fused = rrf_fuse(vec_ranked, ts_ranked, k=60, top_n=5)
        # Mark which sources contributed
        for item in fused:
            vec_ids = {v["id"] for v in vec_ranked}
            ts_ids = {t["id"] for t in ts_ranked}
            sources = []
            if item["id"] in vec_ids:
                sources.append("vector")
            if item["id"] in ts_ids:
                sources.append("fulltext")
            item["sources"] = sources
        return {"results": fused}
    except Exception as exc:
        return {"error": str(exc)}
```

### 4c. Register in declarations and handlers

Add to `TOOL_DECLARATIONS`:

```python
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
```

Add to `_HANDLERS`:

```python
    "vector_search": lambda args: vector_search(args["query"]),
    "hybrid_retrieve": lambda args: hybrid_retrieve(args["query"]),
```

- [ ] **Step 4a: Add `vector_search` function to `tools.py`**
- [ ] **Step 4b: Add `hybrid_retrieve` function to `tools.py`**
- [ ] **Step 4c: Register both in `TOOL_DECLARATIONS` and `_HANDLERS`**

**Verify:** `uv run python -c "from soccer_agent.tools import vector_search, hybrid_retrieve; print(vector_search('World Cup final')); print(hybrid_retrieve('World Cup final'))"` returns real results.

## Task 5: Tests

**Files:** `tests/test_retrieval.py`, `tests/test_tools.py` (amend)

### 5a. RRF unit tests (`tests/test_retrieval.py`)

Pure unit test — no DB needed, runs offline.

```python
"""Unit tests for RRF fusion logic."""
from soccer_agent.retrieval import rrf_fuse


def test_rrf_fuses_two_rankings():
    vec = [
        {"id": 42, "content": "doc 42"},
        {"id": 17, "content": "doc 17"},
        {"id": 88, "content": "doc 88"},
    ]
    txt = [
        {"id": 17, "content": "doc 17"},
        {"id": 88, "content": "doc 88"},
        {"id": 42, "content": "doc 42"},
    ]
    result = rrf_fuse(vec, txt, k=60, top_n=5)

    # doc 17 ranks high in both (2nd + 1st) → should be first
    assert result[0]["id"] == 17
    # All three should appear
    ids = {r["id"] for r in result}
    assert ids == {17, 42, 88}


def test_rrf_doc_in_only_one_list_still_scores():
    vec = [{"id": 1, "content": "a"}]
    txt = [{"id": 2, "content": "b"}]
    result = rrf_fuse(vec, txt, k=60, top_n=5)
    assert len(result) == 2


def test_rrf_respects_top_n():
    vec = [{"id": i, "content": str(i)} for i in range(20)]
    txt = []
    result = rrf_fuse(vec, txt, k=60, top_n=3)
    assert len(result) == 3
```

- [ ] **Step 5a: Create `tests/test_retrieval.py`**

**Verify:** `uv run pytest tests/test_retrieval.py -q` → 3 passed.

### 5b. Integration tests for tools (`tests/test_tools.py`)

Add after the existing `test_remember_then_recall_via_dispatch` test. Requires `@pytest.mark.integration` because it hits the DB.

```python
@pytest.mark.integration
def test_vector_search_returns_results():
    from soccer_agent.tools import vector_search

    result = vector_search("World Cup final Argentina")
    assert "results" in result
    assert len(result["results"]) > 0
    for r in result["results"]:
        assert "content" in r
        assert "score" in r
        assert "teams" in r


@pytest.mark.integration
def test_hybrid_retrieve_returns_fused_results():
    from soccer_agent.tools import hybrid_retrieve

    result = hybrid_retrieve("World Cup final Argentina")
    assert "results" in result
    assert len(result["results"]) > 0
    for r in result["results"]:
        assert "content" in r
        assert "rrf_score" in r
        assert "sources" in r
        assert len(r["sources"]) >= 1  # at least one source contributed


@pytest.mark.integration
def test_hybrid_retrieve_via_dispatch():
    from soccer_agent.tools import dispatch

    result = dispatch("hybrid_retrieve", {"query": "Brazil goals"})
    assert "results" in result
    assert len(result["results"]) > 0
```

- [ ] **Step 5b: Add integration tests to `tests/test_tools.py`**

**Verify:** `uv run pytest tests/ -q` (including integration, DB must be up).

## Verification

- [ ] **Step 6: Run the full suite and commit**

```bash
uv run pytest -q
# Expected: all pass (unit offline + integration with DB up).
```

```bash
git add soccer-analytics-agent docs/
git commit -m "feat(soccer-agent): hybrid retrieval with RRF fusion (vector + full-text)"
```

## Smoke test

After committing, run the CLI and try queries that benefit from hybrid:

```bash
uv run python -m soccer_agent.cli
```

Try prompts like:
- "Use hybrid_retrieve to find Argentina World Cup final matches"
- "Use vector_search to find high-scoring matches"
- "Compare vector_search and hybrid_retrieve for 'Brazil vs Argentina'"

---

## Self-review notes

- Spec coverage (Phase 3): document store ✓, vector_search ✓, hybrid_retrieve ✓, RRF fusion ✓.
- RRF is extracted into `retrieval.py` — a pure module with no DB or genai imports, trivially testable.
- Both tools return structured results the model can reason over (dates, scores, teams, sources).
- `websearch_to_tsquery('english', $1)` handles user-style queries without requiring `&`/`|` syntax — it's more forgiving than `plainto_tsquery` for multi-word phrases.
- vector_search uses LIMIT 5 directly; hybrid_retrieve fetches 20 from each method to give RRF a richer candidate pool before narrowing to 5.
- `match_documents` uses GENERATED ALWAYS AS STORED for the tsvector column — no triggers, no manual updates, Postgres handles it.
- Deferred to later phases: proper tuning of RRF `k` parameter per domain (60 is fine for now), document chunking/overlap for long content, re-ranking with a cross-encoder.
