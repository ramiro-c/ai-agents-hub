# Soccer Analytics Agent — Design

**Date**: 2026-07-10
**Status**: Approved
**Goal**: Learning-first replication of Oracle's `soccer-analytics-agent` workshop, rebuilt on an open stack with a hand-written agent loop. The main deliverable is understanding, not the app.

## Context

The reference workshop (`oracle-ai-developer-hub/workshops/soccer-analytics-agent`) builds a FIFA soccer analytics chat agent over 49k international matches (Kaggle, 1872–2024). Its key ideas:

- Custom prompt/tool loop (no agent framework)
- 13 tools: read-only SQL, vector search, hybrid retrieval, XGBoost match predictor, memory read/write, analytical feature tools
- Three-tier agent memory: working / episodic / semantic
- Hybrid retrieval (vector + full-text with RRF fusion)
- Per-turn observability (step trace persisted to the DB)
- 92-feature XGBoost pipeline (Elo, form, H2H, momentum, Poisson xG, tournament context) with Optuna hyperparameter tuning — the LLM is stock; the domain intelligence lives in the specialist model exposed as a tool

We replicate the architecture and concepts, not the Oracle stack.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Stack | Open stack, custom loop | Learn agent internals; no framework hiding the loop |
| LLM | Gemini via raw `google-genai` SDK | $1500 GCP credits available; no ADK — the loop is hand-written |
| Database | Postgres 16 + pgvector (Docker) | Single layer for data + vectors + memory, mirroring Oracle AI DB's role |
| Embeddings | `sentence-transformers` local, `all-MiniLM-L6-v2` (384 dims) | Same model family as the workshop, free, no API dependency |
| Dataset | Kaggle international results (49k matches) | Free, proven, user knows the domain professionally |
| Scope | Everything, phased | Agent works from phase 1; ML pipeline lands last |
| Location | `soccer-analytics-agent/` at repo root | New top-level project in `ai-agents-hub` |
| Language | Python 3.12 + `uv` | Matches the original and the rest of the hub |

## Architecture

```
CLI REPL (phase 1) / React UI (phase 6)
        |
FastAPI (phase 6): /chat /predict /health /memory /trace
        |
Agent loop (hand-written): recall memory -> ground with hybrid retrieval
    -> Gemini -> dispatch tool calls -> persist memory + trace -> answer
        |
Tools: sql_query (read-only, allowlisted) | vector_search | hybrid_retrieve
       | remember / recall | get_elo / get_team_form / get_h2h
       | predict_match (Elo-based v1 -> XGBoost v2)
        |
Postgres 16 + pgvector (Docker)
  - matches, goalscorers, shootouts (Kaggle data)
  - working / episodic / semantic memory tables (vector(384))
  - document store for hybrid retrieval (tsvector + vector)
  - agent_trace (per-turn step log)
```

## Phases

Each phase: concept first, then code, then tests. The agent chats from phase 1 onward.

| Phase | Build | Learn |
|---|---|---|
| 0 | Docker compose (Postgres+pgvector), schema, Kaggle data load | Data modeling for agents |
| 1 | Minimal loop: Gemini + `sql_query` tool + CLI REPL | Tool calling by hand — the core |
| 2 | Working/episodic/semantic memory + `remember`/`recall` tools | Three-tier agent memory |
| 3 | Hybrid retrieval: pgvector + Postgres full-text, RRF fusion | Why hybrid beats semantic-only |
| 4 | Elo tracker + `predict_match` v1 (Elo-based heuristic) | Analytical tools, grounding with computation |
| 5 | Observability: persist every step of every turn | Debugging agents seriously |
| 6 | FastAPI + React frontend | From REPL to product |
| 7 | Full ML pipeline: feature trackers, XGBoost, Optuna; swap predictor | Temporal feature engineering + live inference |

## Error handling and safety

- `sql_query`: read-only, statement allowlist (SELECT only), query timeout, row limit — mirrors the original's guardrails
- Tool dispatch wraps every tool in try/except; errors are returned to the model as tool results, never crash the loop
- LLM calls: retry with backoff on transient API errors

## Testing

- pytest per phase, following the hub's existing conventions (Ruff, pre-commit)
- Unit tests for tools and trackers (Elo math, RRF fusion, memory persistence)
- Smoke test script per phase that exercises the loop end-to-end against the local DB

## Out of scope

- Oracle AI Database, OCI GenAI, in-DB ONNX embeddings
- LangChain/LangGraph (the original uses them only as storage adapters)
- Deployment (Cloud Run can come later; local-first for learning)
