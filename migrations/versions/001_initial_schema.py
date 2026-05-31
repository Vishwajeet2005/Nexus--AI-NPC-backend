"""Initial schema: players, games, sessions, session_players, npcs, npc_interactions, analytics_events

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

Creates the complete Phase 1 database schema in dependency order:
  1. players          — no FK dependencies
  2. games            — FK → players
  3. sessions         — FK → games
  4. session_players  — FK → sessions, players
  5. npcs             — FK → sessions
  6. npc_interactions — FK → npcs, players, sessions
  7. analytics_events — FK → sessions (player_id has no FK by design)

All primary keys use gen_random_uuid() (requires pgcrypto or Postgres 13+
where the function is built-in). Timestamps use server-side NOW() defaults.

The downgrade() function drops tables in reverse dependency order to avoid
FK constraint violations.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. players ─────────────────────────────────────────────────────────────
    op.create_table(
        "players",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "is_guest",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.Column(
            "is_locked",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_players"),
        sa.UniqueConstraint("username", name="uq_players_username"),
        sa.UniqueConstraint("email", name="uq_players_email"),
    )
    op.create_index("ix_players_username", "players", ["username"], unique=True)
    op.create_index("ix_players_email", "players", ["email"], unique=True)
    op.create_index("ix_players_created_at", "players", ["created_at"])

    # ── 2. games ───────────────────────────────────────────────────────────────
    op.create_table(
        "games",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("api_key", sa.String(64), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_games"),
        sa.UniqueConstraint("api_key", name="uq_games_api_key"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["players.id"],
            name="fk_games_owner_id_players",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_games_api_key", "games", ["api_key"], unique=True)
    op.create_index("ix_games_owner_id", "games", ["owner_id"])
    op.create_index("ix_games_created_at", "games", ["created_at"])

    # ── 3. sessions ────────────────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("join_code", sa.String(12), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'created'"),
            nullable=False,
        ),
        sa.Column(
            "max_players",
            sa.Integer(),
            server_default=sa.text("4"),
            nullable=False,
        ),
        sa.Column("region", sa.String(20), nullable=False),
        sa.Column("game_mode", sa.String(50), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "is_locked",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.UniqueConstraint("join_code", name="uq_sessions_join_code"),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name="fk_sessions_game_id_games",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_sessions_join_code", "sessions", ["join_code"], unique=True)
    op.create_index("ix_sessions_game_id", "sessions", ["game_id"])
    op.create_index("ix_sessions_status", "sessions", ["status"])
    op.create_index("ix_sessions_created_at", "sessions", ["created_at"])

    # ── 4. session_players ─────────────────────────────────────────────────────
    op.create_table(
        "session_players",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("left_at", sa.DateTime(), nullable=True),
        sa.Column(
            "role",
            sa.String(20),
            server_default=sa.text("'player'"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_players"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_session_players_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name="fk_session_players_player_id_players",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_session_players_session_id", "session_players", ["session_id"])
    op.create_index("ix_session_players_player_id", "session_players", ["player_id"])
    op.create_index("ix_session_players_created_at", "session_players", ["created_at"])

    # ── 5. npcs ────────────────────────────────────────────────────────────────
    op.create_table(
        "npcs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("personality", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("secrets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("initial_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "memory_scope",
            sa.String(20),
            server_default=sa.text("'session'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_npcs"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_npcs_session_id_sessions",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_npcs_session_id", "npcs", ["session_id"])
    op.create_index("ix_npcs_created_at", "npcs", ["created_at"])

    # ── 6. npc_interactions ────────────────────────────────────────────────────
    op.create_table(
        "npc_interactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("npc_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_message", sa.Text(), nullable=False),
        sa.Column("npc_response", sa.Text(), nullable=False),
        sa.Column("state_before", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state_after", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("behaviour", sa.String(30), nullable=False),
        sa.Column("secret_leaked", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_npc_interactions"),
        sa.ForeignKeyConstraint(
            ["npc_id"],
            ["npcs.id"],
            name="fk_npc_interactions_npc_id_npcs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name="fk_npc_interactions_player_id_players",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_npc_interactions_session_id_sessions",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_npc_interactions_npc_id", "npc_interactions", ["npc_id"])
    op.create_index("ix_npc_interactions_player_id", "npc_interactions", ["player_id"])
    op.create_index("ix_npc_interactions_session_id", "npc_interactions", ["session_id"])
    op.create_index("ix_npc_interactions_created_at", "npc_interactions", ["created_at"])

    # ── 7. analytics_events ────────────────────────────────────────────────────
    op.create_table(
        "analytics_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        # player_id: no FK constraint — see event.py module docstring
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analytics_events"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_analytics_events_session_id_sessions",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_analytics_events_session_id", "analytics_events", ["session_id"])
    op.create_index("ix_analytics_events_player_id", "analytics_events", ["player_id"])
    op.create_index("ix_analytics_events_event_type", "analytics_events", ["event_type"])
    op.create_index("ix_analytics_events_created_at", "analytics_events", ["created_at"])


def downgrade() -> None:
    """
    Drop all tables in reverse dependency order (children before parents)
    to avoid FK constraint violations.
    """
    # Level 3: no dependents
    op.drop_index("ix_analytics_events_created_at", table_name="analytics_events")
    op.drop_index("ix_analytics_events_event_type", table_name="analytics_events")
    op.drop_index("ix_analytics_events_player_id", table_name="analytics_events")
    op.drop_index("ix_analytics_events_session_id", table_name="analytics_events")
    op.drop_table("analytics_events")

    op.drop_index("ix_npc_interactions_created_at", table_name="npc_interactions")
    op.drop_index("ix_npc_interactions_session_id", table_name="npc_interactions")
    op.drop_index("ix_npc_interactions_player_id", table_name="npc_interactions")
    op.drop_index("ix_npc_interactions_npc_id", table_name="npc_interactions")
    op.drop_table("npc_interactions")

    # Level 2: depend on sessions
    op.drop_index("ix_npcs_created_at", table_name="npcs")
    op.drop_index("ix_npcs_session_id", table_name="npcs")
    op.drop_table("npcs")

    op.drop_index("ix_session_players_created_at", table_name="session_players")
    op.drop_index("ix_session_players_player_id", table_name="session_players")
    op.drop_index("ix_session_players_session_id", table_name="session_players")
    op.drop_table("session_players")

    # Level 1: depend on games
    op.drop_index("ix_sessions_created_at", table_name="sessions")
    op.drop_index("ix_sessions_status", table_name="sessions")
    op.drop_index("ix_sessions_game_id", table_name="sessions")
    op.drop_index("ix_sessions_join_code", table_name="sessions")
    op.drop_table("sessions")

    # Level 0: depend on players
    op.drop_index("ix_games_created_at", table_name="games")
    op.drop_index("ix_games_owner_id", table_name="games")
    op.drop_index("ix_games_api_key", table_name="games")
    op.drop_table("games")

    # Root
    op.drop_index("ix_players_created_at", table_name="players")
    op.drop_index("ix_players_email", table_name="players")
    op.drop_index("ix_players_username", table_name="players")
    op.drop_table("players")
