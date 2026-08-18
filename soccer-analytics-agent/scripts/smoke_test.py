"""One-shot end-to-end check against a running backend (local or deployed).

Walks the same path a browser would: health, a grounded chat turn, and the
per-step trace proving the agent actually used a tool (Vertex + Cloud SQL +
models proven inside the container). Uses urllib only — no extra dependencies.

Point it anywhere with SMOKE_TEST_BASE_URL, e.g.:

    SMOKE_TEST_BASE_URL=https://soccer-agent-xxxx-uc.a.run.app \
        uv run python scripts/smoke_test.py

Default base is the local dev server (the Vite proxy targets the same port).
"""

import json
import os
import urllib.error
import urllib.request

BASE_URL = os.environ.get("SMOKE_TEST_BASE_URL", "http://localhost:8081")
QUESTION = "How many official matches has Argentina played, and how many did it win?"


def _request(path: str, *, method: str = "GET", payload: dict | None = None):
    """JSON request helper; exits with a clear message on transport errors."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {method} {url}: {body[:500]}") from None
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Could not reach {url}: {exc.reason}. Is the backend up?"
        ) from None


def main() -> None:
    print(f"SMOKE TEST against {BASE_URL}")

    # 1. Health
    status, health = _request("/api/health")
    assert status == 200, f"health expected 200, got {status}"
    assert health.get("status") == "ok", f"unexpected health payload: {health}"
    print(f"  [ok] /api/health -> {health}")

    # 2. Grounded chat turn: the answer must contain digits, proving the
    # model read real rows instead of answering from memory.
    status, chat = _request("/api/chat", method="POST", payload={"message": QUESTION})
    assert status == 200, f"chat expected 200, got {status}"
    answer = chat.get("answer", "")
    assert any(ch.isdigit() for ch in answer), (
        f"answer not grounded (no digits): {answer[:200]!r}"
    )
    session_id = chat.get("session_id", "")
    assert session_id, "chat response missing session_id"
    print(f"  [ok] /api/chat answered with digits: {answer[:120]}...")

    # 3. Trace must show at least one real tool call.
    status, trace = _request(f"/api/sessions/{session_id}/trace")
    assert status == 200, f"trace expected 200, got {status}"
    steps = trace.get("trace", [])
    tool_steps = [s for s in steps if s.get("content", {}).get("kind") == "tool_calls"]
    assert tool_steps, f"expected >=1 tool_calls step in trace, got {len(steps)} steps"
    tools = [c.get("tool") for s in tool_steps for c in s["content"].get("calls", [])]
    print(f"  [ok] trace shows {len(tool_steps)} tool round(s): {sorted(set(tools))}")

    print("SMOKE TEST OK")


if __name__ == "__main__":
    main()
