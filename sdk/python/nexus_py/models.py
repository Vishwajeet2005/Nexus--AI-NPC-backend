"""
nexus_py.models
─────────────────
Pydantic v2 response models mirrored from `api/schemas/`.

These are intentionally standalone — the SDK does not import from the
`api` package. SDK consumers get fully typed responses (autocomplete,
validation, IDE support) without needing the server source tree installed.

Kept in sync manually with:
    api/schemas/auth.py     → PlayerResponse, TokenResponse
    api/schemas/session.py  → SessionResponse, SessionPlayerResponse
    api/schemas/npc.py      → NPCResponse, NPCEmotionalState, NPCBehaviour,
                               InteractResponse, NPCMemoryEntry, PaginatedMemory
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Auth models ─────────────────────────────────────────────────────────────────

class PlayerResponse(BaseModel):
    """Public player identity returned by register/guest and embedded in sessions."""

    model_config = ConfigDict(frozen=True)

    id: str
    username: str
    email: str
    is_guest: bool


class TokenResponse(BaseModel):
    """JWT token pair returned by login/refresh/guest."""

    model_config = ConfigDict(frozen=True)

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ── Session models ─────────────────────────────────────────────────────────────

class SessionPlayerResponse(BaseModel):
    """A player as they appear within a session's player list."""

    model_config = ConfigDict(frozen=True)

    id: str
    player_id: str
    username: str
    role: str
    joined_at: datetime
    left_at: Optional[datetime] = None


class SessionResponse(BaseModel):
    """Full session representation returned by session endpoints."""

    model_config = ConfigDict(frozen=True)

    id: str
    game_id: Optional[str] = None
    join_code: str
    status: str
    max_players: int
    region: str
    game_mode: Optional[str] = None
    is_locked: bool = False
    config: Optional[dict[str, Any]] = None
    state: Optional[dict[str, Any]] = None
    players: list[SessionPlayerResponse] = Field(default_factory=list)
    created_at: datetime
    ended_at: Optional[datetime] = None


# ── NPC models ─────────────────────────────────────────────────────────────────

class NPCBehaviour(str, Enum):
    """NPC behaviour states derived from emotional state."""

    cooperative = "cooperative"
    deflecting = "deflecting"
    nervous = "nervous"
    hostile = "hostile"
    confessing = "confessing"


class NPCEmotionalState(BaseModel):
    """An NPC's emotional state — four bounded floats in [0.0, 1.0]."""

    model_config = ConfigDict(frozen=True)

    stress: float = 0.2
    trust: float = 0.5
    suspicion: float = 0.3
    cooperation: float = 0.6


class NPCResponse(BaseModel):
    """Public NPC representation. Secrets are never included."""

    model_config = ConfigDict(frozen=True)

    id: str
    session_id: str
    name: str
    personality: dict[str, Any]
    current_emotional_state: NPCEmotionalState
    current_behaviour: NPCBehaviour
    memory_scope: str
    created_at: str


class InteractResponse(BaseModel):
    """Response from POST /npcs/{id}/interact."""

    model_config = ConfigDict(frozen=True)

    npc_response: str
    behaviour: NPCBehaviour
    emotional_state: NPCEmotionalState
    state_delta: NPCEmotionalState
    secret_leaked: Optional[str] = None
    interaction_id: str


class NPCMemoryEntry(BaseModel):
    """A single interaction record from GET /npcs/{id}/memory."""

    model_config = ConfigDict(frozen=True)

    id: str
    player_id: str
    player_message: str
    npc_response: str
    behaviour: NPCBehaviour
    state_before: NPCEmotionalState
    state_after: NPCEmotionalState
    secret_leaked: Optional[str] = None
    created_at: str


class PaginatedMemory(BaseModel):
    """Paginated response wrapper for GET /npcs/{id}/memory."""

    model_config = ConfigDict(frozen=True)

    entries: list[NPCMemoryEntry]
    total: int
    limit: int
    offset: int


# ── Real-time event model ──────────────────────────────────────────────────────

class NexusEvent(BaseModel):
    """
    A real-time event received over the WebSocket connection.

    Wire format:
        { "type": "npc_state_changed", "payload": {...}, "timestamp": "iso8601" }
    or for session/player events published via realtime_service:
        { "event": "player.joined", "session_id": "...", "data": {...}, "ts": ... }

    The SDK normalises both shapes — `type`/`payload` is used for WS-native
    frames (connected, ping, npc_state_changed); `event`/`data` is used for
    events relayed from the Redis pub/sub channel. `RealtimeClient._listen`
    extracts whichever key is present so handlers always see a consistent
    `NexusEvent.type` / `NexusEvent.payload`.
    """

    model_config = ConfigDict(extra="allow")

    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None
