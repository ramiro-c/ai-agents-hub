# Deploy to GCP — Phase 8 runbook (soccer-analytics-agent)

> **GUARD — READ FIRST.** Your active gcloud project is **`astra-suplementos`**.
> Every single `gcloud` command below passes `--project gen-lang-client-0049374628`
> (abbreviated `$P`) explicitly. Do NOT rely on the active project, and do NOT
> run any gcloud command without the explicit `--project $P` flag. A mistargeted
> command could deploy to or mutate the wrong project.

This runbook reproduces the full path from a fresh machine to a public Cloud Run
URL serving the React frontend at `/` and the agent API under `/api/*`:

```
browser → Cloud Run uvicorn → /api/* → respond → run_turn → tools
                             └ / (StaticFiles) React dist   (same-origin)
tools → Cloud SQL via /cloudsql/PROJECT:REGION:INST unix socket (DATABASE_URL secret)
Gemini → Vertex via metadata-server ADC (soccer-agent service account)
```

The agent stack is entirely stateless beyond Postgres: the container bakes the
models, the Elo data, and the frontend; the database holds the match data and
per-session memory/traces. Rollback is a redeploy of a previous image digest.

---

## 1. Prerequisites

- Local: `docker`, `gcloud` (authenticated, `gcloud auth login`), `uv`, and the
  repo cloned with the Phase 0–7 data pipeline working.
- Local Postgres up with the full dataset (`docker compose up -d`, then
  `scripts/load_data.py` / `scripts/generate_documents.py` /
  `scripts/compute_elos.py` if starting from scratch).
- GCP: billing enabled on project `gen-lang-client-0049374628` (Adk Labs).
  Free-trial Cloud SQL eligibility is confirmed at instance creation.
- `.env` present locally with the Vertex settings
  (`GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`,
  `GOOGLE_CLOUD_LOCATION=us-central1`, isolated ADC file under `.secrets/`).

Set the project shorthand once:

```bash
export P=gen-lang-client-0049374628
```

## 2. One-time GCP setup

```bash
# 2.1 Enable the APIs (run, artifactregistry, sqladmin, secretmanager, cloudbuild)
gcloud services enable sqladmin secretmanager run cloudbuild artifactregistry.googleapis.com --project $P

# 2.2 Artifact Registry repo (docker, us-central1)
gcloud artifacts repositories create soccer-agent --repository-format docker --location us-central1 --project $P

# 2.3 Cloud Build SA -> Artifact Registry writer
PN=$(gcloud projects describe $P --format='value(projectNumber)')
gcloud projects add-iam-policy-binding $P --member serviceAccount:$PN@cloudbuild.gserviceaccount.com --role roles/artifactregistry.writer

# 2.4 Cloud SQL instance (POSTGRES_16, pgvector built in)
#     Free-trial tier db-f1-micro preferred; if ineligible, use db-g1-small (~$25/mo).
gcloud sql instances create soccer-agent-db --project $P --region us-central1 --database-version POSTGRES_16 --tier db-f1-micro --root-password "$(openssl rand -base64 24)"

# 2.5 IAM for the app service account (Vertex aiplatform.user already granted)
gcloud projects add-iam-policy-binding $P --member serviceAccount:soccer-agent@$P.iam.gserviceaccount.com --role roles/cloudsql.client
gcloud projects add-iam-policy-binding $P --member serviceAccount:soccer-agent@$P.iam.gserviceaccount.com --role roles/secretmanager.secretAccessor
```

## 3. Build

```bash
# From the soccer-analytics-agent project root.
# The multi-stage image builds the React dist, uv-syncs the Python deps,
# bakes MiniLM weights + the XGBoost joblib, and keeps the repo-relative
# layout (/app) so db.py and the SPA mount resolve unchanged.
gcloud builds submit --project $P --config cloudbuild.yaml \
  --substitutions _TAG=$(git rev-parse --short HEAD)
```

Timeout is 1800s in `cloudbuild.yaml` — the torch/lightgbm wheels are large.

## 4. Migrate the database

