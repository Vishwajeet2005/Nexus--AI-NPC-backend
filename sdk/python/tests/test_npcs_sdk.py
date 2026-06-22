"""
sdk/python/tests/test_npcs_sdk.py
────────────────────────────────────
Tests for nexus_py.npcs.NPCsClient and nexus_py.realtime.RealtimeClient.

Spec test cases (from NEXUS_PHASE3_MEGAPROMPT.md):
  - test_interact_returns_typed_response: InteractResponse with all fields
  - test_get_memory_pagination: limit/offset params work
  - test_on_event_fires: connect() + on("npc_state_changed") handler fires on interact

The WebSocket test uses a local `websockets.serve()` test server rather than
mocking the `websockets` library internals — this exercises the SDK's real
WebSocket client code (auth handshake, frame parsing, handler dispatch)
against an actual (if minimal) WebSocket server running on localhost.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import websockets
from pytest_httpx import HTTPXMock

from nexus_py import InteractResponse, NexusClient, NPCError, PaginatedMemory

pytestmark = pytest.mark.asyncio


async def _login(client: NexusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://test.nexus.local:8000/v1/auth/login",
        status_code=200,
        json={
            "access_token": "npc-test-token",
            "refresh_token": "npc-test-refresh",
            "token_type": "bearer",
            "expires_in": 900,
        },
    )
    await client.auth.login("alice", "SecurePass123!")


def _interact_payload(
    npc_response: str = "I was at The Anchor bar all evening.",
    behaviour: str = "deflecting",
    secret_leaked: str | None = None,
) -> dict:
    return {
        "npc_response": npc_response,
        "behaviour": behaviour,
        "emotional_state": {"stress": 0.35, "trust": 0.35, "suspicion": 0.45, "cooperation": 0.5},
        "state_delta": {"stress": 0.15, "trust": -0.05, "suspicion": 0.1, "cooperation": -0.05},
        "secret_leaked": secret_leaked,
        "interaction_id": "i-0001",
    }


class TestNPCsSDK:

    async def test_interact_returns_typed_response(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """interact() returns an InteractResponse with every field correctly typed."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/npcs/npc-0001/interact",
            status_code=200,
            json=_interact_payload(),
        )

        response = await client.npcs.interact(
            "npc-0001", "Where were you on the night of the 14th?"
        )

        assert isinstance(response, InteractResponse)
        assert response.npc_response == "I was at The Anchor bar all evening."
        assert response.behaviour.value == "deflecting"
        assert response.emotional_state.stress == 0.35
        assert response.state_delta.stress == 0.15
        assert response.secret_leaked is None
        assert response.interaction_id == "i-0001"

        # Verify the request body
        requests = httpx_mock.get_requests(
            url="http://test.nexus.local:8000/v1/npcs/npc-0001/interact"
        )
        body = json.loads(requests[0].content)
        assert body == {"player_message": "Where were you on the night of the 14th?"}

    async def test_interact_with_secret_leaked(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """interact() correctly types a non-null secret_leaked field."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/npcs/npc-0001/interact",
            status_code=200,
            json=_interact_payload(
                npc_response="...All right. I left at 10:15, not midnight.",
                behaviour="nervous",
                secret_leaked="alibi_weakness",
            ),
        )

        response = await client.npcs.interact("npc-0001", "We have CCTV footage.")
        assert response.secret_leaked == "alibi_weakness"
        assert response.behaviour.value == "nervous"

    async def test_interact_npc_not_found_raises_npc_error(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """interact() against an unknown NPC raises NPCError (404)."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/npcs/unknown-npc/interact",
            status_code=404,
            json={
                "error": "NPC not found.",
                "code": "NPC_NOT_FOUND",
                "request_id": "77777777-7777-7777-7777-777777777777",
            },
        )

        with pytest.raises(NPCError) as exc_info:
            await client.npcs.interact("unknown-npc", "Hello?")

        assert exc_info.value.code == "NPC_NOT_FOUND"

    async def test_get_memory_pagination(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """get_memory() correctly passes limit/offset as query params."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="GET",
            url="http://test.nexus.local:8000/v1/npcs/npc-0001/memory?limit=5&offset=10",
            status_code=200,
            json={
                "entries": [
                    {
                        "id": "i-0001",
                        "player_id": "p-0001",
                        "player_message": "Question?",
                        "npc_response": "Answer.",
                        "behaviour": "cooperative",
                        "state_before": {"stress": 0.2, "trust": 0.5, "suspicion": 0.3, "cooperation": 0.6},
                        "state_after": {"stress": 0.25, "trust": 0.5, "suspicion": 0.3, "cooperation": 0.6},
                        "secret_leaked": None,
                        "created_at": "2025-01-01T00:00:00",
                    }
                ],
                "total": 42,
                "limit": 5,
                "offset": 10,
            },
        )

        memory = await client.npcs.get_memory("npc-0001", limit=5, offset=10)

        assert isinstance(memory, PaginatedMemory)
        assert len(memory.entries) == 1
        assert memory.total == 42
        assert memory.limit == 5
        assert memory.offset == 10
        assert memory.entries[0].player_message == "Question?"

    async def test_get_memory_default_pagination(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """get_memory() with no args defaults to limit=20, offset=0."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="GET",
            url="http://test.nexus.local:8000/v1/npcs/npc-0001/memory?limit=20&offset=0",
            status_code=200,
            json={"entries": [], "total": 0, "limit": 20, "offset": 0},
        )

        memory = await client.npcs.get_memory("npc-0001")
        assert memory.limit == 20
        assert memory.offset == 0
        assert memory.entries == []

    async def test_create_npc_returns_typed_response(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """create() returns a fully typed NPCResponse without secrets exposed."""
        await _login(client, httpx_mock)

        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/npcs",
            status_code=201,
            json={
                "id": "npc-0001",
                "session_id": "s-0001",
                "name": "Marcus Webb",
                "personality": {"traits": ["calculated"], "motivation": "x", "fear": "y",
                                "background": "z", "speech_style": "terse",
                                "tells": {"cooperative": "a", "deflecting": "b", "nervous": "c", "hostile": "d"}},
                "current_emotional_state": {"stress": 0.2, "trust": 0.4, "suspicion": 0.35, "cooperation": 0.55},
                "current_behaviour": "cooperative",
                "memory_scope": "session",
                "created_at": "2025-01-01T00:00:00",
            },
        )

        npc = await client.npcs.create({
            "session_id": "s-0001",
            "name": "Marcus Webb",
            "personality": {},
            "secrets": [{"id": "x", "content": "y", "reveal_threshold": 0.5, "reveal_trigger": "z"}],
        })

        assert npc.id == "npc-0001"
        assert npc.name == "Marcus Webb"
        # Security: secrets must not be present on the typed model at all
        assert not hasattr(npc, "secrets")


