#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cleanup() {
  echo ""
  echo "Deteniendo servicios..."
  [[ -n "${ADK_PID:-}" ]] && kill "$ADK_PID" 2>/dev/null || true
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [[ ! -f "$ROOT/agent/.env" ]]; then
  echo "Falta agent/.env — copiá agent/.env.example y agregá OPENROUTER_API_KEY"
  exit 1
fi

if [[ ! -d "$ROOT/agent/.venv" ]]; then
  echo "Creando venv del agente..."
  python3 -m venv "$ROOT/agent/.venv"
  "$ROOT/agent/.venv/bin/pip" install -r "$ROOT/agent/requirements.txt"
fi

if [[ ! -d "$ROOT/backend/.venv" ]]; then
  echo "Creando venv del backend..."
  python3 -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "Instalando dependencias del frontend..."
  (cd "$ROOT/frontend" && npm install)
fi

echo "Iniciando ADK api_server en :8000..."
(
  cd "$ROOT/agent"
  source .venv/bin/activate
  adk api_server --allow_origins http://localhost:5173 --auto_create_session .
) &
ADK_PID=$!

sleep 3

echo "Iniciando backend en :8080..."
(
  cd "$ROOT/backend"
  source .venv/bin/activate
  uvicorn main:app --host 127.0.0.1 --port 8080
) &
BACKEND_PID=$!

sleep 2

echo "Iniciando frontend en :5173..."
(
  cd "$ROOT/frontend"
  npm run dev -- --host 127.0.0.1
) &
FRONTEND_PID=$!

echo ""
echo "Listo:"
echo "  Frontend → http://localhost:5173"
echo "  Backend  → http://localhost:8080/api/health"
echo "  ADK      → http://localhost:8000/docs"
echo ""
echo "Ctrl+C para detener todo."

wait
