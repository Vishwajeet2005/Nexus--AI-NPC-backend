"""
api/services/llm/groq_provider.py
──────────────────────────────────
Groq provider implementation using the official `groq` async client.

Groq is the DEFAULT provider (LLM_PROVIDER=groq) because llama-3.1-8b-instant
delivers sub-second latency on Groq's LPU hardware — critical for an
interrogation game where response delays break immersion.

Configuration (from environment / pydantic Settings):
  GROQ_API_KEY   — required
  GROQ_MODEL     — default: llama-3.1-8b-instant

JSON enforcement:
  Uses `response_format={"type": "json_object"}` (supported by Groq for
  llama-3.1 models). Also appends JSON_INSTRUCTION to the system prompt
  to ensure correct key names.

Timeout:
  asyncio.wait_for wraps the API call with LLM_TIMEOUT_SECONDS (10s).
  On TimeoutError → returns LLMResponse.timeout().

Error handling:
  All exceptions are caught and logged. Callers always receive a valid LLMResponse.
"""

from __future__ import annotations

import asyncio
import logging

from api.services.llm.base import BaseLLMProvider, LLMResponse, LLM_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class GroqProvider(BaseLLMProvider):
    """LLM provider backed by Groq Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.1-8b-instant",
    ) -> None:
        """
        Args:
            api_key: Groq API key (GROQ_API_KEY).
            model:   Groq model to use. Default: llama-3.1-8b-instant.
                     Also works with: llama-3.1-70b-versatile, mixtral-8x7b-32768.
        """
        try:
            from groq import AsyncGroq
        except ImportError as exc:
            raise ImportError(
                "Groq provider requires the `groq` package. "
                "Install it with: pip install groq"
            ) from exc

        self._client = AsyncGroq(api_key=api_key)
        self._model = model
        logger.info(
            "llm.provider.groq.init",
            extra={"model": self._model},
        )

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
    ) -> LLMResponse:
        """
        Call Groq Chat Completions with JSON mode enabled.

        Groq's JSON mode is enabled per-model; llama-3.1-8b-instant and
        llama-3.1-70b-versatile both support `response_format=json_object`.
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
                    temperature=0.8,
                    max_tokens=512,
                ),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "llm.groq.timeout",
                extra={"model": self._model, "timeout": LLM_TIMEOUT_SECONDS},
            )
            return LLMResponse.timeout()
        except Exception as exc:
            logger.error(
                "llm.groq.api_error",
                extra={"model": self._model, "error": str(exc)},
                exc_info=exc,
            )
            return LLMResponse.error()

        raw_content = raw_response.choices[0].message.content or ""

        try:
            data = self._extract_json(raw_content)
            result = LLMResponse.from_dict(data, raw=raw_content)
            logger.debug(
                "llm.groq.success",
                extra={
                    "model": self._model,
                    "behaviour": result.behaviour.value,
                    "secret_leaked": result.secret_leaked,
                },
            )
            return result
        except Exception as exc:
            logger.error(
                "llm.groq.parse_error",
                extra={
                    "model": self._model,
                    "raw": raw_content[:500],
                    "error": str(exc),
                },
            )
            return LLMResponse.error(raw=raw_content)
