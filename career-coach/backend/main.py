"""FastAPI backend: proxya el Agent Engine (career_coach) y sirve el frontend.

- POST /api/chat: devuelve la respuesta completa en JSON.
- GET/DELETE /api/sessions...
- GET  /api/health
- Sirve el build estatico del frontend en / (si existe la carpeta static/).
El browser habla mismo-origen; la auth a Vertex/Agent Engine es via ADC (sin keys).
"""

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

import vertexai
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from google.auth import default as google_auth_default
from google.auth.transport.requests import AuthorizedSession
from pydantic import BaseModel, Field
from vertexai import agent_engines

load_dotenv()

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
RESOURCE = os.environ["AGENT_ENGINE_RESOURCE"]
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
STATIC_DIR = os.getenv("STATIC_DIR", "static")
API_BASE = "https://aiplatform.googleapis.com/v1"

vertexai.init(project=PROJECT, location=LOCATION)
_remote_app = agent_engines.get(RESOURCE)
_credentials, _ = google_auth_default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
_authed_session = AuthorizedSession(_credentials)

app = FastAPI(title="Career Coach UI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    userId: str | None = None
    sessionId: str | None = None


class ToolCall(BaseModel):
    name: str
    args: Any = None
    response: Any = None


class ChatResponse(BaseModel):
    userId: str
    sessionId: str
    answer: str
    thoughts: str
    tools: list[ToolCall]


class SessionSummary(BaseModel):
    sessionId: str
    title: str
    lastUpdate: str | None = None


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str | None = None
    answer: str | None = None
    thoughts: str | None = None
    tools: list[ToolCall] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    userId: str
    sessionId: str
    messages: list[HistoryMessage]


def _session_id(session) -> str | None:
    if isinstance(session, dict):
        return session.get("id") or session.get("sessionId")
    return getattr(session, "id", None) or getattr(session, "session_id")


def _resource_name(resource_id: str) -> str:
    return f"{RESOURCE}/sessions/{resource_id}"


def _resource_id(name: str | None) -> str:
    if not name:
        return ""
    return name.rsplit("/", 1)[-1]


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _short_title(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return "Conversación"
    return cleaned[:48].rstrip() + ("..." if len(cleaned) > 48 else "")


def _event_text_parts(event: dict[str, Any]) -> list[dict[str, Any]]:
    content = event.get("content") or {}
    return list(content.get("parts") or [])


def _event_text(event: dict[str, Any]) -> str:
    parts = _event_text_parts(event)
    texts = [part.get("text", "") for part in parts if part.get("text")]
    return "".join(texts).strip()


def _response_error(response) -> str:
    try:
        payload = response.json()
        error = payload.get("error") or {}
        if isinstance(error, dict):
            return error.get("message") or response.text
    except ValueError:
        pass
    return response.text or response.reason


def _api_json(
    method: str, path: str, *, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = _authed_session.request(
        method, f"{API_BASE}{path}", params=params, timeout=60
    )
    if not response.ok:
        raise HTTPException(
            status_code=response.status_code, detail=_response_error(response)
        )
    if not response.content:
        return {}
    return response.json()


def _accumulate_event_parts(
    events,
    answer_parts: list[str],
    thought_parts: list[str],
    tools: list[ToolCall],
) -> None:
    """Parsea los parts de cada event (function_call/response/text) hacia los
    acumuladores compartidos. Lo usan tanto el stream en vivo (POST /api/chat)
    como la reconstruccion de historial, para que no se desincronicen."""
    for event in events:
        content = event.get("content") or {}
        for part in content.get("parts") or []:
            if part.get("function_call"):
                function_call = part["function_call"]
                tools.append(
                    ToolCall(
                        name=function_call.get("name") or "",
                        args=function_call.get("args"),
                    )
                )
            elif part.get("function_response"):
                function_response = part["function_response"]
                name = function_response.get("name") or ""
                for tool in reversed(tools):
                    if tool.name == name and tool.response is None:
                        tool.response = function_response.get("response")
                        break
            elif part.get("text"):
                text = part["text"]
                if part.get("thought"):
                    thought_parts.append(text)
                else:
                    answer_parts.append(text)


def _build_assistant_message(events: list[dict[str, Any]]) -> HistoryMessage | None:
    answer_parts: list[str] = []
    thought_parts: list[str] = []
    tools: list[ToolCall] = []
    _accumulate_event_parts(events, answer_parts, thought_parts, tools)

    answer = "".join(answer_parts).strip()
    thoughts = "".join(thought_parts).strip()
    if not answer and not thoughts and not tools:
        return None
    return HistoryMessage(
        role="assistant", answer=answer, thoughts=thoughts, tools=tools
    )


def _session_summary_from_item(item: dict[str, Any]) -> SessionSummary:
    session_name = item.get("name") or ""
    session_id = _resource_id(session_name)
    title = item.get("displayName") or ""
    if not title:
        events = _list_session_events(session_name, single_page=True)
        for event in events:
            if event.get("author") == "user":
                title = _short_title(_event_text(event))
                if title != "Conversación":
                    break
        if not title:
            title = "Conversación"
    return SessionSummary(
        sessionId=session_id,
        title=title,
        lastUpdate=item.get("updateTime") or item.get("createTime"),
    )


def _list_session_events(
    session_name: str, *, single_page: bool = False
) -> list[dict[str, Any]]:
    # single_page corta en la primera pagina: alcanza para derivar el titulo
    # (el primer mensaje del usuario esta al inicio) y evita paginar N sesiones.
    events: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        params: dict[str, Any] = {"pageSize": 100, "orderBy": "timestamp"}
        if page_token:
            params["pageToken"] = page_token
        payload = _api_json("GET", f"/{session_name}/events", params=params)
        events.extend(payload.get("sessionEvents") or [])
        page_token = payload.get("nextPageToken") or None
        if single_page or not page_token:
            break
    return events


def _list_sessions_sync(user_id: str) -> list[SessionSummary]:
    payload = _api_json(
        "GET",
        f"/{RESOURCE}/sessions",
        params={
            "filter": f'userId="{user_id}"',
            "orderBy": "updateTime desc",
            "pageSize": 100,
        },
    )
    sessions = payload.get("sessions") or []
    result = [_session_summary_from_item(item) for item in sessions]
    fallback = datetime(1970, 1, 1, tzinfo=timezone.utc)
    result.sort(
        key=lambda item: _parse_timestamp(item.lastUpdate) or fallback, reverse=True
    )
    return result


def _get_session_history_sync(user_id: str, session_id: str) -> HistoryResponse:
    session_name = _resource_name(session_id)
    events = _list_session_events(session_name)
    messages: list[HistoryMessage] = []
    assistant_buffer: list[dict[str, Any]] = []

    for event in events:
        author = (event.get("author") or "").lower()
        if author == "user":
            if assistant_buffer:
                assistant_message = _build_assistant_message(assistant_buffer)
                if assistant_message:
                    messages.append(assistant_message)
                assistant_buffer = []
            text = _event_text(event)
            if text:
                messages.append(HistoryMessage(role="user", text=text))
            continue
        assistant_buffer.append(event)

    if assistant_buffer:
        assistant_message = _build_assistant_message(assistant_buffer)
        if assistant_message:
            messages.append(assistant_message)

    return HistoryResponse(
        userId=user_id,
        sessionId=session_id,
        messages=messages,
    )


def _delete_session_sync(session_id: str) -> None:
    session_name = _resource_name(session_id)
    response = _authed_session.delete(f"{API_BASE}/{session_name}", timeout=60)
    if not response.ok:
        raise HTTPException(
            status_code=response.status_code, detail=_response_error(response)
        )


def _collect_response_sync(
    message: str, user_id: str, session_id: str | None
) -> ChatResponse:
    if not session_id:
        session = _remote_app.create_session(user_id=user_id)
        session_id = _session_id(session)

    answer_parts: list[str] = []
    thought_parts: list[str] = []
    tools: list[ToolCall] = []

    _accumulate_event_parts(
        _remote_app.stream_query(
            user_id=user_id, session_id=session_id, message=message
        ),
        answer_parts,
        thought_parts,
        tools,
    )

    return ChatResponse(
        userId=user_id,
        sessionId=session_id,
        answer="".join(answer_parts),
        thoughts="".join(thought_parts),
        tools=tools,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    user_id = body.userId or f"user_{uuid.uuid4().hex[:12]}"
    return await asyncio.to_thread(
        _collect_response_sync, body.message, user_id, body.sessionId
    )


@app.get("/api/sessions", response_model=list[SessionSummary])
async def list_sessions(userId: str = Query(min_length=1)) -> list[SessionSummary]:
    return await asyncio.to_thread(_list_sessions_sync, userId)


@app.get("/api/sessions/{session_id}", response_model=HistoryResponse)
async def get_session(
    session_id: str, userId: str = Query(min_length=1)
) -> HistoryResponse:
    return await asyncio.to_thread(_get_session_history_sync, userId, session_id)


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str, userId: str = Query(min_length=1)
) -> dict[str, str]:
    await asyncio.to_thread(_delete_session_sync, session_id)
    return {"status": "ok", "sessionId": session_id, "userId": userId}


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


# Sirve el build del frontend (SPA). app.frontend() -> assets faltantes dan 404
# real y la navegacion de browser cae a index.html (client-side routing). Las
# rutas /api de arriba siempre tienen prioridad. En dev el frontend lo sirve Vite,
# asi que solo montamos si existe el build.
if os.path.isdir(STATIC_DIR):
    app.frontend("/", directory=STATIC_DIR)
