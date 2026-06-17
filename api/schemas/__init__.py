"""
api/schemas/__init__.py
───────────────────────
Re-exports every Pydantic schema so application code can do:

    from api.schemas import RegisterRequest, SessionResponse, ErrorResponse

without knowing which sub-module each schema lives in.
"""

from api.schemas.common import ErrorResponse, PaginatedResponse  # noqa: F401

from api.schemas.auth import (  # noqa: F401
    LoginRequest,
    LogoutRequest,
    PlayerResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPayload,
    TokenResponse,
)

from api.schemas.session import (  # noqa: F401
    SessionCreate,
    SessionListResponse,
    SessionPlayerResponse,
    SessionResponse,
    SessionStateUpdate,
)

from api.schemas.npc import (  # noqa: F401
    NPCMemoryScope,
    NPCBehaviour,
    NPCTell,
    NPCPersonality,
    NPCSecret,
    NPCEmotionalState,
    NPCStateDelta,
    NPCCreate,
    NPCResponse,
    InteractRequest,
    InteractResponse,
    NPCMemoryEntry,
    NPCMemoryResponse,
)

__all__ = [
    # common
    "ErrorResponse",
    "PaginatedResponse",
    # auth
    "RegisterRequest",
    "LoginRequest",
    "RefreshRequest",
    "LogoutRequest",
    "PlayerResponse",
    "TokenResponse",
    "TokenPayload",
    # session
    "SessionCreate",
    "SessionStateUpdate",
    "SessionResponse",
    "SessionListResponse",
    "SessionPlayerResponse",
    # npc
    "NPCMemoryScope",
    "NPCBehaviour",
    "NPCTell",
    "NPCPersonality",
    "NPCSecret",
    "NPCEmotionalState",
    "NPCStateDelta",
    "NPCCreate",
    "NPCResponse",
    "InteractRequest",
    "InteractResponse",
    "NPCMemoryEntry",
    "NPCMemoryResponse",
]
