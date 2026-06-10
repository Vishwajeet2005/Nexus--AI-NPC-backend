"""
api/services/llm/factory.py
────────────────────────────
Provider factory — returns the correct BaseLLMProvider based on the
`LLM_PROVIDER` environment variable.

Supported values (case-insensitive):
  groq       → GroqProvider      (DEFAULT — fastest for live interrogation)
  openai     → OpenAIProvider
  anthropic  → AnthropicProvider

Each provider reads its own API key and model from Settings, which in turn
reads from the environment / .env file. This means:
  - Swapping providers requires only an env var change — zero code changes.
  - The singleton is cached per-process via @lru_cache; tests can call
    `get_llm_provider.cache_clear()` to force re-instantiation.

Required env vars per provider:
  groq:      GROQ_API_KEY      (+ optional GROQ_MODEL)
  openai:    OPENAI_API_KEY    (+ optional OPENAI_MODEL)
  anthropic: ANTHROPIC_API_KEY (+ optional ANTHROPIC_MODEL)
"""

from __future__ import annotations

import logging
from functools import lru_cache

from api.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# Supported provider names → display label for logging
_SUPPORTED_PROVIDERS: dict[str, str] = {
    "groq": "Groq (llama-3.1-8b-instant)",
    "openai": "OpenAI (gpt-4o-mini)",
    "anthropic": "Anthropic (claude-haiku-4-5)",
}


@lru_cache(maxsize=1)
def get_llm_provider() -> BaseLLMProvider:
    """
    Return the singleton LLM provider for this process.

    Reads LLM_PROVIDER (and the corresponding API key / model) from
    pydantic Settings. Raises `ValueError` for unknown provider names
    or `ImportError` if the required SDK is not installed.

    Cache is per-process. Call `get_llm_provider.cache_clear()` in tests
    to force re-instantiation after patching environment variables.
    """
    # Import Settings here (not at module level) to avoid circular imports
    # and so the cache is populated lazily on first NPC interaction.
    from api.config import get_settings
    settings = get_settings()

    provider_name = settings.llm_provider.lower()
    logger.info(
        "llm.factory.creating",
        extra={"provider": provider_name},
    )

    if provider_name == "groq":
        from api.services.llm.groq_provider import GroqProvider
        return GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
        )

    if provider_name == "openai":
        from api.services.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )

    if provider_name == "anthropic":
        from api.services.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER: {provider_name!r}. "
        f"Supported values: {', '.join(_SUPPORTED_PROVIDERS)}"
    )