```bash
# 4.1 Dump the local DB (224MB: 49,505 matches, 47,891 goalscorers,
#     682 shootouts, 49,510 match_documents + embeddings, 336 team_elo)
pg_dump -Fc -d postgresql://soccer:soccer@localhost:5433/soccer -f /tmp/soccer.dump

# 4.2 Tunnel to Cloud SQL with the Auth Proxy
#     (install: https://cloud.google.com/sql/docs/mysql/sql-proxy)
cloud-sql-proxy $P:us-central1:soccer-agent-db --port 5432 &
#     Wait for the proxy to report ready, then:

# 4.3 Create the database
psql -h localhost -p 5432 -U postgres -c "CREATE DATABASE soccer;"

# 4.4 Restore the full dump AS postgres (--no-owner).
#     The dump includes CREATE EXTENSION vector, which only the
#     cloudsqlsuperuser (postgres) can run — restoring as an app role fails.
pg_restore -h localhost -p 5432 -U postgres -d soccer --no-owner /tmp/soccer.dump

# 4.5 Drop local session data — Cloud SQL starts with clean memory/traces
psql -h localhost -p 5432 -U postgres -d soccer -c "TRUNCATE working_memory, episodic_memory, semantic_memory, agent_trace;"

# 4.6 App role: read-only on data tables, INSERT-only on the write tables.
#     GRANT USAGE ON ALL SEQUENCES is required — memory/trace inserts use
#     BIGSERIAL nextval and 500 without it.
APP_PASS=$(openssl rand -base64 18)
psql -h localhost -p 5432 -U postgres -d soccer -v ON_ERROR_STOP=1 -c \
  "CREATE ROLE soccer_app LOGIN PASSWORD '$APP_PASS';
   GRANT SELECT ON matches, goalscorers, shootouts, match_documents, team_elo TO soccer_app;
   GRANT INSERT ON working_memory, episodic_memory, semantic_memory, agent_trace TO soccer_app;
   GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO soccer_app;"

# 4.7 Verify the migration
psql -h localhost -p 5432 -U postgres -d soccer -c \
  "SELECT (SELECT count(*) FROM matches) AS matches,
          (SELECT count(*) FROM match_documents) AS docs,
          (SELECT count(*) FROM team_elo) AS elos;"
# Expect: 49505 | 49510 | 336
psql -h localhost -p 5432 -U postgres -d soccer -c \
  "SELECT indexname, indexdef FROM pg_indexes WHERE tablename IN ('match_documents','team_elo');"
# Expect HNSW (vector) + GIN (tsvector) indexes restored.
```

## 5. Create the DATABASE_URL secret

```bash
# Whole connection string as ONE secret (unix-socket host; db.py unchanged)
printf 'postgresql://soccer_app:%s@/soccer?host=/cloudsql/%s:us-central1:soccer-agent-db' "$APP_PASS" "$P" \
  | gcloud secrets create DATABASE_URL --project $P --data-file=-
```

> `APP_PASS` must stay in scope from step 4.6 — if you opened a new shell,
> re-derive it from the value you set in `CREATE ROLE`.

## 6. Deploy to Cloud Run

```bash
# Full flags: public URL, 600s timeout (model calls), 2Gi memory (models),
# min-instances 1 (warm demos; scale-to-zero = change 1 -> 0),
# Cloud SQL unix socket attached, DATABASE_URL from Secret Manager,
# attached service account for Vertex — NO GOOGLE_APPLICATION_CREDENTIALS:
# genai.Client() picks up the SA via the metadata server.
gcloud run deploy soccer-agent --project $P --region us-central1 \
  --image us-central1-docker.pkg.dev/$P/soccer-agent/soccer-agent:$_TAG \
  --allow-unauthenticated --timeout 600 --memory 2Gi --min-instances 1 \
  --add-cloudsql-instances $P:us-central1:soccer-agent-db \
  --set-secrets DATABASE_URL=projects/$P/secrets/DATABASE_URL:latest \
  --service-account soccer-agent@$P.iam.gserviceaccount.com \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$P,GOOGLE_CLOUD_LOCATION=us-central1

# Print the service URL
gcloud run services describe soccer-agent --project $P --region us-central1 \
  --format='value(status.url)'
```

