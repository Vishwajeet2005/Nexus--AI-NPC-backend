"""
tests/conftest.py
──────────────────
Test infrastructure for the Nexus async test suite.

Database strategy — nested transactions (SAVEPOINT):
  One real transaction wraps the entire test. Within it a SAVEPOINT is
  established before each test function, then rolled back after — so no
  test data ever touches the `nexus_test` disk. The outer transaction is
  also rolled back at the end of the session. The schema (tables) is
  created once at session start via `Base.metadata.create_all`.

Redis strategy — fakeredis:
  `fakeredis.aioredis` provides an in-memory Redis implementation that
  speaks the same async API as `redis.asyncio`. No real Redis instance is
  needed for tests. Each test gets a fresh server instance to prevent
  state bleed between tests.

AsyncClient:
  Uses `httpx.AsyncClient` with `transport=ASGITransport(app=app)` to
  drive the full ASGI stack in-process — middleware, exception handlers,
  and routers all run — without binding a real TCP port.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# fakeredis must be installed: pip install fakeredis
try:
    import fakeredis.aioredis as fakeredis_async  # type: ignore[import]
except ImportError:
    fakeredis_async = None  # tests will skip if not installed

from api.main import app
from api.models import Base
import api.dependencies as _deps

# ── Test database URL ──────────────────────────────────────────────────────────
# Uses a dedicated `nexus_test` database so tests never touch dev data.
# Override via environment variable if needed.
import os

TEST_DATABASE_URL: str = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_test",
)

# ── pytest-asyncio configuration ──────────────────────────────────────────────
# "auto" mode: every async test/fixture is treated as asyncio without
# needing an explicit @pytest.mark.asyncio on each one.

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "asyncio: mark a test as async",
    )


# ── Session-scoped engine (created once for the entire test run) ───────────────

@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Create an async engine pointing at `nexus_test`.
    Build all tables once, then drop them after the session.
    """
    _engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        # NullPool: each `connect()` is a fresh TCP connection.
        # Required when the same engine is shared across tests that use
        # SAVEPOINT/ROLLBACK — pooled connections remember transaction state.
        pool_pre_ping=True,
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield _engine

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await _engine.dispose()


# ── Function-scoped DB session using nested SAVEPOINT rollback ─────────────────

@pytest_asyncio.fixture
async def db(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a per-test AsyncSession wrapped in a SAVEPOINT.

    After the test completes (pass or fail) the SAVEPOINT is rolled back,
    leaving the database in a clean state for the next test. The approach:

      1. Begin a connection-level transaction (`conn.begin()`).
      2. Start a SAVEPOINT via `conn.begin_nested()`.
      3. Bind a session to the SAVEPOINT.
      4. The session's commit() releases the SAVEPOINT and creates a new one
         (SQLAlchemy does this automatically with expire_on_commit=False).
      5. After the test, roll back to the outer transaction start.

    This means ORM `commit()` calls in service code DO execute and the
    session sees the committed data within the same test, but nothing
    persists to the actual database.
    """
    async with engine.connect() as conn:
        # Outer real transaction
        await conn.begin()
        # SAVEPOINT — service layer commit()s will "commit" to this savepoint
        await conn.begin_nested()

        session_factory = async_sessionmaker(
            bind=conn,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

        async with session_factory() as session:
            yield session

        # Roll back everything the test wrote
        await conn.rollback()


# ── Per-test fake Redis ────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def redis() -> AsyncGenerator:
    """
    Yield a fresh in-memory fakeredis instance for each test.
    No real Redis connection is required.
    """
    if fakeredis_async is None:
        pytest.skip("fakeredis not installed — run: pip install fakeredis")

    server = fakeredis_async.FakeRedis()
    yield server
    await server.aclose()


# ── AsyncClient wired to the ASGI app ─────────────────────────────────────────

@pytest_asyncio.fixture
async def client(
    db: AsyncSession,
    redis,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Yield an `httpx.AsyncClient` that drives the full ASGI stack.

    The `get_db` and `get_redis` FastAPI dependencies are overridden to
    return the per-test session and Redis instance respectively, so every
    HTTP call inside a test shares the same rolled-back transaction.
    """

    # Override get_db to yield the test session
    async def _override_get_db():
        yield db

    # Override get_redis to return the fake Redis
    async def _override_get_redis():
        return redis

    app.dependency_overrides[_deps.get_db] = _override_get_db
    app.dependency_overrides[_deps.get_redis] = _override_get_redis

    # Also patch the module-level singletons used by the WebSocket handler
    with patch.object(_deps, "_redis_pool", redis):
        with patch.object(_deps, "_async_session_factory",
                          async_sessionmaker(
                              bind=db.get_bind(),
                              class_=AsyncSession,
                              expire_on_commit=False,
                          )):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                yield ac

    app.dependency_overrides.clear()


# ── Auth helper fixtures ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Register a player and return the response JSON."""
    resp = await client.post("/v1/auth/register", json={
        "username": "testplayer",
        "email": "test@example.com",
        "password": "SecurePass123!",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def auth_tokens(client: AsyncClient, registered_user: dict) -> dict:
    """Register + login a player and return TokenResponse JSON."""
    resp = await client.post("/v1/auth/login", json={
        "username": "testplayer",
        "password": "SecurePass123!",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def auth_headers(auth_tokens: dict) -> dict:
    """Return Authorization header dict for an authenticated player."""
    return {"Authorization": f"Bearer {auth_tokens['access_token']}"}


@pytest_asyncio.fixture
async def second_auth_headers(client: AsyncClient) -> dict:
    """Register a second player and return their auth headers."""
    await client.post("/v1/auth/register", json={
        "username": "player2",
        "email": "player2@example.com",
        "password": "SecurePass123!",
    })
    resp = await client.post("/v1/auth/login", json={
        "username": "player2",
        "password": "SecurePass123!",
    })
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture
async def created_session(client: AsyncClient, auth_headers: dict) -> dict:
    """Create a session owned by the primary test player."""
    from uuid import uuid4

    # Register a game first so we have a valid game_id
    # (In tests we insert a game row directly via the DB, but to keep
    #  conftest self-contained we use a placeholder UUID that the service
    #  will 404 on — individual session tests that need a real game_id
    #  must create the game row themselves.)
    resp = await client.post(
        "/v1/sessions",
        json={
            "game_id": str(uuid4()),  # will fail — tests override as needed
            "config": {"mode": "test", "max_players": 2, "region": "us-east-1"},
        },
        headers=auth_headers,
    )
    # Return raw resp so callers can inspect the status (some tests expect 404)
    return {"response": resp, "data": resp.json() if resp.status_code == 201 else None}
