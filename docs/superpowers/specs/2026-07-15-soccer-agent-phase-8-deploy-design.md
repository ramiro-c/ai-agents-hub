# Soccer Analytics Agent — Phase 8 Design: Deploy to GCP

> **Design doc (spec-level).** Final phase of the roadmap. Takes the agent from a
> local docker-compose + CLI/localhost setup to a single publicly reachable Cloud
> Run service backed by Cloud SQL. The implementation plan is generated from this
> document via the writing-plans skill.

## Goal

Deploy the working agent (backend agent loop + React frontend, both complete) to
GCP so it is reachable at a public URL, without changing agent behavior. Managed
Postgres (Cloud SQL + pgvector) holds the migrated 49k-document dataset; Gemini is
reached via Vertex AI using the service account already attached at deploy time.

**Primary deliverable is understanding the deploy mechanics, not production
hardening.** We favor a topology that teaches the build → registry → run pipeline
and the Cloud Run ↔ Cloud SQL ↔ Secret Manager wiring, over a fully productionized
multi-service stack. Cost is not the driver (GCP credits available); simplicity and
clarity are.

## Decisions (settled during brainstorming)

| Dimension | Choice | Rationale |
|---|---|---|
| Deploy depth | **In-between** | Single service + automated *build* (cloudbuild.yaml), scale-to-zero, read-only DB role. Not always-on multi-service. |
| Topology | **One Cloud Run service** | FastAPI serves `/api/*` **and** the static React bundle at `/`. Same-origin ⇒ no CORS in prod, no frontend code change (paths already relative). |
| Data migration | **`pg_dump` local → `pg_restore` to Cloud SQL** | Embeddings for 49k docs are already computed and deterministic; re-embedding via `generate_documents.py` is the expensive step and buys nothing. Re-running scripts stays documented as the from-scratch fallback. |
| CI | **`cloudbuild.yaml` + manual `gcloud builds submit`** | Learning-first: you see each build step without the GitHub-trigger magic. The auto-trigger is one connection away if wanted later. |
| Availability | **Scale-to-zero default; `min-instances=1` for demos** | A flag, not an architecture change. ~$0 idle; warm during demos. |
| Region | **`us-central1`** | Same as Vertex AI already uses — avoids cross-region latency and egress. |
| DB secret | **Whole `DATABASE_URL` as one Secret Manager secret** | Simpler than a bare password; one thing to rotate. `db.py` reads `DATABASE_URL` unchanged. |
| Vertex auth | **Attached service account, no ADC file in image** | `soccer-agent@…` (`aiplatform.user`) resolves via the metadata server on Cloud Run. `.secrets/adc-personal.json` stays local-only. |

## Architecture

```
                    ┌─────────────────────── Cloud Run (1 service) ───────────────────────┐
                    │  container: uvicorn → FastAPI                                        │
   public URL ────► │    /api/*          agent loop (respond → run_turn → tools)           │
                    │    / (StaticFiles) React dist (built into the image)                 │
                    └───────┬─────────────────────────────────────────┬───────────────────┘
                            │ unix socket                              │ ADC via metadata server
                            │ /cloudsql/PROJECT:REGION:INSTANCE        │ (attached SA)
                            ▼                                          ▼
                   Cloud SQL (Postgres 16 + pgvector)          Vertex AI → Gemini
                     matches / goalscorers / shootouts
                     match_documents (vec 384 + tsv, HNSW+GIN)
                     team_elo
                     working / episodic / semantic_memory
                            ▲
                   Secret Manager ── DATABASE_URL ──► injected as env var
                   Artifact Registry ── image ──► pulled by Cloud Run at deploy
```

No agent-logic modules change. The deploy is packaging + infrastructure around the
existing framework-free loop.

## Container image (multi-stage Dockerfile)

- **Stage 1 (node):** `npm ci && npm run build` in `frontend/` → produces `dist/`.
- **Stage 2 (python + uv):** install deps from `pyproject.toml`, copy `soccer_agent/`
  + `backend/`, copy `dist/` from stage 1, and **bake the models into the image**:
  the MiniLM `all-MiniLM-L6-v2` weights and the trained XGBoost artifact, so cold
  starts do not download anything. Entrypoint: `uvicorn backend.main:app`.

Baking the models keeps cold start fast and makes the image self-contained — it
runs the same offline as it does on Cloud Run.

## Data flow

**Migration (one-shot, from the developer machine):**
`pg_dump` local Postgres (matches/goalscorers/shootouts, `match_documents` **with
embeddings**, `team_elo`; memory tables schema-only) → create Cloud SQL instance +
database + `CREATE EXTENSION vector` → `pg_restore` through the Cloud SQL Auth Proxy
→ HNSW + GIN indexes rebuild during restore. Memory tables land empty (schema, not
data).

**Serving (per request, unchanged logic):**
browser → Cloud Run `/api/chat` → `respond()` → `run_turn` → tools → Cloud SQL over
the unix socket; Gemini over Vertex with credentials from the attached SA. The React
bundle is served by the same service at `/`.

