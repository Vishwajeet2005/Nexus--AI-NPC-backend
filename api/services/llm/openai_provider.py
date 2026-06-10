"""
api/services/llm/openai_provider.py
────────────────────────────────────
OpenAI provider implementation using the official `openai` async client.

Configuration (from environment / pydantic Settings):
  OPENAI_API_KEY  — required
  OPENAI_MODEL    — default: gpt-4o-mini

JSON enforcement:
  Uses `response_format={"type": "json_object"}` which guarantees the model
  returns a parseable JSON object. Still appends JSON_INSTRUCTION to the
  system prompt so the model outputs the correct keys.

Timeout:
  asyncio.wait_for wraps the API call with LLM_TIMEOUT_SECONDS (10s).
  On TimeoutError → returns LLMResponse.timeout().

Error handling:
  All exceptions (API errors, rate limits, JSON parse failures) are caught
  and logged. Callers always receive a valid LLMResponse.
"""

from __future__ import annotations

import asyncio
import logging

from api.services.llm.base import BaseLLMProvider, LLMResponse, LLM_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """LLM provider backed by OpenAI Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
    ) -> None:
        """
        Args:
            api_key: OpenAI API key (OPENAI_API_KEY).
            model:   Chat model to use. Default: gpt-4o-mini (fast, cheap, json-capable).
        """
        # Import here so the module can be imported even without `openai` installed
        # (factory.py only instantiates this when LLM_PROVIDER=openai).
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "OpenAI provider requires the `openai` package. "
                "Install it with: pip install openai"
            ) from exc

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        logger.info(
            "llm.provider.openai.init",
            extra={"model": self._model},
        )

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
    ) -> LLMResponse:
        """
        Call OpenAI Chat Completions with JSON mode enabled.

        The system prompt already contains NPC context and personality.
        JSON_INSTRUCTION is appended to make the expected keys explicit.
        """
        full_system = f"{system_prompt}\n\n{self.JSON_INSTRUCTION}"

        try:
            raw_response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": full_system},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.8,   # enough creativity for natural dialogue
                    max_tokens=512,    # NPC responses should be concise
                ),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "llm.openai.timeout",
                extra={"model": self._model, "timeout": LLM_TIMEOUT_SECONDS},
            )
            return LLMResponse.timeout()
        except Exception as exc:
            logger.error(
                "llm.openai.api_error",
                extra={"model": self._model, "error": str(exc)},
                exc_info=exc,
            )
            return LLMResponse.error()

        # Extract text content
        raw_content = raw_response.choices[0].message.content or ""

        try:
            data = self._extract_json(raw_content)
            result = LLMResponse.from_dict(data, raw=raw_content)
            logger.debug(
                "llm.openai.success",
                extra={
                    "model": self._model,
                    "behaviour": result.behaviour.value,
                    "secret_leaked": result.secret_leaked,
                },
            )
            return result
        except Exception as exc:
            logger.error(
                "llm.openai.parse_error",
                extra={
                    "model": self._model,
                    "raw": raw_content[:500],
                    "error": str(exc),
                },
            )
            return LLMResponse.error(raw=raw_content)
