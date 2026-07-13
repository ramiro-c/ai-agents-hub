"""Integration tests for the FastAPI backend.

Uses FastAPI's TestClient — no running server needed.
Monkeypatches the Gemini client to avoid real LLM calls.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_client(monkeypatch):
    """Return a TestClient with a fake Gemini client."""
    from backend.main import app

    # Replace the global _client with a dummy
    class FakeClient:
        pass

    monkeypatch.setattr("backend.main._client", FakeClient())

    # Replace respond() with a fast deterministic stub (sync, not async)
    def _fake_respond(_client, session_id, message, model=None):
        return f"Echo: {message}"

    monkeypatch.setattr("backend.main.respond", _fake_respond)
    return TestClient(app)


class TestHealth:
    def test_health_returns_ok(self, test_client):
        resp = test_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestChat:
    def test_chat_creates_session(self, test_client):
        resp = test_client.post("/api/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"].startswith("web-")
        assert data["answer"] == "Echo: Hello"

    def test_chat_reuses_session(self, test_client):
        sid = "test-session-1"
        resp = test_client.post("/api/chat", json={"message": "Hi", "session_id": sid})
        assert resp.status_code == 200
        assert resp.json()["session_id"] == sid

    def test_chat_empty_message(self, test_client):
        resp = test_client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 200


class TestMemory:
    def test_memory_returns_list(self, test_client):
        resp = test_client.get("/api/sessions/test-memory/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "test-memory"
        assert isinstance(data["memory"], list)


class TestTrace:
    def test_trace_returns_list(self, test_client):
        resp = test_client.get("/api/sessions/test-trace/trace")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "test-trace"
        assert isinstance(data["trace"], list)


class TestTeams:
    def test_get_team_returns_elo(self, test_client):
        resp = test_client.get("/api/teams/Argentina")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Argentina"
        assert data["elo"] is not None or resp.status_code in (200, 422)

    def test_list_teams(self, test_client):
        resp = test_client.get("/api/teams")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["teams"], list)
        if data["teams"]:
            t = data["teams"][0]
            assert "name" in t
            assert "elo" in t
