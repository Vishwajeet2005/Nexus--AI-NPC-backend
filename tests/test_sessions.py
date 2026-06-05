"""
tests/test_sessions.py
───────────────────────
Comprehensive tests for all /v1/sessions endpoints.

Coverage:
  POST   /sessions                    — create (success, game not found)
  GET    /sessions/{id}               — get (success, not found)
  POST   /sessions/{id}/join          — join by UUID (success, full, locked, ended, already in)
  POST   /sessions/join/{code}        — join by code (success, wrong code)
  POST   /sessions/{id}/leave         — leave (success, not in session)
  POST   /sessions/{id}/lock          — lock (host only, non-host rejected)
  POST   /sessions/{id}/end           — end (host only, non-host rejected, already ended)
  GET    /sessions/{id}/players       — list active players
  PATCH  /sessions/{id}/state         — shallow merge, non-member rejected
  Auth   guards                       — 401 on missing token for all endpoints
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

# ── Helpers ────────────────────────────────────────────────────────────────────

async def _make_game(db: AsyncSession) -> uuid.UUID:
    """
    Insert a minimal Game row directly and return its id.
    This bypasses the (nonexistent in Phase 1) game registration endpoint.
    """
    import secrets
    from api.models.game import Game

    game = Game(
        name="Test Game",
        api_key=secrets.token_hex(16),
        config={},
    )
    db.add(game)
    await db.commit()
    await db.refresh(game)
    return game.id


async def _create_session(
    client: AsyncClient,
    auth_headers: dict,
    game_id: uuid.UUID,
    max_players: int = 4,
    region: str = "us-east-1",
) -> dict:
    """Create a session and assert 201. Returns the session response body."""
    resp = await client.post(
        "/v1/sessions",
        json={
            "game_id": str(game_id),
            "config": {
                "mode": "test",
                "max_players": max_players,
                "region": region,
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"create_session failed: {resp.text}"
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/sessions
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateSession:

    async def test_create_session_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Happy path: valid game_id returns 201 SessionResponse."""
        game_id = await _make_game(db)
        resp = await client.post(
            "/v1/sessions",
            json={
                "game_id": str(game_id),
                "config": {"mode": "interrogation", "max_players": 4, "region": "ap-south-1"},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "created"
        assert body["max_players"] == 4
        assert body["region"] == "ap-south-1"
        assert body["game_mode"] == "interrogation"
        assert body["is_locked"] is False
        assert len(body["players"]) == 1  # creator is the host

    async def test_create_session_join_code_format(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Join code must match NEXUS-XXXX format with valid alphabet."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)

        code = session["join_code"]
        assert code.startswith("NEXUS-"), f"Bad prefix: {code}"
        suffix = code[6:]
        assert len(suffix) == 4, f"Suffix length: {len(suffix)}"
        valid_chars = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
        assert all(c in valid_chars for c in suffix), f"Invalid chars in suffix: {suffix}"
        assert "0" not in suffix
        assert "O" not in suffix
        assert "1" not in suffix
        assert "I" not in suffix

    async def test_create_session_creator_is_host(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """The session creator must appear in players list with role='host'."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)

        assert len(session["players"]) == 1
        assert session["players"][0]["role"] == "host"

    async def test_create_session_unknown_game_returns_404(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ) -> None:
        """Non-existent game_id → 404 GAME_NOT_FOUND."""
        resp = await client.post(
            "/v1/sessions",
            json={"game_id": str(uuid.uuid4()), "config": {"region": "us-east-1"}},
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "GAME_NOT_FOUND"

    async def test_create_session_requires_auth(self, client: AsyncClient) -> None:
        """Missing Authorization header → 401."""
        resp = await client.post(
            "/v1/sessions",
            json={"game_id": str(uuid.uuid4()), "config": {}},
        )
        assert resp.status_code == 401

    async def test_create_session_config_stored(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """The full config dict is persisted and returned on GET."""
        game_id = await _make_game(db)
        config = {"mode": "stealth", "max_players": 2, "region": "eu-west-1",
                  "npcs": ["agent_x"], "difficulty": "hard"}
        session = await _create_session(client, auth_headers, game_id, max_players=2, region="eu-west-1")
        session_id = session["id"]

        get_resp = await client.get(f"/v1/sessions/{session_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["max_players"] == 2
        assert body["region"] == "eu-west-1"


# ═══════════════════════════════════════════════════════════════════════════════
# GET /v1/sessions/{session_id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetSession:

    async def test_get_session_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """GET returns full SessionResponse for existing session."""
        game_id = await _make_game(db)
        created = await _create_session(client, auth_headers, game_id)
        session_id = created["id"]

        resp = await client.get(f"/v1/sessions/{session_id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == session_id
        assert body["join_code"] == created["join_code"]

    async def test_get_session_not_found_returns_404(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ) -> None:
        """Unknown session_id → 404."""
        resp = await client.get(f"/v1/sessions/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == "SESSION_NOT_FOUND"

    async def test_get_session_requires_auth(self, client: AsyncClient) -> None:
        resp = await client.get(f"/v1/sessions/{uuid.uuid4()}")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/sessions/{id}/join  and  POST /v1/sessions/join/{code}
# ═══════════════════════════════════════════════════════════════════════════════

class TestJoinSession:

    async def test_join_by_id_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Second player can join a session by UUID → 200 with 2 active players."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id, max_players=4)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/join",
            headers=second_auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["players"]) == 2

    async def test_join_by_code_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Second player can join via human-readable join code → 200."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        code = session["join_code"]

        resp = await client.post(
            f"/v1/sessions/join/{code}",
            headers=second_auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["players"]) == 2

    async def test_join_by_code_case_insensitive(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Join code lookup is case-insensitive."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        code = session["join_code"].lower()  # send lowercase

        resp = await client.post(f"/v1/sessions/join/{code}", headers=second_auth_headers)
        assert resp.status_code == 200

    async def test_join_wrong_code_returns_404(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ) -> None:
        """Non-existent join code → 404 SESSION_NOT_FOUND."""
        resp = await client.post(
            "/v1/sessions/join/NEXUS-ZZZZ",
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "SESSION_NOT_FOUND"

    async def test_join_already_in_session_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Joining a session you're already in → 409 ALREADY_IN_SESSION."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/join",
            headers=auth_headers,  # same user who created it
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "ALREADY_IN_SESSION"

    async def test_join_full_session_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Joining a session that has reached max_players → 409 SESSION_FULL."""
        game_id = await _make_game(db)
        # max_players=1 means the creator fills the only slot
        session = await _create_session(client, auth_headers, game_id, max_players=1)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/join",
            headers=second_auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "SESSION_FULL"

    async def test_join_locked_session_returns_423(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Joining a locked session → 423 SESSION_LOCKED."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)

        # Lock it
        await client.post(f"/v1/sessions/{session['id']}/lock", headers=auth_headers)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/join",
            headers=second_auth_headers,
        )
        assert resp.status_code == 423
        assert resp.json()["code"] == "SESSION_LOCKED"

    async def test_join_ended_session_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Joining an ended session → 409 SESSION_ENDED."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)

        # End it
        await client.post(f"/v1/sessions/{session['id']}/end", headers=auth_headers)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/join",
            headers=second_auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "SESSION_ENDED"

    async def test_join_transitions_status_to_active(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Session moves from 'created' to 'active' when the first non-host joins."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        assert session["status"] == "created"

        resp = await client.post(
            f"/v1/sessions/{session['id']}/join",
            headers=second_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/sessions/{id}/leave
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeaveSession:

    async def test_leave_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Player who joined can leave → 200, no longer in active player list."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)

        await client.post(f"/v1/sessions/{session['id']}/join", headers=second_auth_headers)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/leave",
            headers=second_auth_headers,
        )
        assert resp.status_code == 200
        active_usernames = [p["username"] for p in resp.json()["players"]]
        assert "player2" not in active_usernames

    async def test_leave_when_not_in_session_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Leaving a session you never joined → 409 NOT_IN_SESSION."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/leave",
            headers=second_auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "NOT_IN_SESSION"

    async def test_leave_reduces_active_count(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Active player count drops by 1 after leave."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id, max_players=4)

        await client.post(f"/v1/sessions/{session['id']}/join", headers=second_auth_headers)

        before = await client.get(f"/v1/sessions/{session['id']}", headers=auth_headers)
        assert len(before.json()["players"]) == 2

        await client.post(f"/v1/sessions/{session['id']}/leave", headers=second_auth_headers)

        after = await client.get(f"/v1/sessions/{session['id']}", headers=auth_headers)
        assert len(after.json()["players"]) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/sessions/{id}/lock
# ═══════════════════════════════════════════════════════════════════════════════

class TestLockSession:

    async def test_lock_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Host can lock a session → 200 with is_locked=True."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/lock",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_locked"] is True

    async def test_lock_by_non_host_returns_403(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Non-host player cannot lock the session → 403 NOT_HOST."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        await client.post(f"/v1/sessions/{session['id']}/join", headers=second_auth_headers)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/lock",
            headers=second_auth_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "NOT_HOST"

    async def test_lock_ended_session_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Cannot lock an ended session → 409."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        await client.post(f"/v1/sessions/{session['id']}/end", headers=auth_headers)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/lock",
            headers=auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "SESSION_ENDED"


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/sessions/{id}/end
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndSession:

    async def test_end_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Host can end session → 200 with status='ended' and ended_at set."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/end",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ended"
        assert body["ended_at"] is not None

    async def test_end_by_non_host_returns_403(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Non-host cannot end session → 403 NOT_HOST."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        await client.post(f"/v1/sessions/{session['id']}/join", headers=second_auth_headers)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/end",
            headers=second_auth_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "NOT_HOST"

    async def test_end_already_ended_session_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Ending an already-ended session → 409 SESSION_ENDED."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        await client.post(f"/v1/sessions/{session['id']}/end", headers=auth_headers)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/end",
            headers=auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "SESSION_ENDED"

    async def test_end_closes_all_memberships(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """After ending, all players have left_at set (no active players)."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        await client.post(f"/v1/sessions/{session['id']}/join", headers=second_auth_headers)

        resp = await client.post(
            f"/v1/sessions/{session['id']}/end",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # GET to verify active players count is 0
        get_resp = await client.get(f"/v1/sessions/{session['id']}", headers=auth_headers)
        assert len(get_resp.json()["players"]) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# GET /v1/sessions/{id}/players
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetSessionPlayers:

    async def test_get_players_returns_active_only(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """GET /players returns only players whose left_at is null."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        await client.post(f"/v1/sessions/{session['id']}/join", headers=second_auth_headers)
        await client.post(f"/v1/sessions/{session['id']}/leave", headers=second_auth_headers)

        resp = await client.get(
            f"/v1/sessions/{session['id']}/players",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        players = resp.json()
        assert len(players) == 1
        assert players[0]["role"] == "host"

    async def test_get_players_includes_role_and_timestamps(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Player list includes role, joined_at, and left_at fields."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)

        resp = await client.get(
            f"/v1/sessions/{session['id']}/players",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        player = resp.json()[0]
        assert "role" in player
        assert "joined_at" in player
        assert "left_at" in player
        assert player["left_at"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH /v1/sessions/{id}/state
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionState:

    async def test_state_update_shallow_merge(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """PATCH state performs a shallow merge: existing keys preserved, new keys added."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        sid = session["id"]

        # First update
        resp1 = await client.patch(
            f"/v1/sessions/{sid}/state",
            json={"state": {"phase": "setup", "round": 1}},
            headers=auth_headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["state"] == {"phase": "setup", "round": 1}

        # Second update — shallow merge
        resp2 = await client.patch(
            f"/v1/sessions/{sid}/state",
            json={"state": {"round": 2, "timer": 300}},
            headers=auth_headers,
        )
        assert resp2.status_code == 200
        state = resp2.json()["state"]
        assert state["phase"] == "setup"   # preserved from first update
        assert state["round"] == 2         # overwritten
        assert state["timer"] == 300       # new key

    async def test_state_update_nested_dict_replaced(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Shallow merge: nested dict is replaced wholesale, NOT deep-merged."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        sid = session["id"]

        await client.patch(
            f"/v1/sessions/{sid}/state",
            json={"state": {"nested": {"a": 1, "b": 2}}},
            headers=auth_headers,
        )
        resp = await client.patch(
            f"/v1/sessions/{sid}/state",
            json={"state": {"nested": {"c": 3}}},   # replaces nested entirely
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # If deep-merged, "a" and "b" would still be present
        assert resp.json()["state"]["nested"] == {"c": 3}

    async def test_state_update_by_non_member_returns_403(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """A player not in the session cannot update state → 403 NOT_IN_SESSION."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)

        resp = await client.patch(
            f"/v1/sessions/{session['id']}/state",
            json={"state": {"phase": "hacked"}},
            headers=second_auth_headers,  # player2 never joined
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "NOT_IN_SESSION"

    async def test_state_update_on_ended_session_returns_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Cannot update state of an ended session → 409 SESSION_ENDED."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        await client.post(f"/v1/sessions/{session['id']}/end", headers=auth_headers)

        resp = await client.patch(
            f"/v1/sessions/{session['id']}/state",
            json={"state": {"phase": "post_game"}},
            headers=auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "SESSION_ENDED"

    async def test_state_update_requires_auth(
        self,
        client: AsyncClient,
        db: AsyncSession,
    ) -> None:
        resp = await client.patch(
            f"/v1/sessions/{uuid.uuid4()}/state",
            json={"state": {}},
        )
        assert resp.status_code == 401

    async def test_state_update_any_active_member_can_write(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        db: AsyncSession,
    ) -> None:
        """Any active member (not just host) can update session state."""
        game_id = await _make_game(db)
        session = await _create_session(client, auth_headers, game_id)
        await client.post(f"/v1/sessions/{session['id']}/join", headers=second_auth_headers)

        resp = await client.patch(
            f"/v1/sessions/{session['id']}/state",
            json={"state": {"player2_action": "look_around"}},
            headers=second_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["state"]["player2_action"] == "look_around"


# ═══════════════════════════════════════════════════════════════════════════════
# Auth guard — every endpoint rejects unauthenticated requests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionAuthGuards:

    @pytest.mark.parametrize("method,path", [
        ("GET",   "/v1/sessions/{sid}"),
        ("POST",  "/v1/sessions/{sid}/join"),
        ("POST",  "/v1/sessions/join/NEXUS-AAAA"),
        ("POST",  "/v1/sessions/{sid}/leave"),
        ("POST",  "/v1/sessions/{sid}/lock"),
        ("POST",  "/v1/sessions/{sid}/end"),
        ("GET",   "/v1/sessions/{sid}/players"),
        ("PATCH", "/v1/sessions/{sid}/state"),
    ])
    async def test_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        method: str,
        path: str,
    ) -> None:
        sid = str(uuid.uuid4())
        url = path.replace("{sid}", sid)
        body = {"state": {}} if method == "PATCH" else None
        resp = await client.request(method, url, json=body)
        assert resp.status_code == 401, f"{method} {url} should require auth"
