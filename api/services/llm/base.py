"""
api/services/llm/base.py
────────────────────────
Abstract base class for all LLM providers and the shared response envelope.

Every concrete provider (OpenAI, Groq, Anthropic) must:
  1. Inherit from BaseLLMProvider
  2. Implement `complete(system_prompt, user_message, **kwargs) → LLMResponse`
  3. Apply a 10-second timeout to the underlying HTTP call
  4. Return a structured LLMResponse — never raise on timeout/parse failure;
     instead set `timed_out=True` or `parse_error=True` so the caller
     (npc_service.interact) can return a graceful fallback.

LLMResponse wire contract (parsed from provider JSON):
  {
    "npc_response":  str,               ← in-character reply text
    "state_delta": {                    ← emotional state changes
      "stress":      float [-1.0, 1.0],
      "trust":       float [-1.0, 1.0],
      "suspicion":   float [-1.0, 1.0],
      "cooperation": float [-1.0, 1.0]
    },
    "behaviour":    str,                ← one of the NPCBehaviour values
    "secret_leaked": str | null         ← secret id or null
  }

The provider is responsible for instructing the LLM to return exactly this
JSON structure. npc_service validates `secret_leaked` server-side against
the stress threshold — the LLM cannot force a reveal unilaterally.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from api.schemas.npc import NPCBehaviour, NPCStateDelta

logger = logging.getLogger(__name__)

# ── Timeout applied to every provider API call ─────────────────────────────────
LLM_TIMEOUT_SECONDS: float = 10.0


@dataclass
class LLMResponse:
    """
    Structured response returned by every LLM provider.

    Success path: `timed_out=False`, `parse_error=False`, all fields populated.
    Timeout path: `timed_out=True` — npc_service returns a fallback response
                  and leaves NPC state UNCHANGED.
    Parse error:  `parse_error=True` — provider received a response but could
                  not extract a valid JSON payload. Also triggers fallback.

    `raw_content` stores the original string from the provider for debugging;
    it is never forwarded to the client.
    """

    # ── Core response fields ──────────────────────────────────────────────────
    npc_response: str = ""
    state_delta: NPCStateDelta = field(default_factory=NPCStateDelta)
    behaviour: NPCBehaviour = NPCBehaviour.cooperative
    secret_leaked: Optional[str] = None

    # ── Meta / diagnostics ────────────────────────────────────────────────────
    timed_out: bool = False
    parse_error: bool = False
    raw_content: str = ""

    @property
    def is_valid(self) -> bool:
        """True if the response can be used to update NPC state."""
        return not self.timed_out and not self.parse_error

    @classmethod
    def from_dict(cls, data: dict[str, Any], raw: str = "") -> "LLMResponse":
        """
        Parse a provider-returned dict into an LLMResponse.

        Validates and coerces each field with sensible fallbacks:
        - Unknown behaviour strings fall back to `cooperative`
        - Out-of-range delta values are clamped by NPCStateDelta validation
        - Missing keys use field defaults
        """
        # Parse state_delta — clamp via Pydantic validation
        raw_delta = data.get("state_delta", {})
        try:
            state_delta = NPCStateDelta(
                stress=float(raw_delta.get("stress", 0.0)),
                trust=float(raw_delta.get("trust", 0.0)),
                suspicion=float(raw_delta.get("suspicion", 0.0)),
                cooperation=float(raw_delta.get("cooperation", 0.0)),
            )
        except Exception:
            logger.warning("llm.response.delta_parse_failed", extra={"raw_delta": raw_delta})
            state_delta = NPCStateDelta()

        # Parse behaviour — unknown values fall back to cooperative
        behaviour_str = str(data.get("behaviour", "cooperative"))
        try:
            behaviour = NPCBehaviour(behaviour_str)
        except ValueError:
            logger.warning(
                "llm.response.unknown_behaviour",
                extra={"behaviour": behaviour_str},
            )
            behaviour = NPCBehaviour.cooperative

        # Parse secret_leaked — must be a non-empty string or None
        secret_leaked_raw = data.get("secret_leaked")
        secret_leaked = (
            str(secret_leaked_raw)
            if secret_leaked_raw and isinstance(secret_leaked_raw, str)
            else None
        )

        return cls(
            npc_response=str(data.get("npc_response", "")),
            state_delta=state_delta,
            behaviour=behaviour,
            secret_leaked=secret_leaked,
            raw_content=raw,
        )

    @classmethod
    def timeout(cls, raw: str = "") -> "LLMResponse":
        """Factory: create a timed-out LLMResponse."""
        return cls(timed_out=True, raw_content=raw)

    @classmethod
    def error(cls, raw: str = "") -> "LLMResponse":
        """Factory: create a parse-error LLMResponse."""
        return cls(parse_error=True, raw_content=raw)


class BaseLLMProvider(ABC):
    """
    Abstract base for all LLM provider implementations.

    Subclasses implement `complete()` which accepts a system prompt
    (containing NPC personality, secrets, memory, and emotional state)
    and the player's message, then returns a structured LLMResponse.

    The `complete()` contract:
      - MUST apply LLM_TIMEOUT_SECONDS to the underlying API call.
      - MUST return LLMResponse.timeout() on asyncio.TimeoutError.
      - MUST return LLMResponse.error() on JSON parse failure.
      - MUST NOT raise exceptions to the caller.
      - SHOULD instruct the LLM to respond in the JSON wire format defined
        in this module's docstring.
    """

    # ── JSON instruction appended to every system prompt ──────────────────────
    # Providers that support `response_format={"type": "json_object"}` natively
    # (OpenAI, Groq) still receive this so the LLM produces the right keys.
    # Anthropic (which does not support response_format) relies on this entirely.
    JSON_INSTRUCTION: str = """
