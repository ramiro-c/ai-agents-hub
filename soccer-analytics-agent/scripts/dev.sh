#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cleanup() {
  kill $BACKEND_PID 2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  wait $BACKEND_PID 2>/dev/null || true
  wait $FRONTEND_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting backend on :8081..."
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8081 --reload &
BACKEND_PID=$!
sleep 2

echo "Starting frontend on :5173..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  Backend  → http://127.0.0.1:8081"
echo "  Frontend → http://127.0.0.1:5173"
echo "  API docs → http://127.0.0.1:8081/docs"
echo ""
echo "Press Ctrl+C to stop."

wait
