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

## Docs

- Design spec: `../docs/superpowers/specs/2026-07-10-soccer-analytics-agent-design.md`
- Implementation plan: `../docs/superpowers/plans/2026-07-11-soccer-agent-phase-0-1.md`
