"""Behavior-first tests verifying tool-selection prompt and description changes.

These tests assert that the SYSTEM_PROMPT and TOOL_DECLARATIONS description
strings contain the correct triggering cues from the SDD fix-agent-tool-selection
design. Written AFTER implementation per CONTEXT.md behavior-first convention.
"""

import inspect
import os

import pytest
from soccer_agent.loop import MAX_TOOL_ROUNDS, SYSTEM_PROMPT
from soccer_agent.tools import TOOL_DECLARATIONS, dispatch


def _tool_desc(name: str) -> str:
    for t in TOOL_DECLARATIONS:
        if t["name"] == name:
            return t["description"]
    raise KeyError(f"Tool {name!r} not found in TOOL_DECLARATIONS")


# ── REQUIREMENT-1: SYSTEM_PROMPT prefers specialized tools ──────────────


def test_system_prompt_prefers_specialized_tools():
    """REQ-1 scenarios 1.1-1.6: new prompt maps question types to tools
    and does NOT contain the old sql_query grounding string."""
    assert "TOOL SELECTION" in SYSTEM_PROMPT
    assert "get_h2h" in SYSTEM_PROMPT
    assert "Use the sql_query tool to ground every factual answer" not in SYSTEM_PROMPT


def test_system_prompt_has_error_recovery_guidance():
    """REQ-2 scenarios 2.1-2.2: new error recovery guides tool-switch,
    not 'do NOT apologize or give up'."""
    assert "switch to it" in SYSTEM_PROMPT


def test_system_prompt_no_old_apology_pattern():
    """REQ-2 scenario 2.2: the old 'do NOT apologize or give up' pattern is removed."""
    assert "do NOT apologize or give up" not in SYSTEM_PROMPT


def test_system_prompt_preserves_language_instruction():
    """Legacy behavior: 'Answer in the user's language' must remain."""
    assert "Answer in the user's language" in SYSTEM_PROMPT


def test_predict_match_prompt_describes_trained_model_not_elo():
    """The predict_match guidance must describe the trained XGBoost model, not
    claim it predicts 'using Elo ratings'.

    Regression: the stale Phase-6 phrasing made the agent explain its own
    XGBoost prediction as "based on Elo ratings" when asked 'why?', because the
    LLM parrots the tool description it is given.
    """
    assert (
        "predict_match: match outcome probabilities using Elo ratings"
        not in SYSTEM_PROMPT
    )
    assert "XGBoost" in SYSTEM_PROMPT


# ── REQUIREMENT-3: specialized tool descriptions have trigger cues ──────


def test_get_h2h_description_has_trigger_cue():
    """REQ-3 scenario 3.1: get_h2h description cues head-to-head intent."""
    desc = _tool_desc("get_h2h")
    assert "head-to-head" in desc
    assert "two specific teams" in desc
    assert desc.startswith("Use this tool when")


def test_get_team_form_description_has_trigger_cue():
    """REQ-3 scenario 3.2: get_team_form description cues form intent."""
    desc = _tool_desc("get_team_form")
    assert "last N matches" in desc or "recent form" in desc
    assert desc.startswith("Use this tool when")


def test_predict_match_description_has_trigger_cue():
    """REQ-3 scenario 3.3: predict_match description cues prediction intent."""
    desc = _tool_desc("predict_match")
    assert "who will win" in desc
    assert desc.startswith("Use this tool when")


def test_get_team_elo_description_has_trigger_cue():
    """REQ-3 scenario 3.4: get_team_elo description cues rating intent."""
    desc = _tool_desc("get_team_elo")
    assert "Elo rating" in desc or "Elo ratings" in desc
    assert desc.startswith("Use this tool when")


def test_recall_description_has_trigger_cue():
    """REQ-3 scenario 3.5: recall description cues memory intent."""
    desc = _tool_desc("recall")
    assert "previous conversation" in desc
    assert desc.startswith("Use this tool when")


# ── REQUIREMENT-4: sql_query demotion ───────────────────────────────────


def test_sql_query_description_is_demoted():
    """REQ-4 scenarios 4.1-4.3: sql_query is last-resort, keeps PostgreSQL
    syntax hints and table schemas."""
    desc = _tool_desc("sql_query")
    assert desc.startswith("Use this tool ONLY when no specialized tool")
    assert "PostgreSQL" in desc
    assert "ILIKE" in desc


# ── REQUIREMENT-5: dispatch() and MAX_TOOL_ROUNDS untouched ─────────────


def test_max_tool_rounds_unchanged():
    """REQ-2 scenario 2.3: MAX_TOOL_ROUNDS must still be 8."""
    assert MAX_TOOL_ROUNDS == 8


def test_dispatch_body_unchanged():
    """REQ-5 scenario 5.1: dispatch() function body is unmodified.

    Verifies via inspect.getsource that the dispatch function still
    routes through _HANDLERS with a try/except and returns the known
    'unknown tool' error message for missing handlers."""
    src = inspect.getsource(dispatch)
    assert "_HANDLERS" in src
    assert "try:" in src or "return handler(args)" in src
    assert "unknown tool" in src


# ── OPTIONAL INTEGRATION TEST (gated) ───────────────────────────────────


@pytest.mark.integration
def test_h2h_question_routes_to_get_h2h():
    """Smoke: asking 'Argentina vs Germany H2H' via the agent loop calls
    get_h2h as the first tool, not sql_query.

    Gated on GEMINI_API_KEY or GOOGLE_GENAI_USE_VERTEXAI environment
    variables. Skipped if neither is present."""
    if not (
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")
    ):
        pytest.skip("No Gemini credentials (set GEMINI_API_KEY or ADC)")

    # Lazily import to avoid breaking import collection without credentials
    from google.genai import Client
    from soccer_agent.loop import run_turn

    client = Client()
    model = "gemini-2.5-flash"
    answer, history, steps = run_turn(client, [], "Argentina vs Germany H2H", model)

    # Walk the history to find the first tool call
    first_tool = None
    for content in history:
        for part in content.parts:
            if part.function_call:
                first_tool = part.function_call.name
                break
        if first_tool:
            break

    assert first_tool == "get_h2h", (
        f"Expected get_h2h as first tool call, got {first_tool!r}"
    )
