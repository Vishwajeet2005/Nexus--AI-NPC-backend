"""
migrations/env.py
─────────────────
Alembic environment script, configured for async SQLAlchemy 2.0 + asyncpg.

Key differences from the default env.py template:
- Uses `AsyncEngine` / `run_async_migrations()` instead of synchronous connect.
- Imports `Base` from api.models so autogenerate sees all mapped tables.
- Reads the DSN from pydantic Settings (which honours .env) rather than
  alembic.ini, keeping secrets out of version control.
- The `include_schemas` and `compare_type` options are enabled for safer diffs.
"""

from __future__ import annotations

import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Project imports ────────────────────────────────────────────────────────────
# Importing Base here causes all mapped models to register with its metadata,
# which is what autogenerate reads. The explicit model imports in
# api/models/__init__.py guarantee every table is visible.
from api.models import Base  # noqa: F401 — populates Base.metadata
from api.config import get_settings

# ── Alembic Config object ──────────────────────────────────────────────────────
config = context.config

# ── Logging ────────────────────────────────────────────────────────────────────
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# ── Target metadata ────────────────────────────────────────────────────────────
# Alembic compares this against the live DB to generate migration diffs.
target_metadata = Base.metadata

# ── DSN override ───────────────────────────────────────────────────────────────
# Pull the URL from Settings so alembic.ini never needs a real secret.
_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.database_url)


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode (emit SQL to stdout, no live connection).

    Useful for generating a SQL script to review or apply manually in production.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Detect column type changes (e.g. VARCHAR length changes)
        compare_type=True,
        # Detect server_default changes
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure context and run migrations against a live connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Include the public schema explicitly
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create an async engine, acquire a sync-compatible connection via
    `run_sync()`, and delegate to `do_run_migrations()`.

    SQLAlchemy's `run_sync` bridges the gap between Alembic's synchronous
    migration runner and our async engine — it's the officially recommended
    pattern for async Alembic environments.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _settings.database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        # NullPool prevents connection reuse between migration steps,
        # which is the correct choice for a short-lived CLI process.
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online mode — runs the async event loop."""
    asyncio.run(run_async_migrations())


# ── Dispatch ───────────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
