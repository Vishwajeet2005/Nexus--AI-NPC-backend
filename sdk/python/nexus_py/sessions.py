"""
nexus_py.sessions
────────────────────
SessionsClient — handles all session lifecycle endpoints.

Accessed via `nexus.sessions.*` on a NexusClient instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nexus_py.models import PlayerResponse, SessionResponse

if TYPE_CHECKING:
    from nexus_py.client import NexusClient


class SessionsClient:
    """
    Session lifecycle operations: create, join, leave, lock, end, state.

    All methods that return session data return a fully-typed
    `SessionResponse` — no raw dicts ever reach the caller.
    """

    def __init__(self, client: "NexusClient") -> None:
        self._c = client

    async def create(
        self,
        game_id: str,
        config: dict[str, Any] | None = None,
    ) -> SessionResponse:
        """
        Create a new game session.

        Args:
            game_id: UUID of the registered game this session belongs to.
            config:  Game-specific session configuration (mode, max_players,
                     region, npcs, difficulty, etc).

        Returns:
            SessionResponse with a freshly generated `join_code` (format:
            "NEXUS-XXXX") and the creator registered as host.
        """
        data = await self._c._post(
            "/sessions",
            json={"game_id": game_id, "config": config or {}},
        )
        return SessionResponse(**data)

    async def get(self, session_id: str) -> SessionResponse:
        """
        Retrieve full session details by UUID.

        Raises:
            NexusError: session not found (404).
        """
        data = await self._c._get(f"/sessions/{session_id}")
        return SessionResponse(**data)

    async def join(self, session_id: str) -> SessionResponse:
        """
        Join a session by its UUID.

        Raises:
            SessionError: session full, already a member, or session ended (409).
            AuthError:    session is locked (423).
        """
        data = await self._c._post(f"/sessions/{session_id}/join")
        return SessionResponse(**data)

    async def join_by_code(self, join_code: str) -> SessionResponse:
        """
        Join a session using its human-readable join code (e.g. "NEXUS-AB23").

        The join code is case-insensitive.

        Raises:
            NexusError:   no session found with that code (404).
            SessionError: session full, already a member, or session ended (409).
            AuthError:    session is locked (423).
        """
        data = await self._c._post(f"/sessions/join/{join_code}")
        return SessionResponse(**data)

    async def leave(self, session_id: str) -> SessionResponse:
        """
        Leave a session you are currently a member of.

        Raises:
            SessionError: not currently a member of this session (409).
        """
        data = await self._c._post(f"/sessions/{session_id}/leave")
        return SessionResponse(**data)

    async def lock(self, session_id: str) -> SessionResponse:
        """
        Lock a session to prevent new players from joining.

        Only the session host may call this.

        Raises:
            NexusError: caller is not the host (403).
        """
        data = await self._c._post(f"/sessions/{session_id}/lock")
        return SessionResponse(**data)

    async def end(self, session_id: str) -> SessionResponse:
        """
        End a session permanently. Only the session host may call this.

        All active player memberships are closed. The session becomes
        immutable after this call.

        Raises:
            NexusError: caller is not the host (403).
        """
        data = await self._c._post(f"/sessions/{session_id}/end")
        return SessionResponse(**data)

    async def update_state(
        self,
        session_id: str,
        state: dict[str, Any],
    ) -> SessionResponse:
        """
        Shallow-merge `state` into the session's existing game state.

        `{ **current_state, **state }` — top-level keys in `state` overwrite
        existing keys; nested dicts are replaced wholesale, not deep-merged.

        Raises:
            SessionError: session has already ended (409).
        """
        data = await self._c._patch(
            f"/sessions/{session_id}/state",
            json={"state": state},
        )
        return SessionResponse(**data)

    async def list_players(self, session_id: str) -> list[PlayerResponse]:
        """
        List currently active players in a session.

        Note: the underlying API endpoint returns SessionPlayerResponse
        objects (which include role/joined_at/left_at), but this SDK method
        projects them down to the simpler PlayerResponse shape per the
        spec's documented return type. Use `.get(session_id).players` for
        the full membership detail including role and join timestamps.
        """
        data = await self._c._get(f"/sessions/{session_id}/players")
        return [
            PlayerResponse(
                id=p["player_id"],
                username=p["username"],
                email="",  # not present on SessionPlayerResponse — see docstring
                is_guest=False,
            )
            for p in data
        ]
