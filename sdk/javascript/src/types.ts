/**
 * nexus-js / types.ts
 * ────────────────────
 * All TypeScript interfaces and the NexusError class for the Nexus SDK.
 *
 * Mirrors `api/schemas/` from the Python backend so SDK consumers get full
 * autocomplete and compile-time type checking — zero `any` anywhere in this
 * file or anywhere downstream that consumes it.
 */

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface PlayerResponse {
  id: string;
  username: string;
  email: string;
  is_guest: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// ── Sessions ──────────────────────────────────────────────────────────────────

export interface SessionPlayerResponse {
  id: string;
  player_id: string;
  username: string;
  role: string;
  joined_at: string;
  left_at: string | null;
}

export interface SessionResponse {
  id: string;
  game_id: string | null;
  join_code: string;
  status: "created" | "active" | "ended";
  max_players: number;
  region: string;
  game_mode: string | null;
  is_locked: boolean;
  config: Record<string, unknown> | null;
  state: Record<string, unknown> | null;
  players: SessionPlayerResponse[];
  created_at: string;
  ended_at: string | null;
}

// ── NPCs ──────────────────────────────────────────────────────────────────────

export type NPCBehaviour =
  | "cooperative"
  | "deflecting"
  | "nervous"
  | "hostile"
  | "confessing";

export interface NPCEmotionalState {
  stress: number;
  trust: number;
  suspicion: number;
  cooperation: number;
}

export interface NPCResponse {
  id: string;
  session_id: string;
  name: string;
  personality: Record<string, unknown>;
  current_emotional_state: NPCEmotionalState;
  current_behaviour: NPCBehaviour;
  memory_scope: "session" | "persistent";
  created_at: string;
}

export interface InteractResponse {
  npc_response: string;
  behaviour: NPCBehaviour;
  emotional_state: NPCEmotionalState;
  state_delta: NPCEmotionalState;
  secret_leaked: string | null;
  interaction_id: string;
}

export interface NPCMemoryEntry {
  id: string;
  player_id: string;
  player_message: string;
  npc_response: string;
  behaviour: NPCBehaviour;
  state_before: NPCEmotionalState;
  state_after: NPCEmotionalState;
  secret_leaked: string | null;
  created_at: string;
}

export interface PaginatedMemory {
  entries: NPCMemoryEntry[];
  total: number;
  limit: number;
  offset: number;
}

// ── Real-time events ────────────────────────────────────────────────────────────

export interface NexusEvent {
  type: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

export type NexusEventHandler = (event: NexusEvent) => void;

// ── Errors ────────────────────────────────────────────────────────────────────

/**
 * Thrown by every NexusClient method on any non-2xx response or WebSocket
 * connection failure. SDK consumers never see a raw fetch Response or a
 * generic Error from this library — always a NexusError (or, where the
 * caller wants finer-grained handling, they can inspect `.code`, which
 * mirrors the server's ErrorResponse.code field, e.g. "ACCOUNT_LOCKED",
 * "SESSION_FULL", "NPC_NOT_FOUND").
 */
export class NexusError extends Error {
  public code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "NexusError";
    this.code = code;

    // Restore the prototype chain — required when targeting ES2022 with
    // certain bundler/transpiler configurations so `instanceof NexusError`
    // keeps working after the class is bundled.
    Object.setPrototypeOf(this, NexusError.prototype);
  }
}
