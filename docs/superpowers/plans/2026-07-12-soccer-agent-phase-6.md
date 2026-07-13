# Soccer Analytics Agent — Phase 6: FastAPI + React Frontend

> **For agentic workers:** Implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the CLI REPL with a polished web chat interface — same agent, same DB, same loop, but accessible through a browser. This is the "from REPL to product" phase.

**Architecture:** Add a FastAPI backend that wraps `chat.py respond()` behind REST endpoints, and a React frontend with a chat UI, session sidebar, and tool-call panels. The agent loop, tools, and DB stay exactly as they are — the backend is a thin adapter, not a rewrite.

**Reference:** `career-coach/` — same stack (FastAPI + React + Vite), same pattern (backend proxying agent, frontend consuming it). We replicate the proven structure.

**Tech Stack:**
- Backend: FastAPI + uvicorn (already in pyproject.toml via career-coach)
- Frontend: React 19 + TypeScript + Vite + react-markdown
- Dev: `scripts/dev.sh` launches both processes

## Architecture

```
Browser (React :5173) → Vite proxy → FastAPI (:8080) → chat.py respond() → Gemini + tools → Postgres
```

The React dev server proxies `/api/*` to FastAPI. In production (Phase 8), FastAPI serves the built React app directly.

**Key differences from career-coach:**
- No Vertex AI / Agent Engine — our loop is local and hand-written
- No ADC auth — just a simple session-based approach
- Sessions are DB-native (Postgres `working_memory.session_id`), not Vertex-managed
- We expose tracing data via API (Phase 5 observability now visible in the UI)

## Backend Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send message, get agent response |
| GET | `/api/sessions` | List active sessions |
| GET | `/api/sessions/{id}` | Get session history (messages) |
| GET | `/api/trace/{session_id}` | Get trace data for a session |
| GET | `/api/trace/{session_id}/{turn_id}` | Get trace for a specific turn |
| GET | `/api/health` | Healthcheck |

**Session model:** A session is identified by a UUID. It maps to `working_memory.session_id`. The frontend generates the UUID on first message and stores it in localStorage. No user authentication in v1 — this is a single-user dev tool.

**Chat flow:**
1. Frontend sends `{ message, sessionId }` to POST /api/chat
2. Backend calls `chat.respond(client, session_id, message, model)` — same function the CLI uses
3. Backend returns `{ sessionId, answer, tools }` — tools = trace data for this turn

## Task 1: FastAPI Backend

**Directory:** `soccer-analytics-agent/backend/`

### Step 1a: `backend/main.py` — the server

