"""Integration tests for agent trace persistence."""

import pytest

pytestmark = pytest.mark.integration

requires_db = pytest.mark.requires_db


@pytest.fixture
def trace_session():
    """Unique session ID per test, clean up after."""
    import uuid

    return f"test-trace-{uuid.uuid4().hex[:8]}"


@requires_db
def test_save_and_get_turn_trace(trace_session):
    from soccer_agent.trace import get_turn_trace, save_step

    save_step(trace_session, 1, 1, {"kind": "answer", "text": "hello"})
    save_step(trace_session, 1, 2, {"kind": "tool_calls", "calls": []})

    steps = get_turn_trace(trace_session, 1)
    assert len(steps) == 2
    assert steps[0]["step"] == 1
    assert steps[0]["content"]["kind"] == "answer"
    assert steps[1]["step"] == 2
    assert steps[1]["content"]["kind"] == "tool_calls"


@requires_db
def test_get_last_turn_id_starts_at_zero(trace_session):
    from soccer_agent.trace import get_last_turn_id

    assert get_last_turn_id(trace_session) == 0


@requires_db
def test_get_last_turn_id_increments(trace_session):
    from soccer_agent.trace import get_last_turn_id, save_step

    save_step(trace_session, 1, 1, {"kind": "answer", "text": "a"})
    assert get_last_turn_id(trace_session) == 1

    save_step(trace_session, 2, 1, {"kind": "answer", "text": "b"})
    assert get_last_turn_id(trace_session) == 2


@requires_db
def test_get_session_trace_spans_turns(trace_session):
    from soccer_agent.trace import get_session_trace, save_step

    save_step(trace_session, 1, 1, {"kind": "answer", "text": "turn1"})
    save_step(trace_session, 2, 1, {"kind": "answer", "text": "turn2"})

    trace = get_session_trace(trace_session)
    assert len(trace) == 2
    assert trace[0]["turn_id"] == 1
    assert trace[0]["content"]["text"] == "turn1"
    assert trace[1]["turn_id"] == 2
    assert trace[1]["content"]["text"] == "turn2"


@requires_db
def test_get_turn_trace_empty_for_unknown_turn(trace_session):
    from soccer_agent.trace import get_turn_trace

    assert get_turn_trace(trace_session, 999) == []
