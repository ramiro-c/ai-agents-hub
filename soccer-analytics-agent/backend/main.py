"""FastAPI backend for the Soccer Analytics Agent.

Wraps the agent loop in HTTP endpoints. Gemini client is created once at startup.
Blocking calls (respond, DB) run via asyncio.to_thread to avoid event-loop stalls.
"""

import asyncio
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from soccer_agent import db, memory, trace
from soccer_agent.chat import respond
from soccer_agent.tools import get_team_elo, get_team_form

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Soccer Analytics Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Gemini client — created once, reused across requests.
# The real import is deferred so tests can monkeypatch.
def _make_client():
    from google import genai

    return genai.Client()


_client = _make_client()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str


class MemoryItem(BaseModel):
    role: str
    content: str


class MemoryResponse(BaseModel):
    session_id: str
    memory: list[MemoryItem]


class TraceStep(BaseModel):
    turn_id: int
    step: int
    content: dict


class TraceResponse(BaseModel):
    session_id: str
    trace: list[TraceStep]


class TeamResponse(BaseModel):
    name: str
    elo: Optional[float]
    form: list[dict]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    """Quick liveness check — verifies DB is reachable."""
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        raise HTTPException(503, f"DB unreachable: {exc}")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Run one turn of the agent loop.

    Creates a new session if session_id is omitted.
    """
    session_id = req.session_id or f"web-{uuid.uuid4().hex[:8]}"
    try:
        answer = await asyncio.to_thread(
            respond, _client, session_id, req.message, model="gemini-2.5-flash"
        )
        return ChatResponse(session_id=session_id, answer=answer)
    except Exception as exc:
        raise HTTPException(500, f"Agent error: {exc}")


@app.get("/api/sessions/{session_id}/memory", response_model=MemoryResponse)
async def get_memory(session_id: str):
    """Return the working memory for a session (recency-ordered)."""
    turns = memory.load_working(session_id)
    return MemoryResponse(
        session_id=session_id,
        memory=[MemoryItem(role=r, content=c) for r, c in turns],
    )


@app.get("/api/sessions/{session_id}/trace", response_model=TraceResponse)
async def get_trace(session_id: str):
    """Return the full per-step trace for a session."""
    steps = trace.get_session_trace(session_id)
    return TraceResponse(
        session_id=session_id,
        trace=[TraceStep(turn_id=s[0], step=s[1], content=s[2]) for s in steps],
    )


@app.get("/api/teams/{name}", response_model=TeamResponse)
async def get_team(name: str):
    """Return a team's Elo rating and recent form."""
    elo_result = get_team_elo(name)
    elo_val = None
    if "elos" in elo_result and name in elo_result["elos"]:
        elo_val = elo_result["elos"][name]["elo"]
    form_result = get_team_form(name, 5)
    return TeamResponse(
        name=name,
        elo=elo_val,
        form=form_result.get("form", []),
    )


@app.get("/api/teams")
async def list_teams():
    """Return all rated teams with their Elo."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT team, elo FROM team_elo ORDER BY elo DESC"
        ).fetchall()
    return {
        "teams": [{"name": r[0], "elo": round(r[1], 1)} for r in rows],
    }
