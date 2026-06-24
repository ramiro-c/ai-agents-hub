import os
import uuid
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

ADK_API_URL = os.getenv("ADK_API_URL", "http://127.0.0.1:8000").rstrip("/")
ADK_APP_NAME = os.getenv("ADK_APP_NAME", "agent")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

app = FastAPI(title="Customer Support Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    userId: str | None = None
    sessionId: str | None = None


class ChatResponse(BaseModel):
    reply: str
    userId: str
    sessionId: str


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _extract_reply(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        content = event.get("content") or {}
        if content.get("role") != "model":
            continue
        parts = content.get("parts") or []
        texts = [part.get("text", "") for part in parts if part.get("text")]
        if texts:
            return "".join(texts).strip()
    return ""


async def _ensure_session(
    client: httpx.AsyncClient, user_id: str, session_id: str
) -> None:
    url = f"{ADK_API_URL}/apps/{ADK_APP_NAME}/users/{user_id}/sessions/{session_id}"
    response = await client.post(url, json={})
    if response.status_code in (200, 201):
        return
    if response.status_code == 409 or "already exists" in response.text.lower():
        return
    response.raise_for_status()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    user_id = body.userId or _new_id("user")
    session_id = body.sessionId or _new_id("session")

    payload = {
        "appName": ADK_APP_NAME,
        "userId": user_id,
        "sessionId": session_id,
        "newMessage": {
            "role": "user",
            "parts": [{"text": body.message}],
        },
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            await _ensure_session(client, user_id, session_id)
            response = await client.post(f"{ADK_API_URL}/run", json=payload)
            response.raise_for_status()
            events = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise HTTPException(
            status_code=502,
            detail=f"ADK API error ({exc.response.status_code}): {detail}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo conectar con ADK en {ADK_API_URL}. ¿Está corriendo adk api_server?",
        ) from exc

    reply = _extract_reply(events)
    if not reply:
        raise HTTPException(
            status_code=502, detail="El agente no devolvió una respuesta de texto."
        )

    return ChatResponse(reply=reply, userId=user_id, sessionId=session_id)
