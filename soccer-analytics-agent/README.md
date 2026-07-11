# Soccer Analytics Agent

A soccer analytics chat agent over 49k international matches (1872–today), built with a **hand-written LLM tool loop** — no agent framework. Gemini reasons and calls tools; Postgres + pgvector is the single layer for data, memory, and observability. A learning-first replication of Oracle's `soccer-analytics-agent` workshop on an open, GCP-deployable stack.

## Quickstart

```bash
uv sync --all-groups                     # install deps
docker compose up -d                     # start Postgres + pgvector
uv run python scripts/load_data.py       # download & load the Kaggle dataset
uv run python -m soccer_agent.cli        # chat with the agent
```

Copy `.env.example` to `.env` and fill in your Gemini credentials (AI Studio key or Vertex AI) before running the agent.

## Docs

- Design spec: `../docs/superpowers/specs/2026-07-10-soccer-analytics-agent-design.md`
- Implementation plan: `../docs/superpowers/plans/2026-07-11-soccer-agent-phase-0-1.md`
