#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cleanup() {
  echo ""
  echo "Deteniendo servicios..."
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [[ ! -f "$ROOT/backend/.env" ]]; then
  echo "Falta backend/.env — copia backend/.env.example y completa AGENT_ENGINE_RESOURCE"
  exit 1
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
echo "  Frontend -> http://localhost:5173"
echo "  Backend  -> http://localhost:8080/api/health"
echo ""
echo "Ctrl+C para detener todo."

wait
