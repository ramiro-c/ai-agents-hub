# Career Coach

Agente [ADK](https://google.github.io/adk-docs/) que arma **planes de carrera a N meses** con Gemini 2.5 Flash. Hace *tool calling* real (no inventa números) y expone su *thinking* nativo. Se deploya a **Vertex AI Agent Engine**, y una UI (React + FastAPI con `POST /api/chat` en JSON) corre como **un único servicio en Cloud Run**. La UI usa un login liviano por email y muestra un listado de sesiones por usuario.

---

## Arquitectura

```
                    HTTPS (mismo origen)
   ┌─────────┐      /        /api/chat        /api/sessions         ┌──────────────────────────┐
   │ Browser │ ────────────────────────────────────────────────────▶│  Cloud Run service          │
   └─────────┘   ◀──────────────── JSON ───────────────────────────│  ┌──────────────────────┐ │
                                                                  │  │ FastAPI (backend)     │ │
                                                                  │  │  · sirve frontend     │ │
                                                                  │  │  · POST /api/chat      │ │
                                                                  │  │  · GET/DELETE sessions │ │
                                                                  │  └──────────┬───────────┘ │
                                                                  └─────────────┼─────────────┘
                                                                                │ stream_query / sessions API (ADC)
                                                                                ▼
                                                          ┌───────────────────────────────────┐
                                                          │ Vertex AI Agent Engine             │
                                                          │  career_coach (ADK + BuiltInPlanner)│
                                                          │  ├─ Gemini 2.5 Flash (+ thinking)   │
                                                          │  └─ tools: timeline / effort / gap  │
                                                          └───────────────────────────────────┘
```

- **Auth sin secretos**: el backend habla con Agent Engine vía **ADC** (local) o el **service account** de Cloud Run (prod). No hay API keys en ningún lado.
- **Mismo origen**: Cloud Run sirve el frontend estático y el `/api`, así que no hay CORS ni URLs cruzadas en prod.
- **SPA nativa**: el backend sirve el build con [`app.frontend()`](https://fastapi.tiangolo.com/tutorial/frontend/) (FastAPI ≥ 0.138). Los assets faltantes dan 404 real y la navegación de browser cae a `index.html` (client-side routing), sin el viejo hack de `StaticFiles(html=True)`. Las rutas `/api` siempre tienen prioridad.
- **Contrato JSON**: el backend responde a `POST /api/chat` con un JSON completo. La UI mantiene los mismos paneles visibles, pero ahora el pensamiento, las tools y el markdown llegan juntos al final del request.
- **Sesiones por email**: el email del login liviano se usa como `userId`. Eso permite listar, abrir y borrar sesiones sin una base de datos propia.

---

## Estructura

```
career-coach/
├── agent/                 # Agente ADK (self-contained, deployable)
│   ├── agent.py           #   root_agent + 3 tools inline
│   ├── requirements.txt   #   google-adk[a2a]==2.2.0  (el extra a2a es obligatorio, ver Troubleshooting)
│   ├── .env.example       #   env para correr el agente en LOCAL contra Vertex
│   └── .env.deploy        #   env VACÍO a propósito para `adk deploy` (evita choque de flags)
├── backend/               # FastAPI (>=0.138): POST JSON + sirve el SPA con app.frontend()
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/              # React 19 + Vite 6 + TypeScript
│   ├── src/App.tsx        #   login por email + sidebar de sesiones + chat markdown
│   ├── src/api.ts         #   consumidor JSON (chat + sessions API)
│   └── ...
├── scripts/dev.sh         # levanta backend :8080 + frontend :5173
├── Dockerfile             # multi-stage: build frontend → runtime backend + estáticos
└── .dockerignore
```

---

## Las 3 tools

El agente **no inventa números**: delega los cálculos en funciones deterministas.
Además, **no le pide al usuario que liste las skills requeridas**: infiere esa parte con conocimiento propio del rol objetivo y después usa `skill_gap_analysis`.

| Tool | Firma | Devuelve |
|---|---|---|
| `skill_gap_analysis` | `(current_skills, required_skills)` | `have`, `missing`, `coverage_pct` |
| `estimate_learning_effort` | `(total_hours, hours_per_week)` | `weeks`, `months`, `estimated_finish` (fecha ISO) |
| `build_career_timeline` | `(total_months, phases)` | reparte el horizonte en fases con rangos de meses (`"1-3"`, `"4-6"`, …) |

El *planner* es `BuiltInPlanner` con `ThinkingConfig(include_thoughts=True)`, por eso el razonamiento de Gemini se puede mostrar en la UI.

---

## Contrato JSON

`POST /api/chat` con body:

```json
{ "message": "string", "userId": "string?", "sessionId": "string?" }
```

Responde un JSON completo con estos campos:

| Campo | Tipo | Uso |
|---|---|---|
| `userId` | `string` | identifica al usuario; si no viene en la request, el backend genera uno nuevo |
| `sessionId` | `string` | sesión del Agent Engine que permite continuar la conversación |
| `answer` | `string` | respuesta final en markdown |
| `thoughts` | `string` | razonamiento acumulado para el panel de pensamiento |
| `tools` | `array` | lista de tools invocadas, con `name`, `args` y `response` |

La UI mantiene exactamente el mismo layout visible: panel de pensamientos, panel de tools y la respuesta en markdown. Lo único que cambió es el timing: todo aparece cuando termina el request, no de forma incremental.

### Sesiones

- `GET /api/sessions?userId=email` lista las sesiones del usuario autenticado por email.
- `GET /api/sessions/{sessionId}?userId=email` devuelve el historial reconstruido de esa sesión.
- `DELETE /api/sessions/{sessionId}?userId=email` borra la sesión.

El sidebar usa el email como `userId`, deriva el título de cada sesión desde el primer mensaje del usuario. El email se persiste en `localStorage` (para no re-loguear en cada visita); la sesión activa vive solo en memoria del frontend, así "Nueva conversación" siempre arranca limpia.

---

## Requisitos

- **Python 3.11+**, **Node 20+**, **gcloud CLI**.
- Proyecto GCP con **Vertex AI habilitado** y **billing** activo.
- **ADC** configurado apuntando al proyecto correcto:
  ```bash
  gcloud auth application-default login
  gcloud auth application-default set-quota-project YOUR_PROJECT_ID
  ```

---

## Correr en local

```bash
cd career-coach
cp backend/.env.example backend/.env    # completá con los valores de tu proyecto
./scripts/dev.sh
```

`dev.sh` es idempotente: la primera vez crea el venv del backend, corre `npm install` y luego levanta:

- **Frontend** → http://localhost:5173  ← abrí esto
- **Backend** → http://localhost:8080/api/health

`Ctrl+C` frena ambos. El frontend proxya `/api` → `:8080` en local.

> Local **también consume el Agent Engine deployado** (que tiene costo mientras exista). No levanta el modelo localmente.

### Probar solo el agente (sin UI)

```bash
cd agent
GOOGLE_GENAI_USE_VERTEXAI=TRUE \
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID \
GOOGLE_CLOUD_LOCATION=us-central1 \
  adk run .
```

---

## Deploy

### 1. Agente → Agent Engine

```bash
cd career-coach
adk deploy agent_engine \
  --project=YOUR_PROJECT_ID \
  --region=YOUR_REGION \
  --staging_bucket=gs://YOUR_PROJECT_ID-adk-staging \
  --display_name="Career Coach" \
  --env_file=agent/.env.deploy \
  agent
```

Guardá el `reasoningEngines/...` que devuelve y actualizá `AGENT_ENGINE_RESOURCE` en `backend/.env` (local) y en el `--set-env-vars` de Cloud Run (prod).

### 2. UI → Cloud Run

Requiere (una vez): APIs `run`, `cloudbuild`, `artifactregistry` habilitadas, y el rol Vertex para el service account de runtime:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  --project=YOUR_PROJECT_ID

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user" --condition=None
```

Deploy desde el fuente (Cloud Build construye el `Dockerfile`):

```bash
gcloud run deploy YOUR_SERVICE_NAME \
  --source=career-coach \
  --region=YOUR_REGION \
  --project=YOUR_PROJECT_ID \
  --allow-unauthenticated --memory=1Gi --cpu=1 --timeout=300 \
  --set-env-vars=GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,GOOGLE_CLOUD_LOCATION=YOUR_REGION,AGENT_ENGINE_RESOURCE=projects/YOUR_PROJECT_NUMBER/locations/YOUR_REGION/reasoningEngines/YOUR_ENGINE_ID
```

---

## Variables de entorno

**Backend** (`backend/.env`, y `--set-env-vars` en Cloud Run):

| Var | Requerida | Descripción |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | ✅ | proyecto GCP |
| `AGENT_ENGINE_RESOURCE` | ✅ | resource name completo del Agent Engine |
| `GOOGLE_CLOUD_LOCATION` | — | región (default `us-central1`) |
| `FRONTEND_ORIGIN` | — | origen permitido para CORS (default `http://localhost:5173`; irrelevante en prod porque es mismo origen) |
| `STATIC_DIR` | — | carpeta del frontend build (default `static`; el Dockerfile la setea) |

---

## Troubleshooting

Problemas reales que aparecen al deployar esto y cómo se resuelven:

- **`adk deploy` falla con `No module named 'vertexai'`**
  El venv desde el que corrés el CLI no tiene el SDK. Instalá:
  `pip install "google-cloud-aiplatform[agent_engines]"`.

- **El Reasoning Engine "failed to start / cannot serve traffic"**
  Mirá los logs:
  `gcloud logging read 'resource.labels.reasoning_engine_id="<ID>"' --project=<PROJ> --freshness=1h`.
  El caso típico es `ModuleNotFoundError: No module named 'a2a'`: el runtime de ADK necesita el extra a2a. Por eso `agent/requirements.txt` usa **`google-adk[a2a]==2.2.0`**, no `google-adk` pelado.

- **Warning `--staging_bucket / --env_file / --requirements_file is deprecated`**
  Son solo avisos; los flags siguen funcionando. Usamos `--env_file=agent/.env.deploy` (archivo vacío) para que `GOOGLE_CLOUD_*` de un `.env` no choque con `--project/--region`.

- **`PERMISSION_DENIED` sobre `aiplatform.endpoints.predict` en local**
  ADC mal configurado (proyecto por defecto distinto o sin quota project). Reautenticá:
  `gcloud auth application-default login` + `... set-quota-project <PROJ>`.

- **Cloud Run arranca pero devuelve 5xx al chatear**
  El service account de runtime no tiene `roles/aiplatform.user`. Concedelo (ver [Deploy → UI](#2-ui--cloud-run)).

---

## Costos y limpieza

Cloud Run **escala a cero** (prácticamente gratis en reposo), pero el **Agent Engine tiene costo mientras exista**. Cuando termines de probar, borrá ambos:

```bash
# Agent Engine
python -c "from vertexai import agent_engines; \
agent_engines.get('projects/YOUR_PROJECT_NUMBER/locations/YOUR_REGION/reasoningEngines/YOUR_ENGINE_ID').delete(force=True)"

# Cloud Run
gcloud run services delete YOUR_SERVICE_NAME --region=YOUR_REGION --project=YOUR_PROJECT_ID
```
