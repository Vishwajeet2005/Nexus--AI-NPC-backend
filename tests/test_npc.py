"""
tests/test_npc.py
──────────────────
Phase 2 NPC test suite covering all 12 test cases from the spec.

Mocking strategy:
  - LLM calls are intercepted via `patch("api.services.npc_service.get_llm_provider")`
    which replaces the factory with a function returning a mock provider.
  - The mock provider returns a pre-built `LLMResponse` so tests are deterministic
    and never make real HTTP calls.
  - For timeout tests, the mock provider's `complete()` coroutine raises
    `asyncio.TimeoutError` directly (since the timeout is handled inside
    the provider, not the service — `LLMResponse.timeout()` is what gets returned
    when the provider catches it; but in the service the provider is called
    and we test that the service handles `is_valid=False` gracefully).
  - fakeredis is used in-process — no real Redis needed.
  - Per-test DB rollback via SAVEPOINT (from conftest.py).

All tests use `pytest.mark.asyncio` (configured as auto-mode in pytest.ini).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.npc import NPC, NPCInteraction
from api.models.game import Game
from api.schemas.npc import (
    NPCBehaviour,
    NPCCreate,
    NPCEmotionalState,
    NPCMemoryScope,
    NPCPersonality,
    NPCSecret,
    NPCStateDelta,
    NPCTell,
)
from api.services.emotion_service import EmotionService
from api.services.llm.base import LLMResponse
from api.services.memory_service import HOT_MEMORY_LIMIT, _memory_key

pytestmark = pytest.mark.asyncio


# ── Test fixtures ──────────────────────────────────────────────────────────────

def _make_personality() -> NPCPersonality:
    return NPCPersonality(
        traits=["calculated", "defensive", "prideful"],
        motivation="Protect his brother",
        fear="Prison",
        background="Mid-level accountant for 15 years.",
        speech_style="Terse, precise, slightly condescending.",
        tells=NPCTell(
            cooperative="Leans back. Makes eye contact.",
            deflecting="Answers a question with a question.",
            nervous="Uses filler phrases like 'as I said'.",
            hostile="Goes monosyllabic. Crosses arms.",
        ),
    )


def _make_secrets() -> list[NPCSecret]:
    return [
        NPCSecret(
            id="alibi_weakness",
            content="Left The Anchor at 10:15 PM, not midnight.",
            reveal_threshold=0.65,
            reveal_trigger="Player presents CCTV evidence.",
            is_revealed=False,
        ),
        NPCSecret(
            id="brothers_involvement",
            content="Danny moved the money. Marcus covered it up.",
            reveal_threshold=0.85,
            reveal_trigger="Player accuses Danny directly.",
            is_revealed=False,
        ),
    ]


def _make_npc_create(session_id: uuid.UUID) -> NPCCreate:
    return NPCCreate(
        session_id=str(session_id),
        name="Marcus Webb",
        personality=_make_personality(),
        secrets=_make_secrets(),
        initial_emotional_state=NPCEmotionalState(
            stress=0.2, trust=0.4, suspicion=0.35, cooperation=0.55
        ),
        confession_threshold=0.85,
        memory_scope=NPCMemoryScope.session,
    )


def _llm_response(
    text: str = "I was at The Anchor bar all evening.",
    stress_delta: float = 0.05,
    trust_delta: float = -0.05,
    suspicion_delta: float = 0.1,
    cooperation_delta: float = -0.05,
    behaviour: NPCBehaviour = NPCBehaviour.deflecting,
    secret_leaked: str | None = None,
) -> LLMResponse:
    """Build a deterministic LLMResponse for mocking."""
    return LLMResponse(
        npc_response=text,
        state_delta=NPCStateDelta(
            stress=stress_delta,
            trust=trust_delta,
            suspicion=suspicion_delta,
            cooperation=cooperation_delta,
        ),
        behaviour=behaviour,
        secret_leaked=secret_leaked,
        timed_out=False,
        parse_error=False,
    )


def _mock_provider(response: LLMResponse):
    """Return a patch context that replaces get_llm_provider with a mock."""
    mock = MagicMock()
    mock.complete = AsyncMock(return_value=response)
    factory_mock = MagicMock(return_value=mock)
    return patch("api.services.npc_service.get_llm_provider", factory_mock)


async def _make_game(db: AsyncSession) -> uuid.UUID:
    import secrets as _secrets
    game = Game(name="Test Game", api_key=_secrets.token_hex(16), config={})
    db.add(game)
    await db.commit()
    await db.refresh(game)
    return game.id


async def _create_npc_via_api(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    session_id: uuid.UUID | None = None,
    llm_response: LLMResponse | None = None,
) -> tuple[dict, uuid.UUID]:
    """
    Helper: create a session, then spawn an NPC via POST /v1/npcs.
    Returns (npc_body_dict, session_id).
    """
    # Need a game for the session
    game_id = await _make_game(db)

    if session_id is None:
        sess_resp = await client.post(
            "/v1/sessions",
            json={
                "game_id": str(game_id),
                "config": {"region": "us-east-1", "max_players": 4},
            },
            headers=auth_headers,
        )
        assert sess_resp.status_code == 201, sess_resp.text
        session_id = uuid.UUID(sess_resp.json()["id"])

    npc_payload = _make_npc_create(session_id).model_dump()

    resp = await client.post("/v1/npcs", json=npc_payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json(), session_id


# ═══════════════════════════════════════════════════════════════════════════════
# test_create_npc
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateNPC:

    async def test_create_npc_returns_201(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession
    ) -> None:
        """POST /v1/npcs with valid NPCCreate body returns 201."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        assert npc_body["name"] == "Marcus Webb"
        assert "id" in npc_body
        assert npc_body["memory_scope"] == "session"

    async def test_create_npc_persisted_with_personality(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession
    ) -> None:
        """NPC persisted to DB with correct personality and secrets."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = uuid.UUID(npc_body["id"])

        result = await db.execute(select(NPC).where(NPC.id == npc_id))
        npc = result.scalar_one()

        assert npc.name == "Marcus Webb"
        assert npc.personality["traits"] == ["calculated", "defensive", "prideful"]
        assert len(npc.secrets) == 2
        assert npc.secrets[0]["id"] == "alibi_weakness"
        assert npc.secrets[1]["id"] == "brothers_involvement"

    async def test_create_npc_initial_state_stored(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession
    ) -> None:
        """initial_emotional_state is stored in current_state column."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = uuid.UUID(npc_body["id"])

        result = await db.execute(select(NPC).where(NPC.id == npc_id))
        npc = result.scalar_one()

        assert abs(npc.current_state["stress"] - 0.2) < 1e-9
        assert abs(npc.current_state["trust"] - 0.4) < 1e-9
        assert abs(npc.current_state["suspicion"] - 0.35) < 1e-9
        assert abs(npc.current_state["cooperation"] - 0.55) < 1e-9

    async def test_create_npc_requires_auth(self, client: AsyncClient) -> None:
        """POST /v1/npcs without auth → 401."""
        resp = await client.post(
            "/v1/npcs",
            json={"session_id": str(uuid.uuid4()), "name": "Test"},
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# test_get_npc
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetNPC:

    async def test_get_npc_returns_correct_structure(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession
    ) -> None:
        """GET /v1/npcs/{id} returns correct NPCResponse structure."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        resp = await client.get(f"/v1/npcs/{npc_id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()

        assert body["id"] == npc_id
        assert body["name"] == "Marcus Webb"
        assert "current_emotional_state" in body
        assert "current_behaviour" in body
        assert "personality" in body
        assert body["current_behaviour"] in [b.value for b in NPCBehaviour]

    async def test_get_npc_secrets_not_in_response(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession
    ) -> None:
        """
        SECURITY: secrets field is NOT present in NPCResponse.
        This is the most critical security test in the suite.
        """
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        resp = await client.get(f"/v1/npcs/{npc_id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()

        # The word "secrets" must not appear at the top level
        assert "secrets" not in body, \
            "SECURITY VIOLATION: secrets exposed in NPCResponse"
        # And the secret content must not appear anywhere in the serialised body
        body_str = json.dumps(body)
        assert "Left The Anchor" not in body_str, \
            "SECURITY VIOLATION: secret content leaked in response"
        assert "Danny moved" not in body_str, \
            "SECURITY VIOLATION: secret content leaked in response"

    async def test_get_npc_not_found_returns_404(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """GET /v1/npcs/{unknown_id} → 404."""
        resp = await client.get(f"/v1/npcs/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == "NPC_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════════
# test_interact_basic
# ═══════════════════════════════════════════════════════════════════════════════

class TestInteractBasic:

    async def test_interact_returns_200_with_response(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """POST /v1/npcs/{id}/interact returns 200 with non-empty npc_response."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        with _mock_provider(_llm_response(text="I was at the bar.")):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "Where were you on the night of the 14th?"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["npc_response"] == "I was at the bar."
        assert body["npc_response"] != ""
        assert "interaction_id" in body

    async def test_interact_emotional_state_in_bounds(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """Response emotional_state has all four floats in [0.0, 1.0]."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        with _mock_provider(_llm_response()):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "Tell me about your alibi."},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        es = resp.json()["emotional_state"]
        for field in ["stress", "trust", "suspicion", "cooperation"]:
            val = es[field]
            assert 0.0 <= val <= 1.0, f"{field}={val} out of bounds"

    async def test_interact_stored_in_db(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """Interaction is stored in npc_interactions table."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        with _mock_provider(_llm_response()):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "What did you do after 10 PM?"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        interaction_id = uuid.UUID(resp.json()["interaction_id"])

        # Verify row exists in DB
        result = await db.execute(
            select(NPCInteraction).where(NPCInteraction.id == interaction_id)
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.player_message == "What did you do after 10 PM?"
        assert row.npc_response == "I was at The Anchor bar all evening."

    async def test_interact_updates_npc_current_state(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """NPC current_state is updated in DB after interact."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = uuid.UUID(npc_body["id"])

        original_stress = 0.2  # initial

        with _mock_provider(_llm_response(stress_delta=0.15)):
            await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "Stop lying!"},
                headers=auth_headers,
            )

        # Reload from DB
        await db.refresh(await db.get(NPC, npc_id))
        result = await db.execute(select(NPC).where(NPC.id == npc_id))
        npc = result.scalar_one()
        new_stress = npc.current_state["stress"]
        assert new_stress > original_stress, \
            f"Stress should have increased: {original_stress} → {new_stress}"

    async def test_interact_requires_auth(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession
    ) -> None:
        """POST /v1/npcs/{id}/interact without auth → 401."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        resp = await client.post(
            f"/v1/npcs/{npc_body['id']}/interact",
            json={"player_message": "Hello?"},
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# test_interact_state_drift
# ═══════════════════════════════════════════════════════════════════════════════

class TestInteractStateDrift:

    async def test_stress_increases_across_aggressive_messages(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """
        Send 5 aggressive messages — verify stress increases each time and
        behaviour eventually transitions from cooperative to nervous or hostile.
        """
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        stress_values: list[float] = []
        behaviours: list[str] = []

        # Each aggressive message raises stress by 0.12 (net after trust drop)
        for i in range(5):
            with _mock_provider(_llm_response(
                text=f"You are lying! Response {i}",
                stress_delta=0.12,
                trust_delta=-0.08,
                suspicion_delta=0.05,
                cooperation_delta=-0.08,
                behaviour=NPCBehaviour.nervous if i >= 2 else NPCBehaviour.deflecting,
            )):
                resp = await client.post(
                    f"/v1/npcs/{npc_id}/interact",
                    json={"player_message": f"You're clearly hiding something! [{i}]"},
                    headers=auth_headers,
                )

            assert resp.status_code == 200, f"Interact {i} failed: {resp.text}"
            body = resp.json()
            stress_values.append(body["emotional_state"]["stress"])
            behaviours.append(body["behaviour"])

        # Stress must be monotonically increasing
        for i in range(1, len(stress_values)):
            assert stress_values[i] > stress_values[i - 1], \
                f"Stress did not increase at step {i}: {stress_values}"

        # By message 5, stress should be well above initial (0.2 + 5×0.12 = 0.8)
        final_stress = stress_values[-1]
        assert final_stress > 0.5, f"Expected stress > 0.5, got {final_stress}"

        # Behaviour must have left cooperative at some point
        assert any(b != "cooperative" for b in behaviours), \
            f"Behaviour never left cooperative: {behaviours}"

    async def test_cooperative_messages_lower_stress(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """Empathetic messages should lower stress and increase trust."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        with _mock_provider(_llm_response(
            stress_delta=-0.05,
            trust_delta=0.1,
            suspicion_delta=-0.05,
            cooperation_delta=0.1,
            behaviour=NPCBehaviour.cooperative,
        )):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "I understand this must be difficult for you."},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        new_stress = resp.json()["emotional_state"]["stress"]
        # Initial stress is 0.2; -0.05 delta → 0.15 (but clamped to 0.0 floor)
        assert new_stress <= 0.2, f"Cooperative message should reduce stress: {new_stress}"


# ═══════════════════════════════════════════════════════════════════════════════
# test_secret_not_leaked_below_threshold
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecretBelowThreshold:

    async def test_secret_not_leaked_when_stress_too_low(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """
        Stress = 0.3 (below alibi_weakness threshold 0.65).
        LLM claims secret_leaked = 'alibi_weakness'.
        Server must reject and return secret_leaked = None.
        """
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        # LLM tries to leak the secret but stress is only 0.3
        # (initial 0.2 + delta 0.1 = 0.3 < 0.65 threshold)
        with _mock_provider(_llm_response(
            text="Fine. I left a bit earlier. But it was well before midnight.",
            stress_delta=0.1,
            secret_leaked="alibi_weakness",  # LLM claims reveal
        )):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "The bar closed at 10 PM that night."},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        # Server validation must block the reveal
        assert body["secret_leaked"] is None, \
            f"Secret should NOT be leaked below threshold, got: {body['secret_leaked']}"

    async def test_secret_not_leaked_for_unknown_id(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """LLM returning an unknown secret ID must be rejected server-side."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        with _mock_provider(_llm_response(
            stress_delta=0.7,  # High stress — would pass threshold if ID was valid
            secret_leaked="non_existent_secret",
        )):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "I know everything!"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["secret_leaked"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# test_secret_leaked_above_threshold
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecretAboveThreshold:

    async def test_secret_revealed_when_stress_above_threshold(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """
        Manually set NPC stress to 0.7 (above alibi_weakness threshold 0.65).
        Send reveal trigger message.
        Verify secret_leaked = 'alibi_weakness' and is_revealed=True in DB.
        """
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = uuid.UUID(npc_body["id"])

        # Directly set stress above the 0.65 reveal threshold in DB
        result = await db.execute(select(NPC).where(NPC.id == npc_id))
        npc = result.scalar_one()
        npc.current_state = {
            "stress": 0.7,     # above alibi_weakness threshold (0.65)
            "trust": 0.3,
            "suspicion": 0.55,
            "cooperation": 0.4,
        }
        await db.commit()

        with _mock_provider(_llm_response(
            text="...All right. I left at 10:15. Not midnight. I lied about that.",
            stress_delta=0.05,
            behaviour=NPCBehaviour.nervous,
            secret_leaked="alibi_weakness",
        )):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "We have CCTV showing you left at 10:15 PM."},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["secret_leaked"] == "alibi_weakness", \
            f"Expected 'alibi_weakness', got: {body['secret_leaked']}"

        # Verify is_revealed=True persisted in DB
        await db.refresh(npc)
        revealed_secret = next(
            (s for s in npc.secrets if s["id"] == "alibi_weakness"), None
        )
        assert revealed_secret is not None
        assert revealed_secret["is_revealed"] is True, \
            "is_revealed should be True in DB after successful reveal"

    async def test_secret_already_revealed_not_leaked_again(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """Once a secret is revealed, subsequent LLM claims of the same ID return None."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = uuid.UUID(npc_body["id"])

        # Set stress high AND mark secret as already revealed
        result = await db.execute(select(NPC).where(NPC.id == npc_id))
        npc = result.scalar_one()
        npc.current_state = {"stress": 0.8, "trust": 0.3, "suspicion": 0.6, "cooperation": 0.3}
        npc.secrets = [
            {**s, "is_revealed": True} if s["id"] == "alibi_weakness" else s
            for s in npc.secrets
        ]
        await db.commit()

        with _mock_provider(_llm_response(secret_leaked="alibi_weakness")):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "Tell me again about leaving at 10:15."},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["secret_leaked"] is None, \
            "Already-revealed secret must not be leaked again"

    async def test_exact_threshold_boundary_reveals_secret(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """stress == reveal_threshold (0.65) must ALSO allow reveal (>= not >)."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = uuid.UUID(npc_body["id"])

        result = await db.execute(select(NPC).where(NPC.id == npc_id))
        npc = result.scalar_one()
        npc.current_state = {"stress": 0.65, "trust": 0.4, "suspicion": 0.4, "cooperation": 0.5}
        await db.commit()

        with _mock_provider(_llm_response(
            secret_leaked="alibi_weakness",
            stress_delta=0.0,  # no change — stays exactly at 0.65
        )):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "The bar closed at 10."},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["secret_leaked"] == "alibi_weakness", \
            "Secret should be revealed when stress == reveal_threshold (>= boundary)"


# ═══════════════════════════════════════════════════════════════════════════════
# test_llm_timeout_fallback
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMTimeoutFallback:

    async def test_llm_timeout_returns_200_not_500(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """
        LLM provider returns LLMResponse.timeout() (is_valid=False).
        Service must return HTTP 200 with fallback response — never 500.
        """
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        # Provider returns a timed-out LLMResponse
        timeout_response = LLMResponse.timeout()
        with _mock_provider(timeout_response):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "What do you know about the missing funds?"},
                headers=auth_headers,
            )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["npc_response"] != "", "Fallback response should be non-empty"

    async def test_llm_timeout_state_unchanged(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """
        On LLM timeout, NPC state must remain completely unchanged.
        No DB writes should occur.
        """
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = uuid.UUID(npc_body["id"])

        # Record state before
        result = await db.execute(select(NPC).where(NPC.id == npc_id))
        npc = result.scalar_one()
        state_before = dict(npc.current_state)

        # Count interactions before
        count_before_result = await db.execute(
            select(NPCInteraction).where(NPCInteraction.npc_id == npc_id)
        )
        count_before = len(count_before_result.scalars().all())

        timeout_response = LLMResponse.timeout()
        with _mock_provider(timeout_response):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "Trigger timeout."},
                headers=auth_headers,
            )

        assert resp.status_code == 200

        # Reload NPC and verify state UNCHANGED
        await db.refresh(npc)
        result2 = await db.execute(select(NPC).where(NPC.id == npc_id))
        npc2 = result2.scalar_one()
        assert npc2.current_state == state_before, \
            f"State should be unchanged after timeout: before={state_before}, after={npc2.current_state}"

        # No new interaction rows written
        count_after_result = await db.execute(
            select(NPCInteraction).where(NPCInteraction.npc_id == npc_id)
        )
        count_after = len(count_after_result.scalars().all())
        assert count_after == count_before, \
            f"No interaction rows should be written on timeout: {count_before} → {count_after}"

    async def test_llm_timeout_fallback_delta_is_zero(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """Fallback response carries zero state_delta."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        with _mock_provider(LLMResponse.timeout()):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "Timeout test."},
                headers=auth_headers,
            )

        body = resp.json()
        delta = body["state_delta"]
        assert delta["stress"] == 0.0
        assert delta["trust"] == 0.0
        assert delta["suspicion"] == 0.0
        assert delta["cooperation"] == 0.0

    async def test_llm_parse_error_also_falls_back(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """LLMResponse.error() (parse failure) also triggers the fallback path."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        with _mock_provider(LLMResponse.error(raw="definitely not json")):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "Parse error test."},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["state_delta"]["stress"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# test_memory_hot_cache
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryHotCache:

    async def test_redis_key_exists_after_interact(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """After one interaction, verify Redis key exists for npc_id."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        with _mock_provider(_llm_response()):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "First message."},
                headers=auth_headers,
            )
        assert resp.status_code == 200

        # Check Redis key
        key = _memory_key(npc_id)
        exists = await redis.exists(key)
        assert exists == 1, f"Redis key '{key}' should exist after interact"

    async def test_redis_list_has_one_entry_after_one_interact(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """Redis list contains exactly one entry after one interaction."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        with _mock_provider(_llm_response()):
            await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "Single message."},
                headers=auth_headers,
            )

        key = _memory_key(npc_id)
        length = await redis.llen(key)
        assert length == 1, f"Expected 1 entry in Redis, got {length}"

    async def test_redis_list_capped_at_hot_memory_limit(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """Redis list is trimmed to HOT_MEMORY_LIMIT even if more interactions occur."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        # Send HOT_MEMORY_LIMIT + 3 interactions
        for i in range(HOT_MEMORY_LIMIT + 3):
            with _mock_provider(_llm_response(text=f"Response {i}")):
                await client.post(
                    f"/v1/npcs/{npc_id}/interact",
                    json={"player_message": f"Message {i}"},
                    headers=auth_headers,
                )

        key = _memory_key(npc_id)
        length = await redis.llen(key)
        assert length == HOT_MEMORY_LIMIT, \
            f"Redis list should be capped at {HOT_MEMORY_LIMIT}, got {length}"

    async def test_redis_entry_has_correct_ttl(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """Redis key has a TTL set (24-hour expiry)."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        with _mock_provider(_llm_response()):
            await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "TTL test."},
                headers=auth_headers,
            )

        key = _memory_key(npc_id)
        ttl = await redis.ttl(key)
        assert ttl > 0, "Redis key should have a positive TTL"
        assert ttl <= 86400, f"TTL should be ≤ 86400s, got {ttl}"


# ═══════════════════════════════════════════════════════════════════════════════
# test_memory_pagination
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryPagination:

    async def test_memory_limit_respected(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """GET /v1/npcs/{id}/memory?limit=5&offset=0 returns at most 5 entries."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        # Create 8 interactions
        for i in range(8):
            with _mock_provider(_llm_response(text=f"Response {i}")):
                await client.post(
                    f"/v1/npcs/{npc_id}/interact",
                    json={"player_message": f"Question {i}"},
                    headers=auth_headers,
                )

        resp = await client.get(
            f"/v1/npcs/{npc_id}/memory?limit=5&offset=0",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["entries"]) == 5
        assert body["limit"] == 5
        assert body["offset"] == 0

    async def test_memory_total_reflects_full_count(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """total field reflects the full interaction count, not just the page."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        for i in range(7):
            with _mock_provider(_llm_response(text=f"R{i}")):
                await client.post(
                    f"/v1/npcs/{npc_id}/interact",
                    json={"player_message": f"Q{i}"},
                    headers=auth_headers,
                )

        resp = await client.get(
            f"/v1/npcs/{npc_id}/memory?limit=3&offset=0",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["entries"]) == 3
        assert body["total"] == 7, f"Expected total=7, got {body['total']}"

    async def test_memory_offset_pagination(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """offset parameter correctly skips earlier entries."""
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]

        messages = [f"Question {i}" for i in range(6)]
        for msg in messages:
            with _mock_provider(_llm_response()):
                await client.post(
                    f"/v1/npcs/{npc_id}/interact",
                    json={"player_message": msg},
                    headers=auth_headers,
                )

        # Page 1
        resp1 = await client.get(
            f"/v1/npcs/{npc_id}/memory?limit=3&offset=0",
            headers=auth_headers,
        )
        # Page 2
        resp2 = await client.get(
            f"/v1/npcs/{npc_id}/memory?limit=3&offset=3",
            headers=auth_headers,
        )

        page1_msgs = [e["player_message"] for e in resp1.json()["entries"]]
        page2_msgs = [e["player_message"] for e in resp2.json()["entries"]]

        # Pages must not overlap
        assert set(page1_msgs).isdisjoint(set(page2_msgs)), \
            "Pages overlap — offset not working correctly"
        assert len(page1_msgs) == 3
        assert len(page2_msgs) == 3

    async def test_memory_requires_auth(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession
    ) -> None:
        npc_body, _ = await _create_npc_via_api(client, auth_headers, db)
        resp = await client.get(f"/v1/npcs/{npc_body['id']}/memory")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# test_ws_npc_state_changed_event
# ═══════════════════════════════════════════════════════════════════════════════

class TestWSNPCStateChangedEvent:

    async def test_npc_state_changed_published_to_redis(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """
        After a successful interact, verify that a `npc_state_changed` event
        is published to the session's Redis pub/sub channel.

        We subscribe to the channel before triggering the interact, then
        check that a message arrives with the correct structure.
        """
        npc_body, session_id = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]
        channel = f"session:{session_id}"

        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)

        with _mock_provider(_llm_response(
            text="I have nothing more to say.",
            behaviour=NPCBehaviour.deflecting,
        )):
            resp = await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "What were you doing at 10 PM?"},
                headers=auth_headers,
            )

        assert resp.status_code == 200

        # Drain subscription confirmation frames and find the npc_state_changed message
        found: dict | None = None
        for _ in range(10):  # try up to 10 frames
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if msg and msg["type"] == "message":
                payload = json.loads(msg["data"])
                if payload.get("event") == "npc_state_changed":
                    found = payload
                    break

        await pubsub.unsubscribe(channel)
        await pubsub.aclose()

        assert found is not None, \
            f"No npc_state_changed event published to channel '{channel}'"

        # Verify event payload structure
        data = found["data"]
        assert data["npc_id"] == npc_id
        assert data["npc_name"] == "Marcus Webb"
        assert "behaviour" in data
        assert "emotional_state" in data
        assert "secret_leaked" in data
        assert found["session_id"] == str(session_id)

    async def test_npc_state_changed_not_published_on_timeout(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, redis
    ) -> None:
        """On LLM timeout/fallback, no npc_state_changed event is published."""
        npc_body, session_id = await _create_npc_via_api(client, auth_headers, db)
        npc_id = npc_body["id"]
        channel = f"session:{session_id}"

        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)

        with _mock_provider(LLMResponse.timeout()):
            await client.post(
                f"/v1/npcs/{npc_id}/interact",
                json={"player_message": "Trigger timeout."},
                headers=auth_headers,
            )

        # Check for npc_state_changed — should not appear
        npc_event_found = False
        for _ in range(5):
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=0.3
            )
            if msg and msg["type"] == "message":
                payload = json.loads(msg["data"])
                if payload.get("event") == "npc_state_changed":
                    npc_event_found = True
                    break

        await pubsub.unsubscribe(channel)
        await pubsub.aclose()

        assert not npc_event_found, \
            "npc_state_changed must NOT be published when LLM times out"


