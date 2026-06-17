"""
api/routers/npcs.py
────────────────────
FastAPI router for all NPC endpoints under `/v1/npcs`.

All endpoints require authentication via `Depends(get_current_user)`.

Endpoints
─────────
POST   /v1/npcs                           → 201 NPCResponse          (create NPC)
GET    /v1/npcs/{npc_id}                  → 200 NPCResponse          (get NPC)
GET    /v1/npcs/session/{session_id}      → 200 list[NPCResponse]    (list session NPCs)
POST   /v1/npcs/{npc_id}/interact        → 200 InteractResponse      (player ↔ NPC)
GET    /v1/npcs/{npc_id}/memory          → 200 NPCMemoryResponse     (interaction history)
POST   /v1/npcs/seed/{session_id}        → 201 NPCResponse           (seed Marcus Webb)

Route ordering:
  /npcs/session/{session_id} and /npcs/seed/{session_id} MUST be registered
  BEFORE /npcs/{npc_id} otherwise FastAPI will try to parse the literal
  segments "session" and "seed" as UUIDs and return 422.

WebSocket events:
  The interact endpoint triggers `npc_state_changed` on the session's
  Redis pub/sub channel via npc_service._publish_npc_state_changed —
  this happens inside npc_service.interact(), not in the router.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from api.dependencies import get_current_user, get_db, get_redis
from api.models.npc import NPC
from api.models.player import Player
from api.schemas.npc import (
    InteractRequest,
    InteractResponse,
    NPCCreate,
    NPCMemoryResponse,
    NPCResponse,
)
from api.services import npc_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/npcs", tags=["NPCs"])


# ── POST /npcs ─────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=NPCResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new NPC in a session",
    responses={
        201: {"description": "NPC created successfully"},
        404: {"description": "Session not found"},
        422: {"description": "Validation error"},
    },
)
async def create_npc(
    payload: NPCCreate,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NPCResponse:
    """
    Spawn a new NPC into a session with a full personality definition.

    - `secrets` are stored server-side and never returned in the response.
    - `initial_emotional_state` defaults to the spec-defined starting values.
    - The creating player must be authenticated (though any player can create
      an NPC — host restriction is a Phase 3 concern).
    """
    npc = await npc_service.create_npc(payload, db)
    return npc_service.build_npc_response(npc)


# ── GET /npcs/session/{session_id} ────────────────────────────────────────────
# MUST come before /{npc_id} to prevent "session" being parsed as a UUID.

@router.get(
    "/session/{session_id}",
    response_model=list[NPCResponse],
    status_code=status.HTTP_200_OK,
    summary="List all NPCs in a session",
    responses={
        404: {"description": "Session not found"},
    },
)
async def list_session_npcs(
    session_id: UUID,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NPCResponse]:
    """
    Return all NPCs bound to the given session.

    Secrets are excluded from every NPCResponse in the list.
    """
    result = await db.execute(
        select(NPC).where(NPC.session_id == session_id)
    )
    npcs = result.scalars().all()
    return [npc_service.build_npc_response(npc) for npc in npcs]


# ── POST /npcs/seed/{session_id} ──────────────────────────────────────────────
# MUST come before /{npc_id} to prevent "seed" being parsed as a UUID.

@router.post(
    "/seed/{session_id}",
    response_model=NPCResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Seed Marcus Webb into a session",
    responses={
        201: {"description": "Marcus Webb created in session"},
        404: {"description": "NPC data file not found"},
    },
)
async def seed_marcus_webb(
    session_id: UUID,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NPCResponse:
    """
    Convenience endpoint: load `marcus_webb.json` and spawn him into the session.

    This is the fast path for the *Echoes of Truth* game — no need to POST
    a full NPCCreate payload; the character definition is baked into the
    server's data files.

    Equivalent to:
        npc_create = load_npc_from_file("marcus_webb.json")
        npc_create.session_id = str(session_id)
        POST /v1/npcs with npc_create
    """
    npc_create = load_npc_from_file("marcus_webb.json")
    npc_create_with_session = NPCCreate(
        **{**npc_create.model_dump(), "session_id": str(session_id)}
    )
    npc = await npc_service.create_npc(npc_create_with_session, db)
    logger.info(
        "npc.marcus_webb.seeded",
        extra={"session_id": str(session_id), "npc_id": str(npc.id)},
    )
    return npc_service.build_npc_response(npc)


# ── GET /npcs/{npc_id} ────────────────────────────────────────────────────────

@router.get(
    "/{npc_id}",
    response_model=NPCResponse,
    status_code=status.HTTP_200_OK,
    summary="Get NPC by ID",
    responses={
        404: {"description": "NPC not found"},
    },
)
async def get_npc(
    npc_id: UUID,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NPCResponse:
    """
    Retrieve the current state of an NPC.

    Returns the live `current_emotional_state` and derived `current_behaviour`.
    Secrets are never included in the response.
    """
    npc = await npc_service.get_npc_or_404(npc_id, db)
    return npc_service.build_npc_response(npc)


# ── POST /npcs/{npc_id}/interact ─────────────────────────────────────────────

@router.post(
    "/{npc_id}/interact",
    response_model=InteractResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message to the NPC",
    responses={
        200: {"description": "NPC responded (even on LLM timeout — fallback used)"},
        404: {"description": "NPC not found"},
    },
)
async def interact(
    npc_id: UUID,
    payload: InteractRequest,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> InteractResponse:
    """
    Send a player message to the NPC and receive an in-character response.

    **Full 12-step pipeline:**
    1. Load NPC + deserialise emotional state and secrets
    2. Fetch recent memory (Redis hot cache → Postgres cold fallback)
    3. Build LLM system prompt (personality + state + memory + secrets)
    4. Call LLM with 10-second timeout
    5. On timeout/error → return fallback response, **NPC state unchanged**
    6. Server-side secret validation (stress gate + known-ID check)
    7. Apply emotional state delta (clamped to [0.0, 1.0])
    8. Classify new behaviour from updated state
    9. Persist to Postgres (`npc_interactions` + update `npcs.current_state`)
    10. Push to Redis hot cache (LPUSH + LTRIM 20 + EXPIRE 24h)
    11. Publish `npc_state_changed` to `session:{session_id}` WebSocket channel
    12. Return `InteractResponse`

    **On LLM failure:** Returns HTTP 200 with a canned in-character response.
    The NPC's emotional state and secrets are left completely unchanged.
    No database writes occur on failure.
    """
    return await npc_service.interact(
        npc_id=npc_id,
        player_id=current_user.id,
        request=payload,
        db=db,
        redis=redis,
    )


# ── GET /npcs/{npc_id}/memory ─────────────────────────────────────────────────

@router.get(
    "/{npc_id}/memory",
    response_model=NPCMemoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get NPC interaction history",
    responses={
        404: {"description": "NPC not found"},
    },
)
async def get_npc_memory(
    npc_id: UUID,
    limit: int = Query(default=20, ge=1, le=100, description="Max entries to return."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NPCMemoryResponse:
    """
    Retrieve paginated interaction history for an NPC from cold storage (Postgres).

    Results are returned in chronological order (oldest first).
    Use `limit` and `offset` for pagination.
    This endpoint always reads from Postgres — use the WebSocket channel for
    live state updates during an active session.
    """
    return await npc_service.get_memory(
        npc_id=npc_id,
        db=db,
        limit=limit,
        offset=offset,
    )


# ── Utility: load NPC definition from data file ───────────────────────────────

def load_npc_from_file(filename: str) -> NPCCreate:
    """
    Load an NPC definition from `api/data/npcs/{filename}`.

    The JSON file matches the NPCCreate schema minus `session_id`, which
    is injected at spawn time. A placeholder UUID is set so Pydantic
    validation passes; callers must overwrite it before calling create_npc().

    Usage:
        npc_create = load_npc_from_file("marcus_webb.json")
        npc_create_with_session = NPCCreate(
            **{**npc_create.model_dump(), "session_id": str(session_id)}
        )
        npc = await npc_service.create_npc(npc_create_with_session, db)

    Raises:
        FileNotFoundError: if the file does not exist under api/data/npcs/
    """
    # Delegate to npc_service — the path resolution lives there
    return npc_service.load_npc_from_file(filename)
