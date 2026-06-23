/**
 * nexus-js — JavaScript/TypeScript SDK for the Nexus AI-native game backend.
 *
 * Quick start:
 *
 *   import { NexusClient } from "nexus-js";
 *
 *   const nexus = new NexusClient({ host: "localhost:8000" });
 *   await nexus.auth.login("dev", "password123");
 *   const session = await nexus.sessions.create("your-game-id");
 *   const npc = await nexus.npcs.create({ ...marcusWebbData });
 *
 *   nexus.realtime.on("npc_state_changed", (event) => {
 *     console.log("NPC behaviour:", event.payload.behaviour);
 *   });
 *   await nexus.realtime.connect(session.id);
 *
 *   const response = await nexus.npcs.interact(npc.id, "Where were you on the 14th?");
 *   console.log(response.npc_response);
 *
 * See README.md for full documentation of every sub-client.
 */

export { NexusClient } from "./client";
export type { NexusClientOptions } from "./client";

export { AuthClient } from "./auth";
export { SessionsClient } from "./sessions";
export { NPCsClient } from "./npcs";
export { RealtimeClient } from "./realtime";

export { NexusError } from "./types";
export type {
  PlayerResponse,
  TokenResponse,
  SessionPlayerResponse,
  SessionResponse,
  NPCBehaviour,
  NPCEmotionalState,
  NPCResponse,
  InteractResponse,
  NPCMemoryEntry,
  PaginatedMemory,
  NexusEvent,
  NexusEventHandler,
} from "./types";
