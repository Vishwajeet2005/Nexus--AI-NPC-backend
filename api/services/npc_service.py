"""
api/services/npc_service.py
────────────────────────────
Core NPC orchestration service — the brain of Phase 2.

Wires together EmotionService, MemoryService, and the LLM provider
into the full 12-step interact pipeline.

12-step interact() pipeline
───────────────────────────
 1.  Load NPC from Postgres (404 if not found)
 2.  Deserialise current_state → NPCEmotionalState
 3.  Deserialise secrets → list[NPCSecret]
 4.  Fetch recent memory (hot Redis → cold Postgres fallback)
 5.  Build system prompt (personality + secrets + state + memory)
 6.  Call LLM with 10s timeout via provider.complete()
 7.  On timeout / parse error → return _llm_fallback_response (state UNCHANGED)
 8.  Server-side secret validation:
       claimed_id must be a known secret ID
       AND current stress >= secret.reveal_threshold
       AND secret not already revealed
 9.  Apply NPCStateDelta → new NPCEmotionalState (clamped)
10.  Classify new behaviour
11.  Write Postgres: npc_interactions row + update npcs.current_state + secrets
12.  Push to Redis hot cache + publish npc_state_changed WS event
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from api.models.npc import NPC
from api.schemas.npc import (
    NPCBehaviour,
    NPCCreate,
    NPCEmotionalState,
    NPCMemoryEntry,
    NPCMemoryResponse,
    NPCPersonality,
    NPCResponse,
    NPCSecret,
    NPCMemoryScope,
    NPCStateDelta,
    NPCTell,
    InteractRequest,
    InteractResponse,
)
from api.services.emotion_service import emotion_service
from api.services.memory_service import memory_service
from api.services.llm import get_llm_provider
from api.services.realtime_service import publish_event

logger = logging.getLogger(__name__)

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data" / "npcs"

_FALLBACK_RESPONSE = (
    "I have already told you everything I know. "
    "I have nothing more to add at this time."
)


# ── System prompt builder ──────────────────────────────────────────────────────

def build_system_prompt(
    npc: NPC,
    personality: NPCPersonality,
    secrets: list[NPCSecret],
    current_state: NPCEmotionalState,
    current_behaviour: NPCBehaviour,
    memory: list[NPCMemoryEntry],
) -> str:
    """Build the full LLM system prompt from NPC context."""
    traits_str = ", ".join(personality.traits)

    parts: list[str] = [
        f"You are {npc.name}, a character in an interrogation game.",
        "",
        f"PERSONALITY TRAITS: {traits_str}",
        f"MOTIVATION: {personality.motivation}",
        f"FEAR: {personality.fear}",
        f"BACKGROUND: {personality.background}",
        f"SPEECH STYLE: {personality.speech_style}",
        "",
        "CURRENT EMOTIONAL STATE:",
        f"  Stress:      {current_state.stress:.2f}  (0=calm, 1=breaking)",
        f"  Trust:       {current_state.trust:.2f}  (0=hostile, 1=open)",
        f"  Suspicion:   {current_state.suspicion:.2f}  (0=unsuspicious, 1=paranoid)",
        f"  Cooperation: {current_state.cooperation:.2f}  (0=stonewalling, 1=fully cooperative)",
        "",
    ]

    # Behaviour mode + observable tell
    tell_map = {
        NPCBehaviour.cooperative: personality.tells.cooperative,
        NPCBehaviour.deflecting:  personality.tells.deflecting,
        NPCBehaviour.nervous:     personality.tells.nervous,
        NPCBehaviour.hostile:     personality.tells.hostile,
        NPCBehaviour.confessing:  personality.tells.nervous,
    }
    current_tell = tell_map.get(current_behaviour, personality.tells.cooperative)

    parts += [
        f"CURRENT BEHAVIOUR MODE: {current_behaviour.value.upper()}",
        f"PHYSICAL/VERBAL TELL: {current_tell}",
        "Your response must be consistent with these observable signals.",
        "",
    ]

    # Unrevealed secrets as private context
    unrevealed = [s for s in secrets if not s.is_revealed]
    if unrevealed:
        parts.append("PRIVATE CONTEXT (you know this — do NOT reveal unless forced):")
        for secret in unrevealed:
            parts.append(f"  - {secret.content}")
            parts.append(f"    (Reveal only if: {secret.reveal_trigger})")
        parts.append("")

    # Recent memory
    if memory:
        parts.append("RECENT CONVERSATION HISTORY:")
        for entry in memory:
            parts.append(f"  Player: {entry.player_message}")
            parts.append(f"  You:    {entry.npc_response}")
        parts.append("")

    # Interaction rules
    parts += [
        "INTERACTION RULES:",
        "1. Stay completely in character as " + npc.name + " at all times.",
        "2. Response length by mode: cooperative/nervous=2-4 sentences, "
        "deflecting=answer-with-question, hostile=1-2 terse sentences, "
        "confessing=longer emotional response.",
        "3. Never acknowledge you are an AI or NPC.",
        "4. Never break the fourth wall.",
        "5. Keep emotional state deltas small and organic (+-0.05 to +-0.25 per turn).",
        "6. Only set secret_leaked if you are explicitly revealing that secret in npc_response.",
    ]

    return "\n".join(parts)


# ── NPC CRUD ───────────────────────────────────────────────────────────────────

async def create_npc(payload: NPCCreate, db: AsyncSession) -> NPC:
    """Persist a new NPC row. Returns the ORM object after refresh."""
    session_uuid = UUID(payload.session_id)
    initial_state = payload.initial_emotional_state

    npc = NPC(
        session_id=session_uuid,
        name=payload.name,
        personality=payload.personality.model_dump(),
        secrets=[s.model_dump() for s in payload.secrets],
        initial_state=initial_state.model_dump(),
        current_state=initial_state.model_dump(),
        memory_scope=payload.memory_scope.value,
    )
    db.add(npc)
    await db.commit()
    await db.refresh(npc)

    logger.info(
        "npc.created",
        extra={"npc_id": str(npc.id), "npc_name": npc.name, "session_id": str(npc.session_id)},
    )
    return npc


async def get_npc_or_404(npc_id: UUID, db: AsyncSession) -> NPC:
    """Load NPC by PK; raise HTTP 404 if not found."""
    result = await db.execute(select(NPC).where(NPC.id == npc_id))
    npc: NPC | None = result.scalar_one_or_none()
    if npc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NPC not found.", "code": "NPC_NOT_FOUND"},
        )
    return npc


def build_npc_response(npc: NPC) -> NPCResponse:
    """
    Build a public NPCResponse from an ORM NPC row.

    SECURITY: secrets are intentionally NEVER included here.
    """
    current_state = NPCEmotionalState(**npc.current_state)
    personality = _deserialise_personality(npc.personality)
    behaviour = emotion_service.classify_behaviour(current_state)

    return NPCResponse(
        id=str(npc.id),
        session_id=str(npc.session_id),
        name=npc.name,
        personality=personality,
        current_emotional_state=current_state,
        current_behaviour=behaviour,
        memory_scope=NPCMemoryScope(npc.memory_scope),
        created_at=npc.created_at.isoformat(),
    )


# ── Interact pipeline ──────────────────────────────────────────────────────────

async def interact(
    npc_id: UUID,
    player_id: UUID,
    request: InteractRequest,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> InteractResponse:
    """Full 12-step NPC interaction pipeline."""

    # Step 1: Load NPC
    npc = await get_npc_or_404(npc_id, db)

    # Step 2: Deserialise emotional state
    current_state = NPCEmotionalState(**npc.current_state)

    # Step 3: Deserialise secrets
    secrets: list[NPCSecret] = [NPCSecret(**s) for s in (npc.secrets or [])]

    # Step 4: Fetch memory (hot → cold fallback)
    memory = await memory_service.get_memory_for_context(npc_id, db, redis)

    # Step 5: Build system prompt
    personality = _deserialise_personality(npc.personality)
    current_behaviour = emotion_service.classify_behaviour(current_state)

    system_prompt = build_system_prompt(
        npc=npc,
        personality=personality,
        secrets=secrets,
        current_state=current_state,
        current_behaviour=current_behaviour,
        memory=memory,
    )

    # Step 6: Call LLM
    provider = get_llm_provider()
    llm_response = await provider.complete(
        system_prompt=system_prompt,
        user_message=request.player_message,
    )

    # Step 7: Handle LLM failure — return fallback, state UNCHANGED
    if not llm_response.is_valid:
        logger.warning(
            "npc.interact.llm_fallback",
            extra={
                "npc_id": str(npc_id),
                "timed_out": llm_response.timed_out,
                "parse_error": llm_response.parse_error,
            },
        )
        return _llm_fallback_response(npc_id, current_state, current_behaviour)

    # Step 8: Server-side secret validation
    validated_secret: str | None = None
    updated_secrets = list(secrets)

    if llm_response.secret_leaked:
        validated_secret = _validate_secret_reveal(
            claimed_secret_id=llm_response.secret_leaked,
            secrets=updated_secrets,
            current_stress=current_state.stress,
        )
        if validated_secret:
            updated_secrets = [
                NPCSecret(**{**s.model_dump(), "is_revealed": True})
                if s.id == validated_secret else s
                for s in updated_secrets
            ]
            logger.info(
                "npc.secret_revealed",
                extra={"npc_id": str(npc_id), "secret_id": validated_secret, "stress": current_state.stress},
            )

    # Step 9: Apply delta
    new_state, new_behaviour = emotion_service.step(current_state, llm_response.state_delta)

    # Steps 10-11: Write Postgres
    interaction_row = await memory_service.write_interaction(
        db=db,
        npc_id=npc_id,
        session_id=npc.session_id,
        player_id=player_id,
        player_message=request.player_message,
        npc_response=llm_response.npc_response,
        behaviour=new_behaviour,
        state_before=current_state,
        state_after=new_state,
        secret_leaked=validated_secret,
    )

    npc.current_state = new_state.model_dump()
    npc.secrets = [s.model_dump() for s in updated_secrets]
    await db.commit()

    interaction_id = str(interaction_row.id)

    # Step 12a: Push to Redis hot cache
    memory_entry = NPCMemoryEntry(
        id=interaction_id,
        player_id=str(player_id),
        player_message=request.player_message,
        npc_response=llm_response.npc_response,
        behaviour=new_behaviour,
        state_before=current_state,
        state_after=new_state,
        secret_leaked=validated_secret,
        created_at=interaction_row.created_at.isoformat(),
    )
    await memory_service.push_hot_memory(npc_id, memory_entry, redis)

    # Step 12b: Publish WS event
    await _publish_npc_state_changed(
        redis=redis,
        session_id=npc.session_id,
        npc_id=npc_id,
        npc_name=npc.name,
        behaviour=new_behaviour,
        new_state=new_state,
        secret_leaked=validated_secret,
    )

    logger.info(
        "npc.interact.success",
        extra={
            "npc_id": str(npc_id),
            "player_id": str(player_id),
            "behaviour": new_behaviour.value,
            "stress": new_state.stress,
            "secret_leaked": validated_secret,
        },
    )

    return InteractResponse(
        npc_response=llm_response.npc_response,
        behaviour=new_behaviour,
        emotional_state=new_state,
        state_delta=llm_response.state_delta,
        secret_leaked=validated_secret,
        interaction_id=interaction_id,
    )


# ── Memory read ────────────────────────────────────────────────────────────────

async def get_memory(
    npc_id: UUID,
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> NPCMemoryResponse:
    """GET /v1/npcs/{npc_id}/memory — paginated cold storage read."""
    await get_npc_or_404(npc_id, db)
    entries, total = await memory_service.get_cold_memory(
        npc_id=npc_id,
        db=db,
        limit=limit,
        offset=offset,
    )
    return NPCMemoryResponse(entries=entries, total=total, limit=limit, offset=offset)


# ── NPC data file loader ───────────────────────────────────────────────────────

def load_npc_from_file(filename: str) -> NPCCreate:
    """
    Load an NPC definition from api/data/npcs/{filename}.

    session_id must be injected by the caller before passing to create_npc().
    """
    path = _DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"NPC data file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    if "session_id" not in data:
        data["session_id"] = "00000000-0000-0000-0000-000000000000"

    return NPCCreate(**data)


# ── Private helpers ────────────────────────────────────────────────────────────

def _deserialise_personality(raw: dict[str, Any]) -> NPCPersonality:
    tells_raw = raw.get("tells", {})
    return NPCPersonality(
        traits=raw["traits"],
        motivation=raw["motivation"],
        fear=raw["fear"],
        background=raw["background"],
        speech_style=raw["speech_style"],
        tells=NPCTell(
            cooperative=tells_raw.get("cooperative", ""),
            deflecting=tells_raw.get("deflecting", ""),
            nervous=tells_raw.get("nervous", ""),
            hostile=tells_raw.get("hostile", ""),
        ),
    )


def _validate_secret_reveal(
    claimed_secret_id: str,
    secrets: list[NPCSecret],
    current_stress: float,
) -> str | None:
    """
    Server-side gate: return secret ID only if all three conditions hold:
      1. ID matches a known secret
      2. current_stress >= reveal_threshold
      3. secret has not already been revealed
    """
    for secret in secrets:
        if secret.id != claimed_secret_id:
            continue
        if secret.is_revealed:
            logger.debug("npc.secret.already_revealed", extra={"secret_id": claimed_secret_id})
            return None
        if current_stress < secret.reveal_threshold:
            logger.info(
                "npc.secret.below_threshold",
                extra={
                    "secret_id": claimed_secret_id,
                    "stress": current_stress,
                    "threshold": secret.reveal_threshold,
                },
            )
            return None
        return secret.id

    logger.warning("npc.secret.unknown_id", extra={"claimed_id": claimed_secret_id})
    return None


def _llm_fallback_response(
    npc_id: UUID,
    current_state: NPCEmotionalState,
    current_behaviour: NPCBehaviour,
) -> InteractResponse:
    """Safe in-character fallback on LLM failure. State unchanged, zero delta."""
    return InteractResponse(
        npc_response=_FALLBACK_RESPONSE,
        behaviour=current_behaviour,
        emotional_state=current_state,
        state_delta=NPCStateDelta(),
        secret_leaked=None,
        interaction_id="00000000-0000-0000-0000-000000000000",
    )


async def _publish_npc_state_changed(
    redis: aioredis.Redis,
    session_id: UUID,
    npc_id: UUID,
    npc_name: str,
    behaviour: NPCBehaviour,
    new_state: NPCEmotionalState,
    secret_leaked: str | None,
) -> None:
    """Publish npc_state_changed to session WebSocket channel."""
    await publish_event(
        redis=redis,
        session_id=session_id,
        event_type="npc_state_changed",
        data={
            "npc_id": str(npc_id),
            "npc_name": npc_name,
            "behaviour": behaviour.value,
            "emotional_state": new_state.model_dump(),
            "secret_leaked": secret_leaked,
        },
    )
