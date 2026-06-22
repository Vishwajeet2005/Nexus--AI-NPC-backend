"""
nexus_py — Python SDK for the Nexus AI-native game backend.

Quick start:

    import asyncio
    from nexus_py import NexusClient

    async def main():
        async with NexusClient(host="localhost:8000") as nexus:
            await nexus.auth.login("dev", "password123")
            session = await nexus.sessions.create(game_id="your-game-id")
            npc = await nexus.npcs.create({...marcus_webb_data...})
            response = await nexus.npcs.interact(npc.id, "Where were you on the 14th?")
            print(response.npc_response)
            print(response.behaviour)

    asyncio.run(main())

See README.md for full documentation of every sub-client.
"""

from nexus_py.client import NexusClient
from nexus_py.exceptions import (
    AuthError,
    NexusError,
    NPCError,
    SessionError,
    TimeoutError,
)
from nexus_py.models import (
    InteractResponse,
    NexusEvent,
    NPCBehaviour,
    NPCEmotionalState,
    NPCMemoryEntry,
    NPCResponse,
    PaginatedMemory,
    PlayerResponse,
    SessionPlayerResponse,
    SessionResponse,
    TokenResponse,
)

__version__ = "0.1.0"

__all__ = [
    # Main entry point
    "NexusClient",
    # Exceptions
    "NexusError",
    "AuthError",
    "SessionError",
    "NPCError",
    "TimeoutError",
    # Models
    "PlayerResponse",
    "TokenResponse",
    "SessionResponse",
    "SessionPlayerResponse",
    "NPCResponse",
    "NPCBehaviour",
    "NPCEmotionalState",
    "InteractResponse",
    "NPCMemoryEntry",
    "PaginatedMemory",
    "NexusEvent",
]
