# Soccer Analytics Agent — Project Context

> **Read this first.** This is the single source of truth for what this project is,
> why it exists, how it is built, and where it is going. Any agent or developer
> should be able to pick up the work from here without further explanation.

## What this is

A soccer analytics **chat agent** over ~49k international matches (1872–today,
Kaggle dataset), built with a **hand-written LLM tool loop** — deliberately with
**no agent framework** (no ADK, LangGraph, LangChain orchestration). It is a
learning-first replication of Oracle's `soccer-analytics-agent` workshop, rebuilt
on an open, GCP-deployable stack.

**The primary deliverable is understanding, not the app.** Every decision favors
learning the internals of how an agent actually works over shipping fast. If you
are helping here, teach the *why*; do not hide mechanics behind abstractions.

## Three mental models you must internalize

### 1. The agent IS a loop (no framework)

An "agent" here is literally a `while` loop over the raw `google-genai` SDK. The
LLM never executes anything — it emits text or asks you to run a tool. The runtime
(our code) is the executor. Per turn:

1. Send system prompt + tool declarations + history to the model.
2. The model returns either plain **text** (→ done, that's the answer) or one or
   more **`function_call`** parts (→ run the tools).
3. For tool calls: dispatch each, append the raw result back into history as a
   **`function_response`** with `role="user"` (in the Gemini protocol, "user" =
   "everything fed into the model", not "the human"; tool results pair with their
   call via the `name` field).
4. Loop until the model answers in text, or `MAX_TOOL_ROUNDS` is hit.

Errors are returned to the model **as tool results** (`{"error": "..."}`), never
raised — so the model can self-correct. `dispatch()` never raises.

See `soccer_agent/loop.py` (`run_turn`) — kept pure and framework-free.

### 2. One generalist, several specialists

A good agent is not one giant model doing everything. It is a generalist LLM that
delegates narrow jobs to cheap specialist models exposed as tools.

| Model | Size | Job | Runs |
|---|---|---|---|
| Gemini (LLM) | billions of params | reason, converse, decide which tool to call | Vertex AI (paid API) |
| MiniLM (`all-MiniLM-L6-v2`) | ~22M params | text → 384-dim meaning vector (embeddings) | local, free |
| XGBoost (Phase 7, planned) | gradient-boosted trees | predict match outcome from engineered features | local, free |

SQL search matches what words *say* (exact text). Embeddings match what words
*mean* (semantic similarity). The agent uses both.

### 3. Three-tier memory

| Tier | Question it answers | Scope | Retrieval | How it's wired |
|---|---|---|---|---|
| **Working** | "What are we talking about right now?" | This session | Recency (last N turns) | Auto-seeded into history by `respond()` |
| **Episodic** | "Have we touched something like this before?" | This session | Similarity (vector) | Auto-recalled and injected as grounding by `respond()` |
| **Semantic** | "What durable facts do I know?" | Global | Similarity (vector) | Model-controlled via `remember`/`recall` tools |

Episodic = events ("on turn 5 the user asked about Messi"). Semantic = distilled
knowledge ("the user supports Argentina"). Working = short-term recency. Different
scope, retrieval, and owner (runtime vs. model). Keeping them separate is the point.
`run_turn` stays pure; memory is wired around it by `respond()` in `chat.py`.

## Architecture (current)

```
CLI REPL (soccer_agent/cli.py)          [Phase 6: FastAPI + React planned]
        |
respond() — memory-aware wrapper (soccer_agent/chat.py)
   seed working memory + recall episodic  ->  run_turn  ->  persist working+episodic
        |
run_turn — pure hand-written loop (soccer_agent/loop.py)
   model -> function_call -> dispatch -> function_response -> repeat
        |
tools (soccer_agent/tools.py): sql_query | vector_search | hybrid_retrieve | get_team_elo | get_team_form | get_h2h | predict_match | remember | recall
        |
Postgres 16 + pgvector (docker-compose.yml)
   matches / goalscorers / shootouts                  (Kaggle data)
   match_documents                                    (49k docs, tsvector + vector(384), GIN + HNSW)
   team_elo                                           (336 teams, materialized Elo from 49k matches)
   working_memory / episodic_memory / semantic_memory  (vector(384), HNSW cosine)
        |
embeddings (soccer_agent/embeddings.py): MiniLM, local, 384 dims, normalized
```

## Repository map

| Path | Responsibility |
|---|---|
| `soccer_agent/db.py` | Postgres connection + idempotent `apply_schema()` |
| `soccer_agent/tools.py` | 9 tool schemas + guards + `dispatch()` |
| `soccer_agent/loop.py` | Pure hand-written agent loop (`run_turn`) — no memory, no framework |
| `soccer_agent/embeddings.py` | `embed(text) -> list[float]` via MiniLM |
| `soccer_agent/memory.py` | Storage layer for all three tiers + `render_vector()` (no genai imports) |
| `soccer_agent/retrieval.py` | `rrf_fuse()` — RRF math, DB-free, k=60 |
| `soccer_agent/elo.py` | Elo math: `expected_score()`, `k_factor()`, `BASE_ELO=1500` |
| `soccer_agent/chat.py` | `respond()` — memory-aware wrapper around `run_turn` |
| `soccer_agent/cli.py` | Terminal REPL entry point |
| `db/schema.sql` | All tables + pgvector extension + HNSW+GIN indexes |
| `scripts/load_data.py` | Download Kaggle dataset and load into Postgres |
| `scripts/generate_documents.py` | Embed 49k matches as rich-text docs for hybrid retrieval |
| `scripts/compute_elos.py` | Compute Elo ratings from match history → materialize to team_elo |
| `scripts/smoke_test.py` | One-shot end-to-end check (real Vertex + DB) |
| `tests/` | 43 behavior tests (unit + integration, marked `@pytest.mark.integration`) |

## Conventions (non-negotiable)

- **Python 3.12+, `uv` only.** Never `pip install`. Add deps to `pyproject.toml`,
  run `uv sync`. Run things with `uv run ...`.
- **English** for all code, comments, docstrings, and docs. (Chat with the human
  can be Spanish; the artifacts are English.)
- **Behavior-first testing, not strict TDD.** Implement first, then run the
  behavior tests. Do not add ceremony (no test-first red/green ritual). Tests
  should fail when behavior fails — assert on meaningful outcomes, not just
  "non-empty". Unit tests inject fakes and run offline; integration tests are
  marked `@pytest.mark.integration` and skip cleanly when the DB is down.
- **`sql_query` is read-only:** SELECT/WITH only, single statement, 5s timeout,
  50-row cap. (Second layer of defense; a read-only DB role is the real fix at
  deploy time — see Phase 8.)
- **Tests must never mutate shared real data.** Use TEMP tables / rollbacks. (A
  destructive integration test once truncated the real `matches` table — see
  Gotchas.)
- **Conventional commits, no AI attribution / no Co-Authored-By.** Commit at the
  end of each task; commit is part of "done".
- **Ruff pre-commit hook** runs on commit; it may reformat and block on lint. Let
  it fix, `git add` again, re-commit.

## Environment setup

### Database
```bash
docker compose up -d          # start Postgres + pgvector (port 5433)
uv run python scripts/load_data.py   # first time only; data persists in the pgdata volume
```
**Gotcha:** if the machine reboots/sleeps, the container stops. `docker compose up -d`
brings it back with data intact (named volume). If a query returns "connection
refused", the container is down — this is the first thing to check.

### Gemini via Vertex AI (isolated from other GCP work)
- Uses an **isolated per-project ADC file**, not a service-account key (org policy
  `iam.disableServiceAccountKeyCreation` blocks SA keys; also ADC avoids a
  long-lived key on disk).
- GCP project: `gen-lang-client-0049374628` (Adk Labs), personal account.
- Credential: `.secrets/adc-personal.json` (gitignored) — a copy of the personal
  user ADC with quota project set to Adk Labs.
- `.env` sets `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`,
  `GOOGLE_CLOUD_LOCATION=us-central1`, `GOOGLE_APPLICATION_CREDENTIALS` → the
  isolated file. The global ADC can be pointed at anything else; this project is
  unaffected because it reads the isolated copy.
- Service account `soccer-agent@gen-lang-client-0049374628.iam.gserviceaccount.com`
  (role `aiplatform.user`) exists, reserved for the Cloud Run deploy (Phase 8),
  attached to the service — no key needed there.

Copy `.env.example` to `.env` and fill credentials before running the agent.

## Roadmap (phases)

Each phase: concept first, then code, then behavior tests. The agent chats from
Phase 1 onward. Full design in the spec; per-phase detail in the plans.

| Phase | Scope | Status |
|---|---|---|
| 0 | Docker + schema + Kaggle load | ✅ Done |
| 1 | Minimal loop: Gemini + `sql_query` + CLI REPL | ✅ Done |
| 2 | Three-tier memory + `remember`/`recall` + embeddings | ✅ Done |
| 3 | Hybrid retrieval: pgvector + Postgres full-text, RRF fusion (49k docs) | ✅ Done |
| 4 | Elo tracker + `predict_match` v1 (Elo-based heuristic, 336 teams) | ✅ Done |
| 5 | Observability: persist every step of every turn (trace table) | ⏳ Next |
| 6 | FastAPI + React frontend | ⬜ Planned |
| 7 | Full ML pipeline: feature trackers + XGBoost + Optuna; swap predictor | ⬜ Planned |
| 8 | Deploy to GCP: Cloud SQL, Artifact Registry, Cloud Run, Secret Manager | ⬜ Planned |

## Known deferred items & gotchas

- **Loop robustness (→ Phase 5):** `run_turn` assumes `response.candidates[0]`
  exists and `content.parts` is non-`None`. On a safety block or `MAX_TOKENS`
  finish, `candidates` can be empty and `parts` can be `None` → crash. Harden when
  adding observability.
- **Smoke test assertion:** `scripts/smoke_test.py` should assert a *grounded*
  answer (e.g. contains digits), not just non-empty text — otherwise it greens on
  a failed run. Tighten when convenient.
- **Observability is the missing debugging tool (→ Phase 5):** tool calls and
  results currently live only in the in-memory `history` and vanish when the
  process ends. There is no persistent log. Phase 5 writes a step trace to a
  `agent_trace` table so a turn can be reconstructed after the fact:
  `SELECT * FROM agent_trace WHERE session_id = ... ORDER BY created_at`. Until
  then, an `AGENT_DEBUG` env-gated print in the loop is the interim tool.
- **Destructive-test lesson (already fixed):** an integration test used
  `TRUNCATE matches` on the real table and left it with 2 test rows, wiping the
  dataset whenever the suite ran. Fixed by loading into a session-local TEMP table.
  The rule: a test must never mutate data it did not create.
- **NULL scores in matches table:** some future-dated matches (e.g., friendlies
  scheduled for 2026) have NULL scores. Tools querying `matches WHERE home_team = X`
  must add `AND home_score IS NOT NULL` or the NULLs break arithmetic (learned
  Phase 4).

## Elo rankings (Phase 4)

Top 10 teams by current Elo (computed from 49k matches, 336 teams, as of 2026-07-12):

| # | Team | Elo |
|---|------|-----|
  1 | Argentina         | 2136.5 |
| 2 | Spain             | 2090.4 |
| 3 | Netherlands       | 2068.3 |
| 4 | France            | 2062.0 |
| 5 | Brazil            | 2054.5 |
| 6 | England           | 2053.7 |
| 7 | Germany           | 2046.8 |
| 8 | Italy             | 2022.1 |
| 9 | Portugal          | 2017.1 |
| 10 | Uruguay          | 2003.3 |

To refresh rankings: `uv run python scripts/compute_elos.py`

## How to work on this project

- Specs and plans live in the monorepo `docs/superpowers/`:
  - Spec: `docs/superpowers/specs/2026-07-10-soccer-analytics-agent-design.md`
  - Phase 0+1 plan: `docs/superpowers/plans/2026-07-11-soccer-agent-phase-0-1.md`
  - Phase 2 plan: `docs/superpowers/plans/2026-07-12-soccer-agent-phase-2.md`
  - Phase 3 plan: `docs/superpowers/plans/2026-07-12-soccer-agent-phase-3.md`
  - Phase 4 plan: `docs/superpowers/plans/2026-07-12-soccer-agent-phase-4.md`
- Workflow for a new phase: brainstorm the design → write a phase plan
  (concept + tasks with concrete code and behavior tests) → implement task by
  task → run `uv run pytest -q` → commit per task.
- Verify from the project root: `cd soccer-analytics-agent && uv run pytest -q`.
  Live end-to-end check: `uv run python scripts/smoke_test.py`.