## 7. Verify (deployed)

```bash
# Grounded smoke test against the public URL — asserts health ok, chat answer
# contains digits, and the session trace shows >=1 real tool call.
SMOKE_TEST_BASE_URL=<service-url> uv run python scripts/smoke_test.py
# Expected output: "SMOKE TEST OK"
```

Optional manual checks:

```bash
curl -s <service-url>/api/health                      # {"status":"ok","db":"connected"}
curl -s <service-url>/                                # React index.html
curl -s <service-url>/client/some/deep/route          # index.html (SPA fallback)
curl -s <service-url>/api/nope                        # JSON 404, not HTML
```

Health contract: Cloud Run's TCP probe passes as long as uvicorn listens;
`/api/health` returning **503** when the DB is unreachable is the app-level
liveness signal (agent errors surface, the process does not crash).

## 8. Teardown / stop

- **Free-trial instance (db-f1-micro)**: auto-stops when idle — nothing to do
  between demos.
- **Paid fallback (db-g1-small)**: stop it when not demoing to avoid ~$25/mo:
  ```bash
  gcloud sql instances patch soccer-agent-db --project $P --activation-policy NEVER
  # re-enable with:  ... --activation-policy ALWAYS
  ```
- Full teardown (delete everything):
  ```bash
  gcloud run services delete soccer-agent --project $P --region us-central1
  gcloud sql instances delete soccer-agent-db --project $P
  gcloud artifacts repositories delete soccer-agent --location us-central1 --project $P
  gcloud secrets delete DATABASE_URL --project $P
  ```

## 9. Rollback

The app is stateless beyond the DB, so rollback is a redeploy of the previous
image digest with the same flags:

```bash
# Find the previous digest
gcloud artifacts docker images list us-central1-docker.pkg.dev/$P/soccer-agent/soccer-agent \
  --project $P --include-tags
# Redeploy it
gcloud run deploy soccer-agent --project $P --region us-central1 \
  --image us-central1-docker.pkg.dev/$P/soccer-agent/soccer-agent:<prev-digest-or-tag> \
  --allow-unauthenticated --timeout 600 --memory 2Gi --min-instances 1 \
  --add-cloudsql-instances $P:us-central1:soccer-agent-db \
  --set-secrets DATABASE_URL=projects/$P/secrets/DATABASE_URL:latest \
  --service-account soccer-agent@$P.iam.gserviceaccount.com \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$P,GOOGLE_CLOUD_LOCATION=us-central1
```

DB rollback: use a Cloud SQL backup or re-run the migration (section 4). Code
rollback: revert the deploy commits; the unit suite stays green.

## 10. Cost notes

| Item | Cost |
|---|---|
| Cloud Run (min-instances 1, 2Gi, e2-small-ish) | ~$15–30/mo always-on |
| Cloud SQL db-f1-micro (free-trial) | $0 while eligible; auto-stops |
| Cloud SQL db-g1-small (fallback) | ~$25/mo; stop when idle (`--activation-policy NEVER`) |
| Vertex Gemini calls | Pay-per-token, demo volumes are negligible |
| Artifact Registry storage | Negligible at this image count |

## 11. Notes / follow-ups

- **LFS**: the 5.9MB `data/xgboost_match_predictor.joblib` is committed with
  `git add -f` for reproducible fresh-clone builds. Follow up with Git LFS if
  the monorepo grows.
- **Scale-to-zero** is one flag: `gcloud run deploy ... --min-instances 0`.
- **Missing joblib at predict time** → `predict_match` falls back to the Elo
  heuristic; the service still answers.
- **Secret hygiene**: `.secrets/` and `.env` are excluded by `.dockerignore`;
  no credential files ship in the image.
- The service is public and unauthenticated by design (demo). Put it behind
  IAP or an ingress restriction before exposing real data.
