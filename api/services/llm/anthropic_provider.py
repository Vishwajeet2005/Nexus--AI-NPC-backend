"""
api/services/llm/anthropic_provider.py
────────────────────────────────────────
Anthropic provider implementation using the official `anthropic` async client.

Key difference from OpenAI/Groq:
  Anthropic's Messages API does NOT support `response_format={"type": "json_object"}`.
  Instead we use two techniques in combination:

  1. JSON_INSTRUCTION is appended to the system prompt (tells Claude what to output).
  2. Assistant prefill: we start the assistant turn with `{` so Claude is forced
     to continue completing a JSON object rather than generating prose preamble.
     The prefill is stripped off the final content before parsing.

This combination reliably produces clean JSON from Claude models without
needing structured output support.

Configuration (from environment / pydantic Settings):
  ANTHROPIC_API_KEY — required
  ANTHROPIC_MODEL   — default: claude-haiku-4-5-20251001

Timeout:
  asyncio.wait_for wraps the API call with LLM_TIMEOUT_SECONDS (10s).

Error handling:
  All exceptions caught and logged. Callers always receive a valid LLMResponse.
"""

from __future__ import annotations

import asyncio
import logging

from api.services.llm.base import BaseLLMProvider, LLMResponse, LLM_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# The prefill character — forces Claude to begin a JSON object immediately.
# We prepend this to the assistant turn and then add it back before parsing.
_JSON_PREFILL = "{"


class AnthropicProvider(BaseLLMProvider):
    """LLM provider backed by Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        """
        Args:
            api_key: Anthropic API key (ANTHROPIC_API_KEY).
            model:   Anthropic model to use.
                     Default: claude-haiku-4-5-20251001 (fast + cheap for NPC dialogue).
                     Also works with: claude-sonnet-4-6, claude-opus-4-6.
        """
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ImportError(
                "Anthropic provider requires the `anthropic` package. "
                "Install it with: pip install anthropic"
            ) from exc

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        logger.info(
            "llm.provider.anthropic.init",
            extra={"model": self._model},
        )

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
    ) -> LLMResponse:
        """
        Call Anthropic Messages API with JSON prefill technique.

        The assistant turn is pre-seeded with `{` which forces Claude to
        complete a JSON object. The prefill is prepended back to the
        response content before parsing so _extract_json sees a full object.
        """
        full_system = f"{system_prompt}\n\n{self.JSON_INSTRUCTION}"

        try:
            raw_response = await asyncio.wait_for(
                self._client.messages.create(
                    model=self._model,
                    max_tokens=512,
                    system=full_system,
                    messages=[
                        {"role": "user", "content": user_message},
                        # Assistant prefill — forces JSON-first output
                        {"role": "assistant", "content": _JSON_PREFILL},
                    ],
                    temperature=0.8,
                ),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "llm.anthropic.timeout",
                extra={"model": self._model, "timeout": LLM_TIMEOUT_SECONDS},
            )
            return LLMResponse.timeout()
        except Exception as exc:
            logger.error(
                "llm.anthropic.api_error",
                extra={"model": self._model, "error": str(exc)},
                exc_info=exc,
            )
            return LLMResponse.error()

        # Anthropic returns the continuation AFTER the prefill character.
        # We must prepend `{` back to reconstruct the full JSON object.
        continuation = raw_response.content[0].text if raw_response.content else ""
        raw_content = _JSON_PREFILL + continuation

        try:
            data = self._extract_json(raw_content)
            result = LLMResponse.from_dict(data, raw=raw_content)
            logger.debug(
                "llm.anthropic.success",
                extra={
                    "model": self._model,
                    "behaviour": result.behaviour.value,
                    "secret_leaked": result.secret_leaked,
                },
            )
            return result
        except Exception as exc:
            logger.error(
                "llm.anthropic.parse_error",
                extra={
                    "model": self._model,
                    "raw": raw_content[:500],
                    "error": str(exc),
                },
            )
            return LLMResponse.error(raw=raw_content)
