"""
api/schemas/npc.py
──────────────────
Pydantic v2 schemas for all NPC endpoints and internal service contracts.

Schema hierarchy:
  NPCPersonality   ← contains NPCTell
  NPCSecret        ← tracks reveal state
  NPCEmotionalState← four bounded floats
  NPCStateDelta    ← signed deltas applied by EmotionService
  NPCCreate        ← request body for POST /v1/npcs
  NPCResponse      ← API response (secrets EXCLUDED for security)
  InteractRequest  ← POST /v1/npcs/{id}/interact body
  InteractResponse ← full interact result
  NPCMemoryEntry   ← single interaction record (GET /memory)

Security note:
  NPCSecret is used internally (stored in JSONB, passed to LLM context)
  but is NEVER included in NPCResponse. The router builds NPCResponse
  explicitly — it does not use model_validate on the ORM row directly.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Enumerations ───────────────────────────────────────────────────────────────

class NPCMemoryScope(str, Enum):
    """Controls whether NPC memory persists across sessions."""
    session = "session"
    persistent = "persistent"


class NPCBehaviour(str, Enum):
    """
    Discrete behaviour states produced by EmotionService.classify_behaviour().

    Priority order (first match wins in the state machine):
      confessing  — stress ≥ 0.85 (highest pressure)
      hostile     — stress > 0.70 AND trust < 0.20
      nervous     — stress > 0.50 AND trust < 0.40
      deflecting  — suspicion > 0.50 AND stress < 0.70
      cooperative — catch-all fallback
    """
    cooperative = "cooperative"
    deflecting = "deflecting"
    nervous = "nervous"
    hostile = "hostile"
    confessing = "confessing"


# ── Personality sub-schemas ────────────────────────────────────────────────────

class NPCTell(BaseModel):
    """
    Observable behavioural signals the NPC exhibits in each mode.

    These are injected into the LLM system prompt as stage-direction
    cues so the model produces physically/verbally consistent responses.
    E.g. in hostile mode Marcus "crosses arms, goes monosyllabic".
    """

    model_config = ConfigDict(frozen=True)

    cooperative: str = Field(
        ...,
        description="Physical/verbal signals when the NPC is cooperative.",
        examples=["Leans back slightly. Speaks in longer sentences."],
    )
    deflecting: str = Field(
        ...,
        description="Signals when deflecting — avoidance behaviours.",
        examples=["Answers a question with a question."],
    )
    nervous: str = Field(
        ...,
        description="Signals when nervous — stress micro-expressions.",
        examples=["Uses filler phrases like 'as I said'."],
    )
    hostile: str = Field(
        ...,
        description="Signals when hostile — shutdown behaviours.",
        examples=["Crosses arms. Goes completely monosyllabic."],
    )


class NPCPersonality(BaseModel):
    """
    Complete personality definition stored in the `npcs.personality` JSONB column.

    All fields are fed into the LLM system prompt verbatim at interact time.
    `tells` provides per-behaviour stage directions so the model stays
    behaviourally consistent regardless of the underlying model or provider.
    """

    model_config = ConfigDict(frozen=True)

    traits: list[str] = Field(
        ...,
        min_length=1,
        description="Personality trait adjectives, e.g. ['calculated', 'defensive', 'prideful'].",
    )
    motivation: str = Field(
        ...,
        description="The NPC's core driving goal — what they want above all else.",
    )
    fear: str = Field(
        ...,
        description="The NPC's primary fear — what they are most desperate to avoid.",
    )
    background: str = Field(
        ...,
        description="2–3 sentence backstory that grounds the character.",
    )
    speech_style: str = Field(
        ...,
        description="How this NPC talks: terse, formal, sarcastic, verbose, etc.",
    )
    tells: NPCTell = Field(
        ...,
        description="Per-behaviour stage directions injected into the LLM prompt.",
    )


# ── Secret schema ──────────────────────────────────────────────────────────────

class NPCSecret(BaseModel):
    """
    A piece of hidden information the NPC possesses.

    Secrets are stored in `npcs.secrets` JSONB and NEVER returned in API
    responses. They are provided to the LLM as private context so it can
    craft responses that are consistent with the secret without revealing it
    prematurely.

    Reveal logic (enforced server-side, not by the LLM):
      secret_leaked in the LLM response is only accepted if:
        1. current stress >= reveal_threshold
        2. The secret ID matches a known secret for this NPC
    """

    id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Snake_case slug uniquely identifying this secret, e.g. 'alibi_weakness'.",
    )
    content: str = Field(
        ...,
        description="The actual secret content. Provided to the LLM as private context.",
    )
    reveal_threshold: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Minimum stress level at which this secret CAN be revealed.",
    )
    reveal_trigger: str = Field(
        ...,
        description="Natural language description of what player action triggers the reveal.",
    )
    is_revealed: bool = Field(
        default=False,
        description="True once this secret has been leaked in the current session.",
    )


# ── Emotional state schemas ────────────────────────────────────────────────────

class NPCEmotionalState(BaseModel):
    """
    The NPC's live emotional state — four bounded floats in [0.0, 1.0].

    Defaults reflect a fresh NPC at the start of an interrogation:
      stress      0.2  — baseline low, room to escalate
      trust       0.5  — neutral
      suspicion   0.3  — slightly wary of the interrogator
      cooperation 0.6  — professionally compliant until pushed

    Stored in `npcs.current_state` JSONB and updated after every interaction.
    """

    model_config = ConfigDict(frozen=True)

    stress: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Psychological pressure level. Drives secret reveals at high values.",
    )
    trust: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How much the NPC trusts the interrogating player.",
    )
    suspicion: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="How suspicious the NPC is of the player's motives.",
    )
    cooperation: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Willingness to engage and answer questions.",
    )


class NPCStateDelta(BaseModel):
    """
    Signed deltas returned by the LLM after each interaction.

    Values are in [-1.0, 1.0]. EmotionService.apply_delta() adds these to
    the current NPCEmotionalState and clamps all results to [0.0, 1.0].

    Example: stress=+0.15 means "this exchange raised stress by 15 points".
    The LLM is instructed to keep deltas small (typically ±0.05 to ±0.25)
    so state drift feels organic rather than step-function.
    """

    model_config = ConfigDict(frozen=True)

    stress: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Signed delta to apply to stress.",
    )
    trust: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Signed delta to apply to trust.",
    )
    suspicion: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Signed delta to apply to suspicion.",
    )
    cooperation: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Signed delta to apply to cooperation.",
    )


# ── NPC CRUD schemas ───────────────────────────────────────────────────────────

class NPCCreate(BaseModel):
    """
    POST /v1/npcs request body.

    `session_id` is a string UUID (not uuid.UUID) so the schema is
    JSON-serialisation-safe when loaded from files (e.g. marcus_webb.json)
    without requiring extra UUID coercion at the caller.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: str = Field(
        ...,
        description="UUID of the session this NPC belongs to.",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable NPC name shown to players.",
        examples=["Marcus Webb"],
    )
    personality: NPCPersonality = Field(
        ...,
        description="Full personality definition including traits, tells, and backstory.",
    )
    secrets: list[NPCSecret] = Field(
        default_factory=list,
        description="Hidden information the NPC possesses. Never returned in API responses.",
    )
    initial_emotional_state: NPCEmotionalState = Field(
        default_factory=NPCEmotionalState,
        description="Starting emotional state. Defaults to the NPCEmotionalState defaults.",
    )
    confession_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description=(
            "Stress level at which the NPC may begin confessing. "
            "Compared against NPCEmotionalState.stress after apply_delta."
        ),
    )
    memory_scope: NPCMemoryScope = Field(
        default=NPCMemoryScope.session,
        description="'session' = ephemeral; 'persistent' = survives across sessions.",
    )


