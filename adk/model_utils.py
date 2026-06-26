"""
Centralized model provider resolution for ADK agents.

Uses the Strategy pattern via a typing.Protocol to allow multiple
model providers (Gemini, OpenRouter) with eager validation at
resolve_model() time. Auto-loads env vars from agent-specific
.env files with root adk/.env as fallback.
"""

import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

__all__ = ["ModelStrategy", "GeminiStrategy", "OpenRouterStrategy", "resolve_model"]

ADK_ROOT = Path(__file__).parent.resolve()


@runtime_checkable
class ModelStrategy(Protocol):
    """Strategy interface for model providers."""

    def get_model(self) -> str | LiteLlm:
        """Return the model object (string or LiteLlm instance)."""
        ...


class GeminiStrategy:
    """Model strategy for Google Gemini models."""

    def get_model(self) -> str:
        """Return the Gemini model identifier string."""
        return "gemini-2.5-flash"


class OpenRouterStrategy:
    """Model strategy for OpenRouter (via LiteLlm)."""

    def get_model(self) -> LiteLlm:
        """Return a configured LiteLlm instance for OpenRouter."""
        return LiteLlm(
            model="openrouter/owl-alpha",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            api_base=os.getenv("OPENROUTER_BASE_URL"),
        )


def _load_env_chain(agent_dir: str | Path | None = None) -> None:
    """Load .env files in priority order.

    1. Agent-specific .env (higher priority, won't override existing vars)
    2. Root adk/.env (fallback, won't override existing vars)

    Args:
        agent_dir: Optional path to an agent directory with its own .env file.
    """
    if agent_dir:
        agent_env = Path(agent_dir) / ".env"
        if agent_env.exists():
            load_dotenv(agent_env, override=False)
        else:
            root_env = ADK_ROOT / ".env"
            if root_env.exists():
                load_dotenv(root_env, override=False)
            else:
                raise ValueError("No .env file found")


def resolve_model(provider: str | None = None) -> str | LiteLlm:
    """Resolve and return the model object for the given provider.

    Auto-loads .env files via the env chain before reading any env vars.
    Validates all required env vars eagerly — raises ValueError on any
    missing or unknown configuration.

    Args:
        provider: Optional provider name. If None, reads MODEL_PROVIDER
                  from environment. Valid values: "gemini", "openrouter".

    Returns:
        A model string (for Gemini) or LiteLlm instance (for OpenRouter).

    Raises:
        ValueError: If MODEL_PROVIDER is unset, unknown, or required
                    provider-specific env vars are missing.
    """
    _load_env_chain()

    if provider is None:
        provider = os.getenv("MODEL_PROVIDER")

    if not provider:
        raise ValueError(
            "MODEL_PROVIDER env var is not set. Set it to 'gemini' or 'openrouter'."
        )

    provider = provider.strip().lower()

    if provider == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY env var is not set")
        return GeminiStrategy().get_model()

    elif provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        api_base = os.getenv("OPENROUTER_BASE_URL")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY env var is not set")
        if not api_base:
            raise ValueError("OPENROUTER_BASE_URL env var is not set")
        return OpenRouterStrategy().get_model()

    else:
        raise ValueError(
            f"Unknown MODEL_PROVIDER '{provider}'. Valid values: gemini, openrouter"
        )