## Secrets & auth

- **Database:** `DATABASE_URL` (contains password and `host=/cloudsql/…`) stored in
  Secret Manager, injected with `gcloud run deploy --set-secrets`. `soccer_agent/db.py`
  is unchanged — it already reads `DATABASE_URL` and falls back to the local default.
- **Vertex:** deploy with `--service-account soccer-agent@…` and
  `--set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=…,GOOGLE_CLOUD_LOCATION=us-central1`.
  No credential file in the image; ADC resolves to the attached SA.
- **DB role:** create a read-only role for the app's connection (SELECT on data
  tables, write only on the three memory tables). This is the real enforcement of
  the `sql_query` read-only invariant that was deferred from the conventions.

## Build & deploy (manual, learning-first)

1. `cloudbuild.yaml` — build the multi-stage image, push to **Artifact Registry**
   (`us-central1-docker.pkg.dev/PROJECT/soccer-agent/…`).
2. `gcloud builds submit` — build in Cloud Build (ephemeral VM), image lands in
   Artifact Registry (versioned; older images remain for rollback).
3. `gcloud run deploy` with: `--image`, `--region us-central1`,
   `--add-cloudsql-instances`, `--set-secrets`, `--set-env-vars`,
   `--service-account`, `--allow-unauthenticated`. Cloud Run pulls the image and runs
   it; it never builds.

Rollback = redeploy a previous Artifact Registry image tag/digest. No auto GitHub
trigger; the `cloudbuild.yaml` leaves it one connection away.

## Code / config changes (minimal)

- **`backend/main.py`:** mount `StaticFiles` at `/` serving the built `dist/`, with an
  `index.html` fallback so the SPA loads on any path. `/api/*` routes are registered
  before the catch-all. CORS middleware stays only for local dev (harmless in prod
  since prod is same-origin).
- **No change** to `db.py`, `chat.py`, `loop.py`, `tools.py`, or the frontend
  (`api.ts` already uses relative `/api/*` paths).
- **New files:** `Dockerfile`, `.dockerignore`, `cloudbuild.yaml`, and a deploy
  runbook (`docs/deploy.md`) capturing the exact gcloud commands and the migration
  steps so the deploy is reproducible.

## Error handling & resilience

- **Loop hardening (deferred from Phase 5, do it here):** `run_turn` assumes
  `response.candidates[0]` and non-`None` `content.parts`. A safety block or
  `MAX_TOKENS` finish can crash it. Guard both before exposing a public endpoint.
- **DB unreachable:** `/api/health` already returns 503 on a failed `SELECT 1`; use it
  as the Cloud Run startup/liveness probe.
- **Missing secret / SA misconfig:** surfaces as a 500 from the agent endpoint; the
  runbook lists the exact env/secret/SA flags to check.

## Testing & verification

Per project convention (behavior-first). This phase is infra, so verification is
end-to-end against the deployed URL rather than new unit tests:

- Extend `scripts/smoke_test.py` to target a `BASE_URL` (default localhost, override
  for the Cloud Run URL): assert `/api/health` is `ok`, and a real `/api/chat`
  returns a **grounded** answer (contains digits — tightening the known weak
  assertion, another deferred gotcha closed here).
- Verify via `/api/sessions/{id}/trace` that a deployed turn actually invoked a tool
  (e.g. `sql_query` or `predict_match`), proving Vertex + Cloud SQL + models all work
  in the container.
- Confirm the React app loads from `/` and its relative API calls resolve same-origin.
- Existing offline unit tests must still pass (`uv run pytest -q`); the loop-hardening
  change gets a regression test (empty `candidates` / `None` parts → graceful message,
  no crash).

## Out of scope (v1)

- GitHub-connected Cloud Build auto-trigger (file leaves it one step away).
- Separate frontend service / CDN / custom domain / HTTPS cert management (Cloud Run
  gives a managed HTTPS URL).
- Always-on / autoscaling tuning beyond the demo `min-instances` flag.
- Private IP / VPC connector for Cloud SQL (unix socket connector is enough).
- CI test gating, staging environment, blue-green deploys.

## Success criteria

1. The agent is reachable at a public Cloud Run URL; the React app loads and chats.
2. A deployed `/api/chat` turn returns a grounded answer and its trace shows a real
   tool call — proving Vertex, Cloud SQL (pgvector retrieval), and the baked models
   all work in the container.
3. The 49k `match_documents` (with embeddings) and `team_elo` are present in Cloud SQL
   with HNSW + GIN indexes rebuilt; hybrid retrieval returns results.
4. Secrets and Vertex auth come from Secret Manager + the attached SA — no credential
   files baked into the image.
5. `run_turn` no longer crashes on empty `candidates` / `None` parts (regression test).
6. A deploy runbook documents the exact build, migrate, and deploy commands so the
   whole thing is reproducible from scratch.
