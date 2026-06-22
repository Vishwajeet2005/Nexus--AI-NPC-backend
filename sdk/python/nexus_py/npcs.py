"""
nexus_py.npcs
───────────────
NPCsClient — handles all NPC lifecycle and interaction endpoints.

Accessed via `nexus.npcs.*` on a NexusClient instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nexus_py.models import InteractResponse, NPCResponse, PaginatedMemory

if TYPE_CHECKING:
    from nexus_py.client import NexusClient


class NPCsClient:
    """
    NPC operations: create, get, interact, memory retrieval.

    `interact()` is the core gameplay loop method — it sends a player
    message to an NPC and returns the NPC's in-character response along
    with the updated emotional state and behaviour.
    """

    def __init__(self, client: "NexusClient") -> None:
        self._c = client

    async def create(self, npc_data: dict[str, Any]) -> NPCResponse:
        """
        Spawn a new NPC into a session.

        Args:
            npc_data: Full NPC definition matching the API's NPCCreate
                      schema — session_id, name, personality, secrets,
                      initial_emotional_state, confession_threshold,
                      memory_scope. See README for the Marcus Webb example.

        Returns:
            NPCResponse. The `secrets` field is never included — it is
            stored server-side only and never returned over the API.

        Raises:
            NexusError: validation error (422) or session not found (404).
        """
        data = await self._c._post("/npcs", json=npc_data)
        return NPCResponse(**data)

    async def get(self, npc_id: str) -> NPCResponse:
        """
        Retrieve the current state of an NPC.

        Raises:
            NPCError: NPC not found (404).
        """
        data = await self._c._get(f"/npcs/{npc_id}")
        return NPCResponse(**data)

    async def interact(
        self,
        npc_id: str,
        player_message: str,
    ) -> InteractResponse:
        """
        Send a player message to the NPC and receive an in-character response.

        This is always HTTP 200 — even if the server's internal LLM call
        times out, the server returns a graceful fallback response rather
        than an error. Check `response.state_delta` for all-zero values to
        detect a fallback occurred (the NPC's state did not change).

        Args:
            npc_id:         UUID of the NPC to interact with.
            player_message: The player's message text (1–2000 characters).

        Returns:
            InteractResponse with `npc_response`, `behaviour`,
            `emotional_state`, `state_delta`, and `secret_leaked` (if any
            secret was revealed and passed server-side validation).

        Raises:
            NPCError: NPC not found (404).
        """
        data = await self._c._post(
            f"/npcs/{npc_id}/interact",
            json={"player_message": player_message},
        )
        return InteractResponse(**data)

    async def get_memory(
        self,
        npc_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedMemory:
        """
        Retrieve paginated interaction history for an NPC.

        Always reads from cold storage (Postgres) — use the WebSocket
        channel for live state updates during an active session rather
        than polling this endpoint.

        Args:
            npc_id: UUID of the NPC.
            limit:  Max entries to return (1–100, default 20).
            offset: Pagination offset (default 0).

        Returns:
            PaginatedMemory with `entries` ordered chronologically
            (oldest first) plus `total`, `limit`, `offset` for pagination.

        Raises:
            NPCError: NPC not found (404).
        """
        data = await self._c._get(
            f"/npcs/{npc_id}/memory",
            params={"limit": limit, "offset": offset},
        )
        return PaginatedMemory(**data)

    async def list_in_session(self, session_id: str) -> list[NPCResponse]:
        """
        List all NPCs currently spawned in a session.

        Raises:
            NexusError: session not found (404).
        """
        data = await self._c._get(f"/npcs/session/{session_id}")
        return [NPCResponse(**n) for n in data]