class NPCResponse(BaseModel):
    """
    Public NPC representation returned by GET/POST /v1/npcs endpoints.

    SECURITY: `secrets` is intentionally absent. The ORM `npc.secrets`
    JSONB column must NEVER be included here. Routes build this schema
    explicitly rather than calling model_validate on the ORM row.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="NPC UUID as string.")
    session_id: str = Field(..., description="Session UUID as string.")
    name: str
    personality: NPCPersonality
    current_emotional_state: NPCEmotionalState
    current_behaviour: NPCBehaviour = Field(
        ...,
        description="Behaviour derived from current_emotional_state via EmotionService.",
    )
    memory_scope: NPCMemoryScope
    created_at: str = Field(..., description="ISO 8601 creation timestamp.")


# ── Interaction schemas ────────────────────────────────────────────────────────

class InteractRequest(BaseModel):
    """POST /v1/npcs/{npc_id}/interact request body."""

    model_config = ConfigDict(str_strip_whitespace=True)

    player_message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The player's message to the NPC.",
        examples=["Where were you on the night of the 14th?"],
    )


class InteractResponse(BaseModel):
    """
    POST /v1/npcs/{npc_id}/interact response.

    `secret_leaked` is the slug of the revealed secret (e.g. "alibi_weakness")
    or null if no secret was revealed this turn.

    `state_delta` shows the raw emotional shift from this interaction so
    the client can animate gauge transitions.
    """

    model_config = ConfigDict(frozen=True)

    npc_response: str = Field(
        ...,
        description="The NPC's in-character response text.",
    )
    behaviour: NPCBehaviour = Field(
        ...,
        description="NPC's behaviour state after applying the delta.",
    )
    emotional_state: NPCEmotionalState = Field(
        ...,
        description="Full emotional state AFTER applying the delta.",
    )
    state_delta: NPCStateDelta = Field(
        ...,
        description="The raw delta applied this turn (for client-side animation).",
    )
    secret_leaked: Optional[str] = Field(
        default=None,
        description="Secret ID if a secret was revealed this turn, else null.",
        examples=["alibi_weakness", None],
    )
    interaction_id: str = Field(
        ...,
        description="UUID of the npc_interactions row created for this turn.",
    )


# ── Memory schema ──────────────────────────────────────────────────────────────

class NPCMemoryEntry(BaseModel):
    """
    A single interaction record returned by GET /v1/npcs/{npc_id}/memory.

    Built from either the Redis hot cache (recent) or the Postgres
    npc_interactions table (full history). Both storage layers produce
    the same schema so callers never know which tier was hit.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="npc_interactions UUID as string.")
    player_id: str = Field(..., description="Player UUID as string.")
    player_message: str
    npc_response: str
    behaviour: NPCBehaviour
    state_before: NPCEmotionalState
    state_after: NPCEmotionalState
    secret_leaked: Optional[str] = Field(
        default=None,
        description="Secret ID if leaked during this interaction, else null.",
    )
    created_at: str = Field(..., description="ISO 8601 timestamp.")


class NPCMemoryResponse(BaseModel):
    """
    Paginated response for GET /v1/npcs/{npc_id}/memory.
    """

    model_config = ConfigDict(frozen=True)

    entries: list[NPCMemoryEntry]
    total: int = Field(..., ge=0, description="Total interactions in cold storage.")
    limit: int = Field(..., ge=1, description="Max entries returned.")
    offset: int = Field(..., ge=0, description="Pagination offset.")