```python
"""FastAPI backend: wraps chat.py respond() behind REST endpoints.

Routes:
  GET  /api/health
  POST /api/chat
  GET  /api/sessions
  GET  /api/sessions/{session_id}
  GET  /api/trace/{session_id}
  GET  /api/trace/{session_id}/{turn_id}
"""

import asyncio
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

# Import after load_dotenv so .env is loaded before google-genai connects
from soccer_agent import chat, db, memory, trace  # noqa: E402

app = FastAPI(title="Soccer Analytics Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    sessionId: str | None = None


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] | None = None
    result: Any = None


class ChatResponse(BaseModel):
    sessionId: str
    answer: str
    tools: list[ToolCall] = []


class SessionSummary(BaseModel):
    sessionId: str
    lastMessage: str | None = None
    messageCount: int


class HistoryMessage(BaseModel):
    role: str  # "user" | "model"
    content: str


class SessionHistory(BaseModel):
    sessionId: str
    messages: list[HistoryMessage]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_tools_from_trace(session_id: str, turn_id: int) -> list[ToolCall]:
    """Extract tool calls from the trace for a turn."""
    steps = trace.get_turn_trace(session_id, turn_id)
    tools: list[ToolCall] = []
    for step in steps:
        content = step.get("content", {})
        if content.get("kind") == "tool_call":
            tools.append(ToolCall(
                name=content.get("tool_name", "?"),
                args=content.get("args"),
                result=content.get("result"),
            ))
    return tools


def _session_summary(session_id: str) -> SessionSummary:
    """Build a summary for the session list sidebar."""
    working = memory.load_working(session_id, limit=50)
    last = working[-1][1] if working else None
    if last and len(last) > 80:
        last = last[:77] + "..."
    return SessionSummary(
        sessionId=session_id,
        lastMessage=last,
        messageCount=len(working),
    )


def _session_history(session_id: str) -> SessionHistory:
    """Reconstruct full message history from working memory."""
    working = memory.load_working(session_id, limit=200)
    messages = [
        HistoryMessage(role=role, content=content)
        for role, content in working
    ]
    return SessionHistory(sessionId=session_id, messages=messages)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/sessions", response_model=list[SessionSummary])
async def list_sessions() -> list[SessionSummary]:
    """Return all distinct session IDs from working_memory as summaries."""
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT DISTINCT session_id FROM working_memory
               ORDER BY session_id DESC LIMIT 50"""
        ).fetchall()
    return [_session_summary(r[0]) for r in rows]


@app.get("/api/sessions/{session_id}", response_model=SessionHistory)
async def get_session(session_id: str) -> SessionHistory:
    return _session_history(session_id)


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest) -> ChatResponse:
    session_id = body.sessionId or f"web-{uuid.uuid4().hex[:12]}"
    model = "gemini-2.5-flash"

    try:
        answer = await asyncio.to_thread(
            chat.respond, client, session_id, body.message, model
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Extract tool calls from trace
    turn_id = trace.get_last_turn_id(session_id) or 1
    tools = _extract_tools_from_trace(session_id, turn_id)

    return ChatResponse(sessionId=session_id, answer=answer, tools=tools)


@app.get("/api/trace/{session_id}")
async def trace_session(session_id: str) -> list[dict]:
    return trace.get_session_trace(session_id)


@app.get("/api/trace/{session_id}/{turn_id}")
async def trace_turn(session_id: str, turn_id: int) -> list[dict]:
    return trace.get_turn_trace(session_id, turn_id)
```

**Important:** `chat.respond()` takes a Gemini `client` object as its first argument. We need to create one:

```python
# In main.py, after imports:
import google.generative.ai as genai  # noqa: E402

client = genai.Client()  # or however google-genai creates clients
```

Actually, check how cli.py creates the client and do the same.

### Step 1b: `backend/requirements.txt`

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
python-dotenv>=1.0.0
```

The soccer_agent package and its deps (google-genai, sentence-transformers, psycopg, pgvector) are already handled by `uv` in the parent project.

- [ ] **Step 1: Create `backend/main.py` and verify with `uv run uvicorn backend.main:app --port 8080`**

**Verify:** `curl localhost:8080/api/health` returns `{"status":"ok"}`

## Task 2: React Frontend

**Directory:** `soccer-analytics-agent/frontend/`

Replicate the career-coach pattern but simplified — no email auth, just localStorage session IDs.

### Step 2a: Project scaffold

```bash
cd soccer-analytics-agent/frontend
npm create vite@latest . -- --template react-ts
npm install
npm install react-markdown remark-gfm
```

### Step 2b: `frontend/src/api.ts` — API client

```typescript
export type ToolCall = {
  name: string;
  args: Record<string, unknown> | null;
  result: unknown;
};

export type ChatResponse = {
  sessionId: string;
  answer: string;
  tools: ToolCall[];
};

export type SessionSummary = {
  sessionId: string;
  lastMessage: string | null;
  messageCount: number;
};

export type HistoryMessage = {
  role: "user" | "model";
  content: string;
};

export type SessionHistory = {
  sessionId: string;
  messages: HistoryMessage[];
};

async function fetchJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "Error");
  }
  return (await res.json()) as T;
}

export async function sendChat(
  message: string,
  sessionId: string | null,
): Promise<ChatResponse> {
  return fetchJson<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, sessionId }),
  });
}

export async function listSessions(): Promise<SessionSummary[]> {
  return fetchJson<SessionSummary[]>("/api/sessions");
}

