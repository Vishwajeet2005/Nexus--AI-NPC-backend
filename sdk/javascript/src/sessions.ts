/**
 * nexus-js / sessions.ts
 * ────────────────────────
 * SessionsClient — session lifecycle endpoints.
 *
 * Accessed via `nexus.sessions.*` on a NexusClient instance.
 *
 * Note: the spec's reference implementation types `leave`, `lock`, and
 * `end` as `Promise<void>`, but the actual API (api/routers/sessions.py)
 * returns a full SessionResponse body (200, not 204) for all three —
 * so callers can inspect `is_locked`, `status`, `ended_at`, etc. without
 * a follow-up GET. Typed accordingly here.
 */

import type { NexusClient } from "./client";
import type { PlayerResponse, SessionResponse } from "./types";

export class SessionsClient {
  constructor(private c: NexusClient) {}

  /**
   * Create a new game session.
   *
   * Returns a SessionResponse with a freshly generated `join_code`
   * (format: "NEXUS-XXXX") and the creator registered as host.
   */
  create(gameId: string, config?: Record<string, unknown>): Promise<SessionResponse> {
    return this.c.fetch<SessionResponse>("/sessions", {
      method: "POST",
      body: JSON.stringify({ game_id: gameId, config: config ?? {} }),
    });
  }

  /** Retrieve full session details by UUID. Throws NexusError (404) if not found. */
  get(sessionId: string): Promise<SessionResponse> {
    return this.c.fetch<SessionResponse>(`/sessions/${sessionId}`);
  }

  /**
   * Join a session by its UUID.
   * Throws NexusError (409 full/already-joined/ended, or 423 locked).
   */
  join(sessionId: string): Promise<SessionResponse> {
    return this.c.fetch<SessionResponse>(`/sessions/${sessionId}/join`, { method: "POST" });
  }

  /**
   * Join a session using its human-readable join code (e.g. "NEXUS-AB23").
   * The join code is case-insensitive.
   */
  joinByCode(joinCode: string): Promise<SessionResponse> {
    return this.c.fetch<SessionResponse>(`/sessions/join/${joinCode}`, { method: "POST" });
  }

  /** Leave a session you are currently a member of. */
  leave(sessionId: string): Promise<SessionResponse> {
    return this.c.fetch<SessionResponse>(`/sessions/${sessionId}/leave`, { method: "POST" });
  }

  /** Lock a session to prevent new players from joining. Host-only. */
  lock(sessionId: string): Promise<SessionResponse> {
    return this.c.fetch<SessionResponse>(`/sessions/${sessionId}/lock`, { method: "POST" });
  }

  /** End a session permanently. Host-only. All active memberships are closed. */
  end(sessionId: string): Promise<SessionResponse> {
    return this.c.fetch<SessionResponse>(`/sessions/${sessionId}/end`, { method: "POST" });
  }

  /**
   * Shallow-merge `state` into the session's existing game state.
   *
   * `{ ...currentState, ...state }` — top-level keys in `state` overwrite
   * existing keys; nested objects are replaced wholesale, not deep-merged.
   */
  updateState(sessionId: string, state: Record<string, unknown>): Promise<SessionResponse> {
    return this.c.fetch<SessionResponse>(`/sessions/${sessionId}/state`, {
      method: "PATCH",
      body: JSON.stringify({ state }),
    });
  }

  /** List currently active players in a session. */
  listPlayers(sessionId: string): Promise<PlayerResponse[]> {
    return this.c.fetch<PlayerResponse[]>(`/sessions/${sessionId}/players`);
  }
}