class TestRealtimeSDK:

    async def test_on_event_fires(self) -> None:
        """
        connect() + on("npc_state_changed") handler fires when the server
        sends a matching event over the WebSocket.

        Uses a real local `websockets.serve()` test server that:
          1. Waits for the client's auth frame
          2. Replies with a "connected" frame
          3. Immediately pushes an "npc_state_changed" event
          4. Closes after sending
        """
        received_events: list[dict] = []
        server_ready = asyncio.Event()

        async def fake_server(websocket) -> None:
            # Step 1: receive the auth handshake
            auth_frame = json.loads(await websocket.recv())
            assert auth_frame["type"] == "auth"
            assert auth_frame["token"] == "ws-test-token"

            # Step 2: confirm connection
            await websocket.send(json.dumps({
                "type": "connected",
                "session_id": "s-0001",
                "player_id": "p-0001",
            }))

            # Step 3: push the event the test is waiting for
            await websocket.send(json.dumps({
                "type": "npc_state_changed",
                "payload": {
                    "npc_id": "npc-0001",
                    "npc_name": "Marcus Webb",
                    "behaviour": "deflecting",
                    "emotional_state": {"stress": 0.35, "trust": 0.35, "suspicion": 0.45, "cooperation": 0.5},
                    "secret_leaked": None,
                },
                "timestamp": "2025-01-01T00:00:00",
            }))

            # Give the client time to process before closing
            await asyncio.sleep(0.3)

        async with websockets.serve(fake_server, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]

            nexus = NexusClient(host=f"localhost:{port}")
            nexus._access_token = "ws-test-token"  # bypass login for this WS-only test

            async def on_npc_changed(event: dict) -> None:
                received_events.append(event)

            nexus.realtime.on("npc_state_changed", on_npc_changed)
            await nexus.realtime.connect("s-0001")

            # Give the background listener task time to receive and dispatch
            await asyncio.sleep(0.5)

            await nexus.realtime.disconnect()
            await nexus._http.aclose()

        assert len(received_events) == 1
        event = received_events[0]
        assert event["type"] == "npc_state_changed"
        assert event["payload"]["npc_name"] == "Marcus Webb"
        assert event["payload"]["behaviour"] == "deflecting"

    async def test_wildcard_handler_receives_all_events(self) -> None:
        """A handler registered for '*' fires for every event type, not just one."""
        received_types: list[str] = []

        async def fake_server(websocket) -> None:
            await websocket.recv()  # auth frame
            await websocket.send(json.dumps({"type": "connected", "session_id": "s-1", "player_id": "p-1"}))
            await websocket.send(json.dumps({"type": "player.joined", "payload": {}}))
            await websocket.send(json.dumps({"type": "session.state_updated", "payload": {}}))
            await asyncio.sleep(0.3)

        async with websockets.serve(fake_server, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            nexus = NexusClient(host=f"localhost:{port}")
            nexus._access_token = "ws-test-token"

            async def catch_all(event: dict) -> None:
                received_types.append(event["type"])

            nexus.realtime.on("*", catch_all)
            await nexus.realtime.connect("s-1")
            await asyncio.sleep(0.5)
            await nexus.realtime.disconnect()
            await nexus._http.aclose()

        assert "connected" in received_types
        assert "player.joined" in received_types
        assert "session.state_updated" in received_types

    async def test_connect_without_token_raises_auth_error(self) -> None:
        """connect() without a prior login/guest call raises AuthError immediately."""
        from nexus_py import AuthError

        nexus = NexusClient(host="localhost:9999")
        with pytest.raises(AuthError):
            await nexus.realtime.connect("s-0001")
        await nexus._http.aclose()

    async def test_ping_triggers_automatic_pong(self) -> None:
        """When the server sends a ping frame, the SDK automatically replies with pong."""
        pong_received = asyncio.Event()

        async def fake_server(websocket) -> None:
            await websocket.recv()  # auth frame
            await websocket.send(json.dumps({"type": "connected", "session_id": "s-1", "player_id": "p-1"}))
            await websocket.send(json.dumps({"type": "ping"}))

            # Wait for the client's pong reply
            reply_raw = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            reply = json.loads(reply_raw)
            if reply.get("type") == "pong":
                pong_received.set()

            await asyncio.sleep(0.2)

        async with websockets.serve(fake_server, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            nexus = NexusClient(host=f"localhost:{port}")
            nexus._access_token = "ws-test-token"

            await nexus.realtime.connect("s-1")
            await asyncio.sleep(0.5)
            await nexus.realtime.disconnect()
            await nexus._http.aclose()

        assert pong_received.is_set(), "Client did not auto-reply to server ping with pong"