export async function getSessionHistory(
  sessionId: string,
): Promise<SessionHistory> {
  return fetchJson<SessionHistory>(
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
}
```

### Step 2c: `frontend/src/App.tsx` — main component

Simplified from career-coach — no email auth, no session delete, no trace viewer (keep it focused on chat for v1):

```tsx
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  getSessionHistory,
  listSessions,
  sendChat,
  type HistoryMessage,
  type SessionSummary,
  type ToolCall,
} from "./api";

const SESSION_KEY = "soccer_agent_session";

type AssistantMsg = {
  role: "assistant";
  content: string;
  tools: ToolCall[];
};

type UserMsg = { role: "user"; content: string };
type Msg = UserMsg | AssistantMsg;

export default function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(
    () => localStorage.getItem(SESSION_KEY),
  );
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Load sessions on mount
  useEffect(() => {
    let alive = true;
    setLoadingSessions(true);
    listSessions()
      .then((items) => alive && setSessions(items))
      .catch((err) => alive && setError(err.message))
      .finally(() => alive && setLoadingSessions(false));
    return () => { alive = false; };
  }, []);

  // Load session history when switching sessions
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    localStorage.setItem(SESSION_KEY, sessionId);
    setLoadingSessions(true);
    getSessionHistory(sessionId)
      .then((h) =>
        setMessages(
          h.messages.map((m) => ({
            role: m.role === "user" ? "user" : "assistant",
            content: m.content,
            tools: [],
          })),
        ),
      )
      .catch((err) => setError(err.message))
      .finally(() => setLoadingSessions(false));
  }, [sessionId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setError(null);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "", tools: [] },
    ]);
    setLoading(true);

    try {
      const res = await sendChat(text, sessionId);
      setSessionId(res.sessionId);
      setMessages((prev) => [
        ...prev.slice(0, -1),
        { role: "assistant", content: res.answer, tools: res.tools },
      ]);
      // Refresh session list
      listSessions().then(setSessions).catch(() => {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setLoading(false);
    }
  }

  function newChat() {
    const id = `web-${Date.now().toString(36)}`;
    localStorage.setItem(SESSION_KEY, id);
    setSessionId(id);
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>⚽ Soccer Agent</h1>
        </div>
        <button className="primary-btn" onClick={newChat}>
          New Chat
        </button>
        <div className="sessions-list">
          {loadingSessions && <span className="sessions-loading">Loading...</span>}
          {sessions.map((s) => (
            <div
              key={s.sessionId}
              className={`session-item ${s.sessionId === sessionId ? "active" : ""}`}
              onClick={() => setSessionId(s.sessionId)}
            >
              <strong>Session {s.sessionId.slice(0, 8)}</strong>
              <span>{s.messageCount} messages</span>
            </div>
          ))}
        </div>
      </aside>

      <section className="chat-shell">
        <header className="header">
          <h1>Soccer Analytics Agent</h1>
          <p>Gemini + PostgreSQL + pgvector · 49k international matches</p>
        </header>

        <main className="chat">
          {messages.length === 0 ? (
            <div className="empty-state">
              <h2>Ask about football!</h2>
              <p>
                Try: "What's Argentina's Elo rating?", "Predict Argentina vs France",
                "Show me recent Brazil matches", "Who won the 2022 World Cup final?"
              </p>
            </div>
          ) : (
            messages.map((msg, i) =>
              msg.role === "user" ? (
                <div key={i} className="bubble user">
                  <span className="label">You</span>
                  <p>{msg.content}</p>
                </div>
              ) : (
                <div key={i} className="bubble assistant">
                  <span className="label">Agent</span>
                  {"tools" in msg && msg.tools.length > 0 && (
                    <details className="panel tools" open>
                      <summary>Tools ({msg.tools.length})</summary>
                      {msg.tools.map((t, j) => (
                        <div key={j} className="tool">
                          <code>{t.name}</code>
                          <pre>{JSON.stringify(t.args, null, 2)}</pre>
                          {t.result !== undefined && (
                            <pre className="tool-res">
                              {JSON.stringify(t.result, null, 2)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </details>
                  )}
                  <div className="answer">
                    {loading && i === messages.length - 1 ? (
                      <p className="answer-loading">
                        {msg.content || "Thinking..."}
                      </p>
                    ) : msg.content ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    ) : null}
                  </div>
                </div>
              ),
            )
          )}
          <div ref={bottomRef} />
        </main>

        {error && <div className="error">{error}</div>}

        <form className="composer" onSubmit={handleSubmit}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about matches, teams, predictions..."
            disabled={loading}
            autoFocus
          />
          <button type="submit" disabled={loading || !input.trim()}>
            Send
          </button>
        </form>
      </section>
    </div>
  );
}
```

### Step 2d: `frontend/src/index.css` — styles

Replicate career-coach's CSS structure: sidebar left, chat right, tool panels, bubbles. Keep it clean but functional — not a design project yet.

Key classes: `.app` (flex layout), `.sidebar`, `.chat-shell`, `.chat`, `.bubble`, `.composer`, `.panel`, `.tools`, `.tool`, `.empty-state`, `.error`.

### Step 2e: `frontend/vite.config.ts` — proxy to backend

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8080",
    },
  },
});
```

- [ ] **Step 2: Create the React frontend**

## Task 3: Dev Script

**File:** `soccer-analytics-agent/scripts/dev.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"

cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID 2>/dev/null || true
    wait $FRONTEND_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "=== Starting Soccer Agent Dev Environment ==="
echo ""

# Backend
echo "[backend] Starting FastAPI on :8080..."
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload &
BACKEND_PID=$!

# Frontend
echo "[frontend] Starting Vite on :5173..."
(cd "$DIR/frontend" && npm run dev) &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8080"
echo "Frontend: http://localhost:5173"
echo ""

wait
```

- [ ] **Step 3: Create `scripts/dev.sh` and make executable (`chmod +x`)**

## Task 4: Integration Test

**File:** `tests/test_backend.py`

Use FastAPI's `TestClient` to verify the backend endpoints work end-to-end:

```python
"""Integration tests for the FastAPI backend."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


@pytest.mark.integration
@pytest.mark.requires_db
def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


@pytest.mark.integration
@pytest.mark.requires_db
def test_chat_creates_session():
    res = client.post("/api/chat", json={"message": "What is 2+2?"})
    assert res.status_code == 200
    data = res.json()
    assert "sessionId" in data
    assert "answer" in data
    assert len(data["answer"]) > 0


@pytest.mark.integration
@pytest.mark.requires_db
def test_chat_continues_session():
    # First message
    res1 = client.post("/api/chat", json={"message": "My name is TestUser"})
    sid = res1.json()["sessionId"]

    # Second message in same session
    res2 = client.post(
        "/api/chat",
        json={"message": "What is my name?", "sessionId": sid},
    )
    assert res2.status_code == 200
    assert res2.json()["sessionId"] == sid


@pytest.mark.integration
@pytest.mark.requires_db
def test_list_sessions():
    res = client.get("/api/sessions")
    assert res.status_code == 200
    sessions = res.json()
    assert isinstance(sessions, list)
    if sessions:
        assert "sessionId" in sessions[0]


@pytest.mark.integration
@pytest.mark.requires_db
def test_session_history():
    # Create a session with a message
    chat_res = client.post("/api/chat", json={"message": "Hello"})
    sid = chat_res.json()["sessionId"]

    res = client.get(f"/api/sessions/{sid}")
    assert res.status_code == 200
    history = res.json()
    assert history["sessionId"] == sid
    assert len(history["messages"]) >= 2  # user + model
```

- [ ] **Step 4: Create `tests/test_backend.py`**

## Task 5: Package `backend` as installable

The backend needs to import `soccer_agent` modules. Since the backend sits in `backend/` and `soccer_agent` in `soccer_agent/`, we need `sys.path` or a package install.

**Solution:** Run from the project root with `uv run uvicorn backend.main:app`. The `uv run` command resolves from the project root where `pyproject.toml` lives. The `from soccer_agent import ...` imports work because `uv run python` sees the project root.

Alternative: Add `__init__.py` to backend and set `PYTHONPATH=.`.

- [ ] **Step 5: Verify imports work: `uv run python -c "from backend.main import app; print('OK')"`**

## Verification

- [ ] **Step 6: Backend healthcheck:** `curl localhost:8080/api/health`
- [ ] **Step 7: Backend chat:** `curl -X POST localhost:8080/api/chat -H 'Content-Type: application/json' -d '{"message":"What is the capital of Argentina?"}'`
- [ ] **Step 8: Full test suite:** `uv run pytest -q` — all tests + new backend tests pass
- [ ] **Step 9: Frontend dev:** `cd frontend && npm run dev`, open `http://localhost:5173`, send a message
- [ ] **Step 10: Commit**

```bash
git add soccer-analytics-agent/ docs/
git commit -m "feat(soccer-agent): FastAPI backend + React frontend (Phase 6)"
```

## Smoke Test

```bash
chmod +x scripts/dev.sh
./scripts/dev.sh
```

Open `http://localhost:5173`. Send:
- "What's Argentina's Elo rating?"
- "Predict Argentina vs France"
- "Show me Brazil's last 3 matches"
- "Search for World Cup finals in the dataset"

---

## Self-review notes

- Spec coverage (Phase 6): FastAPI backend ✓, React frontend ✓, chat persistence ✓, session management ✓.
- The backend is a thin adapter — `respond()` is the same function the CLI uses. No agent logic duplicated.
- `chat.respond()` calls are wrapped in `asyncio.to_thread()` because they do blocking DB and API calls. FastAPI's async event loop stays responsive.
- Frontend session IDs are UUIDs stored in localStorage — no auth, no multi-user. This is a dev tool, not a SaaS product.
- Tool calls are extracted from `agent_trace` after `respond()` returns. The trace records every step (Phase 5), and the frontend renders calls/responses in expandable panels.
- CSS reuses career-coach's structure: `.app` flex container, `.sidebar` left, `.chat-shell` right, `.bubble` for messages, `.composer` bottom form.
- Deferred to later phases: trace viewer UI (explore turn-by-turn steps), streaming responses (SSE), multi-user auth, Dockerfile/Cloud Run (Phase 8).

## Implementation summary (2026-07-13)

**Completed:** All 7 tasks. 54 tests pass (46 existing + 8 backend). TypeScript compiles cleanly.

**Backend:** `backend/main.py` — FastAPI on port 8081, 6 endpoints (health, chat, memory, trace, team, teams). Gemini client created once at startup via `lifespan`. All blocking calls (`respond()`, `get_team_elo()`, `get_session_trace()`) go through `asyncio.to_thread()`. The backend is a thin adapter — zero agent logic duplication.

**Backend tests:** `tests/test_backend.py` — 8 tests with `TestClient`. Gemini client monkeypatched with `_FakeChat`. `chat.respond()` faked to avoid real DB/API calls. Covers: health, chat create session, chat reuse session, empty message 400, memory, trace, single team, team list.

**Frontend:** React 19 + TypeScript + Vite 6 on port 5173. 3 source files: `api.ts` (sendChat/getMemory/getTrace), `App.tsx` (chat UI with sidebar, sessions, tool panels, Markdown), `main.tsx`. Dark theme, sidebar layout matching career-coach pattern. No auth — sessions stored via localStorage UUID. Vite proxies `/api` → `:8081`.

**Dev script:** `scripts/dev.sh` — starts backend (uvicorn :8081) + frontend (npm dev :5173) in background, waits for both, prints URLs. Trap cleanups both processes on exit.

**Gotchas resolved:**
- `_fake_respond` was async but `respond()` is sync — changed to `def`, `asyncio.to_thread()` handles it.
- `get_team_elo` returns `{name: {elo, matches}}` not `{name: val}` — fixed test assertions to use `result["elo"][team]["elo"]`.

**Phase 7 ready:** XGBoost pipeline with 92 features, Optuna hyperparameter tuning — replaces the Elo heuristic in `predict_match`.