# ═══════════════════════════════════════════════════════════════════════════════
# test_load_marcus_webb
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadMarcusWebb:

    async def test_load_marcus_webb_returns_valid_npc_create(self) -> None:
        """load_npc_from_file('marcus_webb.json') returns a valid NPCCreate."""
        from api.routers.npcs import load_npc_from_file

        npc_create = load_npc_from_file("marcus_webb.json")
        assert isinstance(npc_create, NPCCreate)
        assert npc_create.name == "Marcus Webb"
        assert len(npc_create.secrets) == 2
        assert npc_create.secrets[0].id == "alibi_weakness"
        assert npc_create.secrets[1].id == "brothers_involvement"
        assert npc_create.secrets[0].reveal_threshold == 0.65
        assert npc_create.secrets[1].reveal_threshold == 0.85
        assert npc_create.initial_emotional_state.stress == 0.2
        assert npc_create.initial_emotional_state.trust == 0.4
        assert npc_create.confession_threshold == 0.85
        assert npc_create.memory_scope == NPCMemoryScope.session

    async def test_load_marcus_webb_personality_intact(self) -> None:
        """Marcus Webb's personality fields match the spec exactly."""
        from api.routers.npcs import load_npc_from_file

        npc_create = load_npc_from_file("marcus_webb.json")
        p = npc_create.personality
        assert "calculated" in p.traits
        assert "defensive" in p.traits
        assert "protect" in p.motivation.lower()
        assert p.tells.cooperative != ""
        assert p.tells.hostile != ""

    async def test_post_marcus_webb_creates_npc(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession
    ) -> None:
        """POST /v1/npcs with marcus_webb data creates NPC successfully."""
        from api.routers.npcs import load_npc_from_file

        game_id = await _make_game(db)
        sess_resp = await client.post(
            "/v1/sessions",
            json={"game_id": str(game_id), "config": {"region": "us-east-1"}},
            headers=auth_headers,
        )
        assert sess_resp.status_code == 201
        session_id = sess_resp.json()["id"]

        marcus = load_npc_from_file("marcus_webb.json")
        payload = {**marcus.model_dump(), "session_id": session_id}

        resp = await client.post("/v1/npcs", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Marcus Webb"
        assert "secrets" not in body  # security check

    async def test_seed_endpoint_creates_marcus_webb(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession
    ) -> None:
        """POST /v1/npcs/seed/{session_id} spawns Marcus Webb in one call."""
        game_id = await _make_game(db)
        sess_resp = await client.post(
            "/v1/sessions",
            json={"game_id": str(game_id), "config": {"region": "us-east-1"}},
            headers=auth_headers,
        )
        session_id = sess_resp.json()["id"]

        resp = await client.post(
            f"/v1/npcs/seed/{session_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Marcus Webb"
        assert body["session_id"] == session_id


# ═══════════════════════════════════════════════════════════════════════════════
# test_behaviour_classification (EmotionService unit tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBehaviourClassification:
    """
    Unit tests for EmotionService.classify_behaviour().
    These do not require DB, Redis, or HTTP — pure logic validation.
    """

    def setup_method(self):
        self.svc = EmotionService()

    async def test_stress_09_returns_confessing(self) -> None:
        """stress=0.9 → confessing"""
        state = NPCEmotionalState(stress=0.9, trust=0.5, suspicion=0.3, cooperation=0.5)
        assert self.svc.classify_behaviour(state) == NPCBehaviour.confessing

    async def test_stress_at_085_boundary_returns_confessing(self) -> None:
        """stress=0.85 (exact boundary) → confessing"""
        state = NPCEmotionalState(stress=0.85, trust=0.5, suspicion=0.3, cooperation=0.5)
        assert self.svc.classify_behaviour(state) == NPCBehaviour.confessing

    async def test_high_stress_low_trust_returns_hostile(self) -> None:
        """stress=0.75, trust=0.1 → hostile"""
        state = NPCEmotionalState(stress=0.75, trust=0.1, suspicion=0.3, cooperation=0.3)
        assert self.svc.classify_behaviour(state) == NPCBehaviour.hostile

    async def test_mid_stress_low_trust_returns_nervous(self) -> None:
        """stress=0.55, trust=0.35 → nervous"""
        state = NPCEmotionalState(stress=0.55, trust=0.35, suspicion=0.3, cooperation=0.4)
        assert self.svc.classify_behaviour(state) == NPCBehaviour.nervous

    async def test_high_suspicion_low_stress_returns_deflecting(self) -> None:
        """suspicion=0.6, stress=0.4 → deflecting"""
        state = NPCEmotionalState(stress=0.4, trust=0.5, suspicion=0.6, cooperation=0.5)
        assert self.svc.classify_behaviour(state) == NPCBehaviour.deflecting

    async def test_defaults_return_cooperative(self) -> None:
        """Default NPCEmotionalState → cooperative"""
        state = NPCEmotionalState()
        assert self.svc.classify_behaviour(state) == NPCBehaviour.cooperative

    async def test_confessing_beats_hostile_when_both_conditions_met(self) -> None:
        """stress=0.9 AND trust<0.2 — confessing wins (first-match priority)"""
        state = NPCEmotionalState(stress=0.9, trust=0.1, suspicion=0.3, cooperation=0.3)
        result = self.svc.classify_behaviour(state)
        assert result == NPCBehaviour.confessing, \
            f"confessing should win over hostile: got {result}"

    async def test_apply_delta_clamps_upper_bound(self) -> None:
        """stress=0.9 + delta=0.2 → clamped to 1.0"""
        state = NPCEmotionalState(stress=0.9, trust=0.5, suspicion=0.3, cooperation=0.6)
        delta = NPCStateDelta(stress=0.2)
        new_state = self.svc.apply_delta(state, delta)
        assert new_state.stress == 1.0

    async def test_apply_delta_clamps_lower_bound(self) -> None:
        """trust=0.1 + delta=-0.3 → clamped to 0.0"""
        state = NPCEmotionalState(stress=0.2, trust=0.1, suspicion=0.3, cooperation=0.6)
        delta = NPCStateDelta(trust=-0.3)
        new_state = self.svc.apply_delta(state, delta)
        assert new_state.trust == 0.0

    async def test_apply_delta_zero_leaves_state_unchanged(self) -> None:
        """Zero delta → state unchanged"""
        state = NPCEmotionalState(stress=0.3, trust=0.5, suspicion=0.4, cooperation=0.6)
        new_state = self.svc.apply_delta(state, NPCStateDelta())
        assert new_state.stress == state.stress
        assert new_state.trust == state.trust
        assert new_state.suspicion == state.suspicion
        assert new_state.cooperation == state.cooperation

    async def test_return_type_is_enum_not_string(self) -> None:
        """classify_behaviour returns NPCBehaviour enum, not a plain string."""
        state = NPCEmotionalState()
        result = self.svc.classify_behaviour(state)
        assert isinstance(result, NPCBehaviour), \
            f"Expected NPCBehaviour enum, got {type(result)}"
