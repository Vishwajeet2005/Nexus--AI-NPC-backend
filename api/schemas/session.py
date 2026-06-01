"""
api/schemas/session.py
──────────────────────
Pydantic v2 schemas for all session endpoints.

Endpoint → schema mapping:
  POST   /v1/sessions                      → SessionCreate       → SessionResponse (201)
  GET    /v1/sessions/{id}                 → —                   → SessionResponse (200)
  POST   /v1/sessions/{id}/join            → —                   → SessionResponse (200)
  POST   /v1/sessions/join/{join_code}     → —                   → SessionResponse (200)
  POST   /v1/sessions/{id}/leave           → —                   → SessionResponse (200)
  POST   /v1/sessions/{id}/lock            → —                   → SessionResponse (200)
  POST   /v1/sessions/{id}/end             → —                   → SessionResponse (200)
  GET    /v1/sessions/{id}/players         → —                   → list[SessionPlayerResponse]
  PATCH  /v1/sessions/{id}/state           → SessionStateUpdate  → SessionResponse (200)

`SessionPlayerResponse` is a trimmed player view for the session context —
it includes join metadata but not sensitive player fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Supporting sub-schemas ─────────────────────────────────────────────────────

class SessionPlayerResponse(BaseModel):
    """
    A player as they appear within a session's player list.

    Built from a joined query across `session_players` + `players`.
    `left_at` is None for players currently in the session.
    """

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID = Field(..., description="SessionPlayer row UUID.")
    player_id: UUID = Field(..., description="The player's own UUID.")
    username: str = Field(..., description="Player's display name.")
    role: str = Field(..., description="Player's role in this session: 'player' | 'host'.")
    joined_at: datetime = Field(..., description="When the player joined the session.")
    left_at: datetime | None = Field(
        default=None,
        description="When the player left. None = still in session.",
    )


# ── Request schemas ────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    """
    POST /v1/sessions

    Spec request shape:
    {
      "game_id": "uuid",
      "config": {
        "mode":        "interrogation",
        "max_players": 4,
        "region":      "ap-south-1",
        "npcs":        ["marcus_webb"],
        "difficulty":  "adaptive"
      }
    }

    The `config` dict is forwarded to the session's JSONB `config` column
    as-is. Well-known keys are also promoted to top-level columns by the
    service layer (max_players, region, game_mode).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    game_id: UUID = Field(
        ...,
        description="UUID of the registered Game this session belongs to.",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Game-specific session configuration. "
            "Well-known keys: mode, max_players, region, npcs, difficulty."
        ),
        examples=[
            {
                "mode": "interrogation",
                "max_players": 4,
                "region": "ap-south-1",
                "npcs": ["marcus_webb"],
                "difficulty": "adaptive",
            }
        ],
    )

    @field_validator("config")
    @classmethod
    def validate_config_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate well-known config keys when present."""
        if "max_players" in v:
            mp = v["max_players"]
            if not isinstance(mp, int) or not (1 <= mp <= 100):
                raise ValueError("config.max_players must be an integer between 1 and 100")
        if "region" in v and not isinstance(v["region"], str):
            raise ValueError("config.region must be a string")
        return v


class SessionStateUpdate(BaseModel):
    """
    PATCH /v1/sessions/{id}/state

    Spec behaviour: shallow merge `{ **current_state, **provided_delta }`.
    The `state` value is arbitrary game state — no fixed schema.
    """

    state: dict[str, Any] = Field(
        ...,
        description="Partial game state delta. Shallow-merged into the session's existing state.",
        examples=[{"phase": "interrogation", "round": 2, "timer_seconds": 300}],
    )


# ── Response schemas ───────────────────────────────────────────────────────────

class SessionResponse(BaseModel):
    """
    Full session representation returned by most session endpoints.

    Spec response shape (POST /v1/sessions):
    {
      "id":          "uuid",
      "join_code":   "NEXUS-7742",
      "status":      "created",
      "max_players": 4,
      "region":      "ap-south-1",
      "game_mode":   "interrogation",
      "players":     [],
      "created_at":  "iso8601"
    }

    Additional fields (game_id, is_locked, config, state, ended_at) are
    included for GET /sessions/{id} to give clients full visibility.
    """

    model_config = ConfigDict(
        from_attributes=True,
        frozen=True,
        # Serialise datetime as ISO 8601 strings automatically
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    id: UUID = Field(..., description="Stable session UUID.")
    game_id: UUID | None = Field(None, description="The game this session belongs to.")
    join_code: str = Field(
        ...,
        description="Human-typeable join code in the format 'NEXUS-XXXX'.",
        examples=["NEXUS-7742"],
    )
    status: str = Field(
        ...,
        description="Lifecycle state: created | active | ended.",
        examples=["created", "active", "ended"],
    )
    max_players: int = Field(..., ge=1, description="Hard cap on concurrent players.")
    region: str = Field(..., description="Deployment region tag.", examples=["ap-south-1"])
    game_mode: str | None = Field(
        default=None,
        description="Game-defined mode string.",
        examples=["interrogation"],
    )
    is_locked: bool = Field(..., description="True when no new players may join.")
    config: dict[str, Any] | None = Field(
        default=None,
        description="Immutable configuration set at creation time.",
    )
    state: dict[str, Any] | None = Field(
        default=None,
        description="Live mutable game state.",
    )
    players: list[SessionPlayerResponse] = Field(
        default_factory=list,
        description="Players currently in the session (left_at is None).",
    )
    created_at: datetime = Field(..., description="ISO 8601 creation timestamp.")
    ended_at: datetime | None = Field(
        default=None,
        description="ISO 8601 end timestamp. None while session is live.",
    )


class SessionListResponse(BaseModel):
    """
    Lightweight session summary for list views.
    Omits heavy JSONB fields (config, state) to reduce payload size.
    """

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    join_code: str
    status: str
    max_players: int
    region: str
    game_mode: str | None = None
    is_locked: bool
    player_count: int = Field(
        ...,
        ge=0,
        description="Number of players currently in the session.",
    )
    created_at: datetime
