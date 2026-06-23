/**
 * nexus-js / npcs.ts
 * ────────────────────
 * NPCsClient — NPC lifecycle and interaction endpoints.
 *
 * Accessed via `nexus.npcs.*` on a NexusClient instance.
 *
 * Note: the spec's reference implementation has `listInSession` calling
 * `/sessions/${sessionId}/npcs`, but the actual deployed API route
 * (api/routers/npcs.py, Phase 2 Stage 4) is `/npcs/session/${sessionId}`.
 * Corrected here to match the real server.
 */

import type { NexusClient } from "./client";
import type { InteractResponse, NPCResponse, PaginatedMemory } from "./types";

export class NPCsClient {
  constructor(private c: NexusClient) {}

  /**
   * Spawn a new NPC into a session.
   *
   * `npcData` must match the API's NPCCreate shape — session_id, name,
   * personality, secrets, initial_emotional_state, confession_threshold,
   * memory_scope. See README for the full Marcus Webb example.
   *
   * The returned NPCResponse never includes `secrets` — they are stored
   * server-side only and never returned over the API.
   */
  create(npcData: Record<string, unknown>): Promise<NPCResponse> {
    return this.c.fetch<NPCResponse>("/npcs", {
      method: "POST",
      body: JSON.stringify(npcData),
    });
  }

  /** Retrieve the current state of an NPC. Throws NexusError (404) if not found. */
  get(npcId: string): Promise<NPCResponse> {
    return this.c.fetch<NPCResponse>(`/npcs/${npcId}`);
  }

  /**
   * Send a player message to the NPC and receive an in-character response.
   *
   * Always resolves (HTTP 200) — even if the server's internal LLM call
   * times out, the server returns a graceful fallback rather than an error.
   * Check `response.state_delta` for all-zero values to detect a fallback
   * occurred (the NPC's emotional state did not change that turn).
   */
  interact(npcId: string, playerMessage: string): Promise<InteractResponse> {
    return this.c.fetch<InteractResponse>(`/npcs/${npcId}/interact`, {
      method: "POST",
      body: JSON.stringify({ player_message: playerMessage }),
    });
  }

  /**
   * Retrieve paginated interaction history for an NPC.
   *
   * Always reads from cold storage (Postgres) — use `nexus.realtime` for
   * live state updates during an active session rather than polling this.
   */
  getMemory(npcId: string, limit = 20, offset = 0): Promise<PaginatedMemory> {
    return this.c.fetch<PaginatedMemory>(`/npcs/${npcId}/memory?limit=${limit}&offset=${offset}`);
  }

  /** List all NPCs currently spawned in a session. */
  listInSession(sessionId: string): Promise<NPCResponse[]> {
    return this.c.fetch<NPCResponse[]>(`/npcs/session/${sessionId}`);
  }
}