You must respond with ONLY a valid JSON object. No prose, no markdown, no code fences.

Required JSON structure:
{
  "npc_response": "<your in-character reply as a string>",
  "state_delta": {
    "stress":      <float between -1.0 and 1.0>,
    "trust":       <float between -1.0 and 1.0>,
    "suspicion":   <float between -1.0 and 1.0>,
    "cooperation": <float between -1.0 and 1.0>
  },
  "behaviour": "<one of: cooperative, deflecting, nervous, hostile, confessing>",
  "secret_leaked": "<secret_id string if you revealed a secret this turn, or null>"
}

Rules for state_delta:
- Keep deltas small and organic: typically ±0.05 to ±0.25 per turn.
- Aggressive or clever questions raise stress and suspicion.
- Empathetic or non-threatening questions raise trust and cooperation.
- Hostile accusations sharply raise stress but reduce cooperation.

Rules for secret_leaked:
- Set to the secret's id string ONLY if you are revealing it in npc_response.
- If you are not revealing any secret, set to null.
""".strip()

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
    ) -> LLMResponse:
        """
        Call the LLM and return a structured LLMResponse.

        Args:
            system_prompt: Full NPC context prompt built by npc_service.
                           Includes personality, secrets, emotional state,
                           behaviour tells, and recent memory.
            user_message:  The player's raw message (InteractRequest.player_message).

        Returns:
            LLMResponse — always. Never raises.
        """

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        """
        Extract and parse a JSON object from LLM output.

        Handles three common LLM response patterns:
          1. Clean JSON: `{ ... }`
          2. Fenced JSON: ```json\\n{ ... }\\n```
          3. JSON embedded in prose: finds the first `{` and last `}`

        Raises `ValueError` if no valid JSON object is found.
        """
        content = content.strip()

        # Pattern 1: clean JSON
        if content.startswith("{"):
            return json.loads(content)

        # Pattern 2: strip markdown code fences
        if "```" in content:
            # Find content between the outermost fences
            start = content.find("```")
            end = content.rfind("```")
            if start != end:
                inner = content[start + 3:end]
                # Strip optional language tag (```json)
                if inner.startswith("json"):
                    inner = inner[4:]
                return json.loads(inner.strip())

        # Pattern 3: find first { and last }
        brace_start = content.find("{")
        brace_end = content.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            return json.loads(content[brace_start:brace_end + 1])

        raise ValueError(f"No JSON object found in content: {content[:200]!r}")
