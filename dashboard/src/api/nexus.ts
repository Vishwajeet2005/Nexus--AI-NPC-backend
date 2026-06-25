/**
 * dashboard/src/api/nexus.ts
 * ────────────────────────────
 * Thin typed wrapper around the Nexus REST API for the dashboard.
 *
 * Uses the VITE_API_URL environment variable so the dashboard can be
 * pointed at any Nexus instance by changing a single env var.
 */

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const V1 = `${BASE}/v1`;

let _token: string | null = null;
export function setToken(token: string) { _token = token; }
export function getToken() { return _token; }

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_token) headers["Authorization"] = `Bearer ${_token}`;

  const res = await fetch(`${V1}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
    throw new Error(err.error ?? `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export const api = {
  auth: {
    login: (username: string, password: string) =>
      req<{ access_token: string; refresh_token: string }>("POST", "/auth/login", { username, password }),
    guest: () =>
      req<{ access_token: string; refresh_token: string }>("POST", "/auth/guest"),
  },

  // ── Sessions ────────────────────────────────────────────────────────────────
  sessions: {
    list: () => req<SessionSummary[]>("GET", "/sessions/list").catch(() => [] as SessionSummary[]),
    get: (id: string) => req<Session>("GET", `/sessions/${id}`),
  },

  // ── NPCs ─────────────────────────────────────────────────────────────────────
  npcs: {
    listInSession: (sessionId: string) =>
      req<NPC[]>("GET", `/npcs/session/${sessionId}`),
    get: (npcId: string) => req<NPC>("GET", `/npcs/${npcId}`),
    getMemory: (npcId: string, limit = 20) =>
      req<{ entries: MemoryEntry[]; total: number }>("GET", `/npcs/${npcId}/memory?limit=${limit}`),
  },

  // ── Analytics ─────────────────────────────────────────────────────────────────
  analytics: {
    events: (params: { session_id?: string; event_type?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params.session_id) qs.set("session_id", params.session_id);
      if (params.event_type) qs.set("event_type", params.event_type);
      if (params.limit) qs.set("limit", String(params.limit));
      return req<{ events: AnalyticsEvent[]; total: number }>("GET", `/analytics/events?${qs}`);
    },
  },

  // ── API Keys ──────────────────────────────────────────────────────────────────
  apiKeys: {
    list: (gameId: string) =>
      req<{ keys: ApiKey[] }>("GET", `/games/${gameId}/api-keys`),
    create: (gameId: string, name: string) =>
      req<{ id: string; key: string; name: string; prefix: string }>(
        "POST", `/games/${gameId}/api-keys`, { name }
      ),
    revoke: (gameId: string, keyId: string) =>
      req<void>("DELETE", `/games/${gameId}/api-keys/${keyId}`),
  },

  // ── Webhooks ──────────────────────────────────────────────────────────────────
  webhooks: {
    list: () => req<{ webhooks: Webhook[] }>("GET", "/webhooks"),
    create: (url: string, events: string[], name?: string) =>
      req<Webhook>("POST", "/webhooks", { url, events, name }),
    test: (webhookId: string) =>
      req<{ delivery: DeliveryRecord }>("POST", `/webhooks/${webhookId}/test`),
  },
};

// ── Types ─────────────────────────────────────────────────────────────────────
export interface Session {
  id: string;
  join_code: string;
  status: "created" | "active" | "ended";
  max_players: number;
  region: string;
  game_mode: string | null;
  is_locked: boolean;
  players: SessionPlayer[];
  created_at: string;
  ended_at: string | null;
}
export type SessionSummary = Omit<Session, "players">;

export interface SessionPlayer {
  id: string;
  player_id: string;
  username: string;
  role: string;
  joined_at: string;
  left_at: string | null;
}

export type NPCBehaviour = "cooperative" | "deflecting" | "nervous" | "hostile" | "confessing";
export interface EmotionalState {
  stress: number;
  trust: number;
  suspicion: number;
  cooperation: number;
}
export interface NPC {
  id: string;
  session_id: string;
  name: string;
  current_emotional_state: EmotionalState;
  current_behaviour: NPCBehaviour;
  memory_scope: string;
  created_at: string;
}
export interface MemoryEntry {
  id: string;
  player_message: string;
  npc_response: string;
  behaviour: NPCBehaviour;
  state_before: EmotionalState;
  state_after: EmotionalState;
  secret_leaked: string | null;
  created_at: string;
}
export interface AnalyticsEvent {
  id: string;
  session_id: string | null;
  player_id: string | null;
  event_type: string;
  properties: Record<string, unknown> | null;
  created_at: string;
}
export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  is_active: boolean;
  created_at: string;
  last_used: string | null;
}
export interface DeliveryRecord {
  id: string;
  timestamp: string;
  event_type: string;
  http_status: number | null;
  duration_ms: number;
  success: boolean;
  error: string | null;
}
export interface Webhook {
  id: string;
  name: string;
  url: string;
  events: string[];
  is_active: boolean;
  created_at: string;
  last_delivery_status: number | null;
  delivery_history: DeliveryRecord[];
}
