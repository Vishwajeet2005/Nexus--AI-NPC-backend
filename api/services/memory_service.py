"""
api/services/memory_service.py
───────────────────────────────
Two-tier NPC memory system.

HOT tier  — Redis list `npc_memory:{npc_id}`
  - Last HOT_MEMORY_LIMIT (20) interactions as JSON strings
  - Newest entry at index 0 (LPUSH)
  - LTRIM after every write to enforce the cap
  - EXPIRE 86400 (24 hours) refreshed on every write

COLD tier — Postgres `npc_interactions` table
  - Full immutable audit trail, every interaction ever
  - Source of truth for pagination and analytics

Read path:
  1. Try Redis first — O(1) range read
  2. On Redis miss (key absent or empty), query Postgres last 20
  3. Backfill Redis from Postgres result so subsequent reads are fast

Write path (called once per successful interact, after Postgres commit):
  1. Write Postgres row (done by npc_service before calling this)
  2. LPUSH JSON entry to Redis list
  3. LTRIM list to HOT_MEMORY_LIMIT
  4. EXPIRE key to HOT_MEMORY_TTL
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from api.config import get_settings
from api.models.npc import NPCInteraction
from api.schemas.npc import NPCBehaviour, NPCEmotionalState, NPCMemoryEntry

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Redis key template ─────────────────────────────────────────────────────────
HOT_MEMORY_KEY = "npc_memory:{npc_id}"
HOT_MEMORY_LIMIT: int = settings.npc_memory_hot_limit    # 20
HOT_MEMORY_TTL: int = settings.npc_memory_ttl_seconds    # 86400


def _memory_key(npc_id: str | UUID) -> str:
    return HOT_MEMORY_KEY.format(npc_id=str(npc_id))


def _entry_to_json(entry: NPCMemoryEntry) -> str:
    return json.dumps(entry.model_dump(), separators=(",", ":"))


def _json_to_entry(raw: str | bytes) -> NPCMemoryEntry | None:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        data = json.loads(raw)
        return NPCMemoryEntry(
            id=data["id"],
            player_id=data["player_id"],
            player_message=data["player_message"],
            npc_response=data["npc_response"],
            behaviour=NPCBehaviour(data["behaviour"]),
            state_before=NPCEmotionalState(**data["state_before"]),
            state_after=NPCEmotionalState(**data["state_after"]),
            secret_leaked=data.get("secret_leaked"),
            created_at=data["created_at"],
        )
    except Exception as exc:
        logger.warning(
            "memory.parse_error",
            extra={"error": str(exc), "raw": str(raw)[:200]},
        )
        return None


def _interaction_to_entry(row: NPCInteraction) -> NPCMemoryEntry:
    return NPCMemoryEntry(
        id=str(row.id),
        player_id=str(row.player_id),
        player_message=row.player_message,
        npc_response=row.npc_response,
        behaviour=NPCBehaviour(row.behaviour),
        state_before=NPCEmotionalState(**row.state_before),
        state_after=NPCEmotionalState(**row.state_after),
        secret_leaked=row.secret_leaked,
        created_at=row.created_at.isoformat(),
    )


class MemoryService:
    """Stateless service — pass `db` and `redis` at each call site."""

    # ── Hot tier (Redis) ────────────────────────────────────────────────────────

    async def get_hot_memory(
        self,
        npc_id: str | UUID,
        redis: aioredis.Redis,
    ) -> list[NPCMemoryEntry]:
        """
        Return up to HOT_MEMORY_LIMIT entries from the Redis list.

        List is stored newest-first (LPUSH); we reverse before returning
        so callers receive oldest-first (chronological) order.
        Returns [] on cache miss, key absence, or any Redis error.
        """
        key = _memory_key(npc_id)
        try:
            raw_entries = await redis.lrange(key, 0, HOT_MEMORY_LIMIT - 1)
        except Exception as exc:
            logger.warning(
                "memory.hot.read_error",
                extra={"npc_id": str(npc_id), "error": str(exc)},
            )
            return []

        if not raw_entries:
            return []

        entries: list[NPCMemoryEntry] = []
        for raw in raw_entries:
            entry = _json_to_entry(raw)
            if entry is not None:
                entries.append(entry)

        # Redis list is newest-first; return chronological order
        entries.reverse()
        logger.debug(
            "memory.hot.hit",
            extra={"npc_id": str(npc_id), "count": len(entries)},
        )
        return entries

    async def push_hot_memory(
        self,
        npc_id: str | UUID,
        entry: NPCMemoryEntry,
        redis: aioredis.Redis,
    ) -> None:
        """
        Write one interaction to the Redis hot cache.

        LPUSH  → newest entry at index 0
        LTRIM  → cap list at HOT_MEMORY_LIMIT entries
        EXPIRE → reset TTL to HOT_MEMORY_TTL seconds

        All three commands in a single pipeline for atomicity.
        Failures are logged as warnings — never raise.
        """
        key = _memory_key(npc_id)
        payload = _entry_to_json(entry)
        try:
            async with redis.pipeline(transaction=True) as pipe:
                pipe.lpush(key, payload)
                pipe.ltrim(key, 0, HOT_MEMORY_LIMIT - 1)
                pipe.expire(key, HOT_MEMORY_TTL)
                await pipe.execute()
            logger.debug(
                "memory.hot.write",
                extra={"npc_id": str(npc_id), "interaction_id": entry.id},
            )
        except Exception as exc:
            logger.warning(
                "memory.hot.write_error",
                extra={"npc_id": str(npc_id), "error": str(exc)},
            )

    async def invalidate_hot_memory(
        self,
        npc_id: str | UUID,
        redis: aioredis.Redis,
    ) -> None:
        """Delete the hot cache for an NPC (e.g. on NPC deletion)."""
        try:
            await redis.delete(_memory_key(npc_id))
        except Exception as exc:
            logger.warning(
                "memory.hot.invalidate_error",
                extra={"npc_id": str(npc_id), "error": str(exc)},
            )

    # ── Cold tier (Postgres) ────────────────────────────────────────────────────

    async def get_cold_memory(
        self,
        npc_id: str | UUID,
        db: AsyncSession,
        limit: int = HOT_MEMORY_LIMIT,
        offset: int = 0,
    ) -> tuple[list[NPCMemoryEntry], int]:
        """
        Query the Postgres npc_interactions table.

        Returns (entries, total_count).
        Results are ordered oldest-first within the requested page.
        """
        npc_uuid = UUID(str(npc_id))

        count_result = await db.execute(
            select(func.count(NPCInteraction.id)).where(
                NPCInteraction.npc_id == npc_uuid
            )
        )
        total: int = count_result.scalar_one()

        result = await db.execute(
            select(NPCInteraction)
            .where(NPCInteraction.npc_id == npc_uuid)
            .order_by(NPCInteraction.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = result.scalars().all()
        entries = [_interaction_to_entry(row) for row in rows]

        logger.debug(
            "memory.cold.read",
            extra={"npc_id": str(npc_id), "count": len(entries), "total": total},
        )
        return entries, total

    # ── Context assembly: hot → cold fallback + backfill ───────────────────────

    async def get_memory_for_context(
        self,
        npc_id: str | UUID,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> list[NPCMemoryEntry]:
        """
        Return up to HOT_MEMORY_LIMIT interactions for LLM context assembly.

        1. Try Redis hot cache first.
        2. On miss, fall back to Postgres cold storage.
        3. Backfill Redis from Postgres so future reads are served hot.

        Always returns chronological (oldest-first) order.
        """
        # Step 1: Try hot cache
        entries = await self.get_hot_memory(npc_id, redis)
        if entries:
            return entries

        # Step 2: Cold fallback
        logger.info(
            "memory.cold.fallback",
            extra={"npc_id": str(npc_id)},
        )
        entries, _total = await self.get_cold_memory(npc_id, db, limit=HOT_MEMORY_LIMIT)

        if not entries:
            return []

        # Step 3: Backfill Redis — push in reverse order so LPUSH results in
        # newest-first list (index 0 = most recent)
        key = _memory_key(npc_id)
        try:
            async with redis.pipeline(transaction=True) as pipe:
                for entry in reversed(entries):
                    pipe.rpush(key, _entry_to_json(entry))
                pipe.ltrim(key, 0, HOT_MEMORY_LIMIT - 1)
                pipe.expire(key, HOT_MEMORY_TTL)
                await pipe.execute()
            logger.info(
                "memory.hot.backfill",
                extra={"npc_id": str(npc_id), "count": len(entries)},
            )
        except Exception as exc:
            logger.warning(
                "memory.hot.backfill_error",
                extra={"npc_id": str(npc_id), "error": str(exc)},
            )

        return entries

    # ── Postgres write ─────────────────────────────────────────────────────────

    async def write_interaction(
        self,
        db: AsyncSession,
        npc_id: UUID,
        session_id: UUID,
        player_id: UUID,
        player_message: str,
        npc_response: str,
        behaviour: NPCBehaviour,
        state_before: NPCEmotionalState,
        state_after: NPCEmotionalState,
        secret_leaked: str | None,
    ) -> NPCInteraction:
        """
        Persist one interaction to the Postgres cold store.

        flush() populates row.id without committing the outer transaction.
        Caller must commit after this returns.
        """
        row = NPCInteraction(
            npc_id=npc_id,
            session_id=session_id,
            player_id=player_id,
            player_message=player_message,
            npc_response=npc_response,
            behaviour=behaviour.value,
            state_before=state_before.model_dump(),
            state_after=state_after.model_dump(),
            secret_leaked=secret_leaked,
        )
        db.add(row)
        await db.flush()
        return row


# ── Module-level singleton ─────────────────────────────────────────────────────
memory_service = MemoryService()
