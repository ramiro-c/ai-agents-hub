"""Tests for adk/model_utils.py — model provider resolution with Strategy pattern."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from google.adk.models.lite_llm import LiteLlm

from model_utils import (
    GeminiStrategy,
    ModelStrategy,
    OpenRouterStrategy,
    _load_env_chain,
    resolve_model,
)

# ---------------------------------------------------------------------------
# Strategy unit tests
# ---------------------------------------------------------------------------


def test_gemini_strategy_returns_model_string():
    """GeminiStrategy.get_model() returns 'gemini-2.5-flash'."""
    strategy = GeminiStrategy()
    assert strategy.get_model() == "gemini-2.5-flash"


def test_openrouter_strategy_returns_lite_llm():
    """OpenRouterStrategy.get_model() returns a configured LiteLlm instance."""
    with patch.dict(
        os.environ,
        {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        },
    ):
        strategy = OpenRouterStrategy()
        model = strategy.get_model()

        assert isinstance(model, LiteLlm)
        assert model.model == "openrouter/owl-alpha"
        # LiteLlm stores extra kwargs in _additional_args private attribute
        addl = model.__pydantic_private__["_additional_args"]
        assert addl["api_key"] == "test-key"
        assert addl["api_base"] == "https://openrouter.ai/api/v1"


def test_model_strategy_protocol():
    """GeminiStrategy and OpenRouterStrategy conform to ModelStrategy Protocol."""
    assert isinstance(GeminiStrategy(), ModelStrategy)
    assert isinstance(OpenRouterStrategy(), ModelStrategy)


# ---------------------------------------------------------------------------
# resolve_model — happy paths
# ---------------------------------------------------------------------------


def test_resolve_model_gemini_arg():
    """resolve_model('gemini') returns 'gemini-2.5-flash' when GOOGLE_API_KEY is set."""
    with patch.dict(
        os.environ,
        {
            "GOOGLE_API_KEY": "test-google-key",
        },
        clear=True,
    ):
        result = resolve_model("gemini")
        assert result == "gemini-2.5-flash"


def test_resolve_model_openrouter_arg():
    """resolve_model('openrouter') returns LiteLlm when all OpenRouter vars are set."""
    with patch.dict(
        os.environ,
        {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        },
        clear=True,
    ):
        result = resolve_model("openrouter")

        assert isinstance(result, LiteLlm)
        assert result.model == "openrouter/owl-alpha"


def test_resolve_model_reads_from_env():
    """resolve_model() reads MODEL_PROVIDER from environment."""
    with patch.dict(
        os.environ,
        {
            "MODEL_PROVIDER": "gemini",
            "GOOGLE_API_KEY": "test-google-key",
        },
        clear=True,
    ):
        result = resolve_model()
        assert result == "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# resolve_model — error paths
# ---------------------------------------------------------------------------


def test_missing_model_provider_raises():
    """resolve_model() raises ValueError when MODEL_PROVIDER is unset."""
    with patch.dict(os.environ, {}, clear=True):
        # Mock _load_env_chain so the real adk/.env doesn't interfere
        with patch("model_utils._load_env_chain"):
            with pytest.raises(ValueError, match="MODEL_PROVIDER"):
                resolve_model()


def test_unknown_model_provider_raises():
    """resolve_model() raises ValueError for unknown providers."""
    with patch.dict(
        os.environ,
        {
            "MODEL_PROVIDER": "claude",
        },
        clear=True,
    ):
        with pytest.raises(ValueError, match="Unknown MODEL_PROVIDER"):
            resolve_model()


def test_missing_google_api_key_raises():
    """resolve_model('gemini') raises ValueError when GOOGLE_API_KEY is missing."""
    with patch.dict(
        os.environ,
        {
            "MODEL_PROVIDER": "gemini",
        },
        clear=True,
    ):
        with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
            resolve_model("gemini")


def test_missing_openrouter_api_key_raises():
    """Missing OPENROUTER_API_KEY raises ValueError."""
    with patch.dict(
        os.environ,
        {
            "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        },
        clear=True,
    ):
        # Mock _load_env_chain so the real adk/.env doesn't provide the key
        with patch("model_utils._load_env_chain"):
            with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
                resolve_model("openrouter")


def test_missing_openrouter_base_url_raises():
    """Missing OPENROUTER_BASE_URL raises ValueError."""
    with patch.dict(
        os.environ,
        {
            "OPENROUTER_API_KEY": "test-key",
        },
        clear=True,
    ):
        # Mock _load_env_chain so the real adk/.env doesn't provide the url
        with patch("model_utils._load_env_chain"):
            with pytest.raises(ValueError, match="OPENROUTER_BASE_URL"):
                resolve_model("openrouter")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_string_model_provider_treated_as_missing():
    """Empty MODEL_PROVIDER is treated as unset."""
    with patch.dict(
        os.environ,
        {
            "MODEL_PROVIDER": "",
        },
        clear=True,
    ):
        with patch("model_utils._load_env_chain"):
            with pytest.raises(ValueError, match="MODEL_PROVIDER"):
                resolve_model()


def test_empty_string_api_key_treated_as_missing():
    """Empty GOOGLE_API_KEY is treated as unset."""
    with patch.dict(
        os.environ,
        {
            "MODEL_PROVIDER": "gemini",
            "GOOGLE_API_KEY": "",
        },
        clear=True,
    ):
        with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
            resolve_model()


def test_whitespace_and_case_normalization():
    """MODEL_PROVIDER whitespace is stripped and case is normalized to lowercase."""
    with patch.dict(
        os.environ,
        {
            "MODEL_PROVIDER": "  Gemini  ",
            "GOOGLE_API_KEY": "test-key",
        },
        clear=True,
    ):
        result = resolve_model()
        assert result == "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Env chain loading tests
# ---------------------------------------------------------------------------


def test_agent_dir_env_takes_priority():
    """Agent dir .env vars take priority over root .env vars."""
    with patch.dict(os.environ, {}, clear=True):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_env = Path(tmpdir) / ".env"
            agent_env.write_text("OPENROUTER_API_KEY=agent-key\n")

            _load_env_chain(agent_dir=tmpdir)

            # Agent env should be loaded
            assert os.getenv("OPENROUTER_API_KEY") == "agent-key"


def test_root_env_as_fallback():
    """When agent dir .env is missing, root .env vars are loaded."""
    with patch.dict(os.environ, {}, clear=True):
        with tempfile.TemporaryDirectory() as tmpdir:
            # No agent .env in tmpdir — it loads root .env (adk/.env)
            _load_env_chain(agent_dir=tmpdir)

            # MODEL_PROVIDER should be loaded from root .env
            assert os.getenv("MODEL_PROVIDER") == "openrouter"


def test_idempotent_env_loading():
    """Calling _load_env_chain() twice does not overwrite existing env vars."""
    with patch.dict(
        os.environ,
        {
            "OPENROUTER_API_KEY": "pre-existing-value",
        },
        clear=True,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_env = Path(tmpdir) / ".env"
            agent_env.write_text("OPENROUTER_API_KEY=new-agent-value\n")

            # First call — loads agent env but does NOT override pre-existing
            _load_env_chain(agent_dir=tmpdir)
            assert os.getenv("OPENROUTER_API_KEY") == "pre-existing-value"

            # Second call — still no overwrite
            _load_env_chain(agent_dir=tmpdir)
            assert os.getenv("OPENROUTER_API_KEY") == "pre-existing-value"


def test_missing_agent_dir_env():
    """Missing agent dir .env is silently skipped, root .env still loads."""
    with patch.dict(os.environ, {}, clear=True):
        with tempfile.TemporaryDirectory() as tmpdir:
            # No .env file in tmpdir
            _load_env_chain(agent_dir=tmpdir)

            # Root .env should still be loaded
            assert os.getenv("MODEL_PROVIDER") == "openrouter"
