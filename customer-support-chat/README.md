# Customer Support Chat

Chat web con un agente de soporte construido con [Google ADK](https://google.github.io/adk-docs/), OpenRouter y un mini backend FastAPI.

## Arquitectura

```
Browser (Vite :5173) → Backend FastAPI (:8080) → ADK api_server (:8000) → OpenRouter
```

- **frontend/** — UI de chat en React
- **backend/** — proxy HTTP; el browser nunca ve la API key de OpenRouter
- **agent/** — agente ADK (`root_agent`) con instrucciones en español

## Prerequisitos

- Python 3.11+
- Node.js 20+
- API key de [OpenRouter](https://openrouter.ai/)

## Setup rápido

```bash
# 1. Agente
cp .env.example agent/.env   # pegar OPENROUTER_API_KEY
cd agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Backend (otra terminal)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Frontend (otra terminal)
cd frontend
npm install
```

## Desarrollo

Opción A — script que levanta los 3 servicios:

```bash
./scripts/dev.sh
```

Opción B — manual (3 terminales):

```bash
# Terminal 1 — ADK API
cd agent && source .venv/bin/activate
adk api_server --allow_origins http://localhost:5173 --auto_create_session .

# Terminal 2 — Backend
cd backend && source .venv/bin/activate
uvicorn main:app --reload --port 8080

# Terminal 3 — Frontend
cd frontend && npm run dev
```

Abrir http://localhost:5173

## Probar el backend con curl

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "No puedo iniciar sesión"}'
```

## Deploy (referencia)

| Componente | Destino sugerido |
|------------|------------------|
| `agent/` | Cloud Run (`adk deploy cloud_run`) |
| `backend/` | Cloud Run / Railway / Fly.io |
| `frontend/` | Vercel / Cloudflare Pages (build estático) |

Configurar `OPENROUTER_API_KEY` como secreto en el entorno del agente. El backend apunta a la URL del ADK deployado vía `ADK_API_URL`.
