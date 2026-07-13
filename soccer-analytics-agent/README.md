# Soccer Analytics Agent

A soccer analytics chat agent over 49k international matches (1872–today), built with a **hand-written LLM tool loop** — no agent framework. Gemini reasons and calls tools; Postgres + pgvector is the single layer for data, memory, and observability. A learning-first replication of Oracle's `soccer-analytics-agent` workshop on an open, GCP-deployable stack.

> **New here (human or agent)? Read [`CONTEXT.md`](CONTEXT.md) first** — it is the single source of truth for the vision, mental models, architecture, conventions, roadmap, and gotchas.

## Quickstart

```bash
uv sync --all-groups                     # install deps
docker compose up -d                     # start Postgres + pgvector
uv run python scripts/load_data.py       # download & load the Kaggle dataset
uv run python -m soccer_agent.cli        # chat with the agent
```

Copy `.env.example` to `.env` and fill in your Gemini credentials (AI Studio key or Vertex AI) before running the agent.

## One generalist, several specialists

The core design idea: a large generalist LLM orchestrates, while small specialist
models do one narrow job each — cheaply and locally. A good agent is not one giant
model doing everything; it is an LLM that knows when to delegate to a tool or a
specialized model.

| Model | Size | Job | Runs |
|---|---|---|---|
| Gemini (LLM) | billions of params | reason, converse, decide which tool to call | Vertex AI (paid API) |
| MiniLM (`all-MiniLM-L6-v2`) | ~22M params | turn text into a 384-dim meaning vector (embeddings) | local, free |
| XGBoost (Phase 7) | gradient-boosted trees | predict a match outcome from engineered features | local, free |

SQL search matches what words *say* (exact text); embeddings match what words *mean*
(semantic similarity). The agent uses both — SQL for exact facts, embeddings for
memory recall.

## Key Concepts

### Embedding = Vector

An **embedding** is a dense list of floats (a vector) that captures the meaning of
text in a learned semantic space. MiniLM maps any sentence to 384 numbers. Texts
with similar meaning end up close to each other in this space — measured by cosine
distance (the angle between vectors).

We work with the same embedding in three forms:

| Representation | Example | Where |
|---|---|---|
| Python `list[float]` | `[0.12, -0.08, 0.34, ...]` | `embeddings.embed(text)` |
| pgvector string literal | `'[0.12,-0.08,0.34,...]'` | `memory.render_vector(vec)` |
| Postgres native `vector(384)` | `::vector` cast in SQL | schema, INSERTs, `<=>` operator |

### HNSW (Hierarchical Navigable Small World)

The algorithm behind our `USING hnsw` vector indexes. Instead of comparing a query
against every document (O(n) full scan), HNSW builds a layered graph:

- **Layer 0**: every vector is a node, connected to its nearest neighbors (local streets).
- **Upper layers**: progressively fewer nodes with longer-range edges (highways).

Search starts at the top layer, greedily hops toward the nearest node, then descends
a layer and repeats — like zooming from country → city → neighborhood → street.
Result: ~99% recall in O(log n) time instead of O(n).

### RRF (Reciprocal Rank Fusion)

Combines two ranked result lists (e.g., vector search + full-text search) without
tuning weights. Formula: `RRF(doc) = Σ 1 / (k + rank)` with `k = 60`.

It only cares about **position** (1st, 2nd, 3rd…), not raw scores — making it
immune to different score scales between vector and text engines. A document ranked
3rd in both lists beats one ranked 1st in one and 20th in the other. RRF rewards
consensus.

### Why hybrid beats semantic-only

Vector search understands *meaning* ("scored a goal" matches "found the net") but
misses exact terms. Full-text search (`tsvector`) catches exact names and phrases
("Lionel Messi" vs "Messi, Lionel") but misses synonyms. **Hybrid retrieval** runs
both and fuses results via RRF — each covers the other's blind spots.

## Docs

- Design spec: `../docs/superpowers/specs/2026-07-10-soccer-analytics-agent-design.md`
- Implementation plan: `../docs/superpowers/plans/2026-07-11-soccer-agent-phase-0-1.md`
