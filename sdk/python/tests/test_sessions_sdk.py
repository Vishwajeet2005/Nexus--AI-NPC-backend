"""
sdk/python/tests/test_sessions_sdk.py
────────────────────────────────────────
Tests for nexus_py.sessions.SessionsClient.

Spec test cases (from NEXUS_PHASE3_MEGAPROMPT.md):
  - test_create_session: returns SessionResponse with join_code
  - test_join_by_code: join_by_code() joins the correct session
  - test_update_state: state dict merged correctly
  - test_session_not_found: get("nonexistent") raises NexusError
"""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from nexus_py import NexusClient, NexusError, SessionError, SessionResponse

pytestmark = pytest.mark.asyncio


async def _login(client: NexusClient, httpx_mock: HTTPXMock) -> None:
    """Helper: authenticate the client so the Authorization header is attached."""
    httpx_mock.add_response(
        method="POST",
        url="http://test.nexus.local:8000/v1/auth/login",
        status_code=200,
        json={
            "access_token": "session-test-token",
            "refresh_token": "session-test-refresh",
            "token_type": "bearer",
            "expires_in": 900,
        },
    )
    await client.auth.login("alice", "SecurePass123!")


def _session_payload(
    session_id: str = "s-0001",
    join_code: str = "NEXUS-AB23",
    status: str = "created",
    players: list[dict] | None = None,
) -> dict:
    return {
        "id": session_id,
        "game_id": "g-0001",
        "join_code": join_code,
        "status": status,
        "max_players": 4,
        "region": "us-east-1",
        "game_mode": "interrogation",
        "is_locked": False,
        "config": {"mode": "interrogation"},
        "state": {},
        "players": players or [],
        "created_at": "2025-01-01T00:00:00",
        "ended_at": None,
    }


class TestSessionsSDK:

    async def test_create_session(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """create() returns a SessionResponse with a generated join_code."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/sessions",
            status_code=201,
            json=_session_payload(join_code="NEXUS-7742"),
        )

        session = await client.sessions.create(
            game_id="g-0001",
            config={"mode": "interrogation", "max_players": 4, "region": "us-east-1"},
        )

        assert isinstance(session, SessionResponse)
        assert session.join_code == "NEXUS-7742"
        assert session.status == "created"
        assert session.max_players == 4

        # Verify the request body sent the correct payload
        requests = httpx_mock.get_requests(
            url="http://test.nexus.local:8000/v1/sessions"
        )
        assert len(requests) == 1
        import json
        body = json.loads(requests[0].content)
        assert body["game_id"] == "g-0001"
        assert body["config"]["mode"] == "interrogation"

    async def test_create_session_default_empty_config(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """create() with no config sends an empty dict, not null."""
        await _login(client, httpx_mock)
        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/sessions",
            status_code=201,
            json=_session_payload(),
        )

        await client.sessions.create(game_id="g-0001")

        requests = httpx_mock.get_requests(
            url="http://test.nexus.local:8000/v1/sessions"
        )
        import json
        body = json.loads(requests[0].content)
        assert body["config"] == {}

    async def test_join_by_code(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """join_by_code() hits the correct endpoint and joins the right session."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/sessions/join/NEXUS-7742",
            status_code=200,
            json=_session_payload(
                session_id="s-target",
                join_code="NEXUS-7742",
                status="active",
                players=[
                    {
                        "id": "sp-1", "player_id": "p-1", "username": "alice",
                        "role": "host", "joined_at": "2025-01-01T00:00:00", "left_at": None,
                    },
                    {
                        "id": "sp-2", "player_id": "p-2", "username": "bob",
                        "role": "player", "joined_at": "2025-01-01T00:05:00", "left_at": None,
                    },
                ],
            ),
        )

        session = await client.sessions.join_by_code("NEXUS-7742")

        assert isinstance(session, SessionResponse)
        assert session.id == "s-target"
        assert session.join_code == "NEXUS-7742"
        assert len(session.players) == 2
        assert session.players[1].username == "bob"

        # Verify it called the join-by-code endpoint, NOT join-by-id
        requests = httpx_mock.get_requests(
            url="http://test.nexus.local:8000/v1/sessions/join/NEXUS-7742"
        )
        assert len(requests) == 1

    async def test_join_by_code_session_full_raises_session_error(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """join_by_code() against a full session raises SessionError (409)."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/sessions/join/NEXUS-FULL",
            status_code=409,
            json={
                "error": "Session is full.",
                "code": "SESSION_FULL",
                "request_id": "44444444-4444-4444-4444-444444444444",
            },
        )

        with pytest.raises(SessionError) as exc_info:
            await client.sessions.join_by_code("NEXUS-FULL")

        assert exc_info.value.code == "SESSION_FULL"

    async def test_update_state(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """update_state() sends the delta and returns the merged state."""
        await _login(client, httpx_mock)

        merged_payload = _session_payload(session_id="s-0001")
        merged_payload["state"] = {"phase": "interrogation", "round": 2, "timer": 300}

        httpx_mock.add_response(
            method="PATCH",
            url="http://test.nexus.local:8000/v1/sessions/s-0001/state",
            status_code=200,
            json=merged_payload,
        )

        session = await client.sessions.update_state(
            "s-0001", {"round": 2, "timer": 300}
        )

        assert session.state == {"phase": "interrogation", "round": 2, "timer": 300}

        # Verify the request body wraps the delta in {"state": ...}
        requests = httpx_mock.get_requests(
            url="http://test.nexus.local:8000/v1/sessions/s-0001/state"
        )
        import json
        body = json.loads(requests[0].content)
        assert body == {"state": {"round": 2, "timer": 300}}

    async def test_session_not_found(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """get('nonexistent') raises NexusError (404 SESSION_NOT_FOUND)."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="GET",
            url="http://test.nexus.local:8000/v1/sessions/nonexistent",
            status_code=404,
            json={
                "error": "Session not found.",
                "code": "SESSION_NOT_FOUND",
                "request_id": "55555555-5555-5555-5555-555555555555",
            },
        )

        with pytest.raises(NexusError) as exc_info:
            await client.sessions.get("nonexistent")

        assert exc_info.value.code == "SESSION_NOT_FOUND"

    async def test_leave_returns_updated_session(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """leave() returns the session with the player removed from active list."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/sessions/s-0001/leave",
            status_code=200,
            json=_session_payload(session_id="s-0001", players=[]),
        )

        session = await client.sessions.leave("s-0001")
        assert session.players == []

    async def test_lock_requires_host_raises_on_non_host(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """lock() by a non-host raises NexusError (403 NOT_HOST)."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/sessions/s-0001/lock",
            status_code=403,
            json={
                "error": "Only the session host may perform this action.",
                "code": "NOT_HOST",
                "request_id": "66666666-6666-6666-6666-666666666666",
            },
        )

        with pytest.raises(NexusError) as exc_info:
            await client.sessions.lock("s-0001")

        assert exc_info.value.code == "NOT_HOST"

    async def test_end_returns_ended_session(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """end() returns a SessionResponse with status='ended'."""
        await _login(client, httpx_mock)

        ended_payload = _session_payload(session_id="s-0001", status="ended")
        ended_payload["ended_at"] = "2025-01-01T01:00:00"

        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/sessions/s-0001/end",
            status_code=200,
            json=ended_payload,
        )

        session = await client.sessions.end("s-0001")
        assert session.status == "ended"
        assert session.ended_at is not None
