/**
 * nexus-js / client.ts
 * ─────────────────────
 * NexusClient — the single entry point for the JavaScript/TypeScript SDK.
 *
 * Usage:
 *   const nexus = new NexusClient({ host: "localhost:8000" });
 *   await nexus.auth.login("dev", "password123");
 *   const session = await nexus.sessions.create("game-id");
 *   const npc = await nexus.npcs.create({...});
 *   const response = await nexus.npcs.interact(npc.id, "Where were you?");
 *
 * Every sub-client (`auth`, `sessions`, `npcs`, `realtime`) routes its HTTP
 * calls through this client's `fetch<T>()` method, so the base URL, the
 * Authorization header, and error translation are configured in exactly
 * one place.
 */

import { AuthClient } from "./auth";
import { NPCsClient } from "./npcs";
import { RealtimeClient } from "./realtime";
import { SessionsClient } from "./sessions";
import { NexusError } from "./types";

export interface NexusClientOptions {
  /** Host:port of the Nexus API, without scheme. Default: "localhost:8000" */
  host?: string;
  /** If true, use https:// and wss:// instead of http:// / ws://. Default: false */
  useTLS?: boolean;
}

export class NexusClient {
  readonly baseUrl: string;
  readonly wsUrl: string;

  /** The current access token, or null if not authenticated. Set automatically by AuthClient. */
  accessToken: string | null = null;
  /** The current refresh token, stored so refresh()/logout() can be called with no arguments. */
  refreshToken: string | null = null;

  readonly auth: AuthClient;
  readonly sessions: SessionsClient;
  readonly npcs: NPCsClient;
  readonly realtime: RealtimeClient;

  constructor({ host = "localhost:8000", useTLS = false }: NexusClientOptions = {}) {
    const scheme = useTLS ? "https" : "http";
    const wsScheme = useTLS ? "wss" : "ws";
    this.baseUrl = `${scheme}://${host}/v1`;
    this.wsUrl = `${wsScheme}://${host}/v1`;

    this.auth = new AuthClient(this);
    this.sessions = new SessionsClient(this);
    this.npcs = new NPCsClient(this);
    this.realtime = new RealtimeClient(this);
  }

  /** Attach an access token to all subsequent requests. Called automatically by AuthClient. */
  setToken(token: string): void {
    this.accessToken = token;
  }

  /** Remove the access token. Called automatically by AuthClient.logout(). */
  clearToken(): void {
    this.accessToken = null;
  }

  /**
   * Issue an HTTP request against the Nexus API and parse the JSON response.
   *
   * Generic type T is the expected shape of a successful response body.
   * Use `fetch<void>(...)` for endpoints that return 204 No Content.
   *
   * Throws NexusError for any non-2xx response, with `.message` and
   * `.code` populated from the server's ErrorResponse envelope where
   * available.
   */
  async fetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...(this.accessToken ? { Authorization: `Bearer ${this.accessToken}` } : {}),
      ...options.headers,
    };

    let res: Response;
    try {
      res = await fetch(`${this.baseUrl}${path}`, { ...options, headers });
    } catch (err) {
      // Network-level failure (DNS, connection refused, CORS, etc.) — fetch()
      // itself throws a TypeError here rather than returning a Response.
      const message = err instanceof Error ? err.message : "Network request failed";
      throw new NexusError(`Network error calling ${path}: ${message}`);
    }

    if (!res.ok) {
      const body: { error?: string; code?: string } = await res
        .json()
        .catch(() => ({}) as { error?: string; code?: string });
      throw new NexusError(body.error ?? `HTTP ${res.status}`, body.code);
    }

    // 204 No Content (e.g. POST /auth/logout) has no body to parse.
    if (res.status === 204) {
      return undefined as T;
    }

    return res.json() as Promise<T>;
  }

  /** Disconnects any open realtime connection. Call when you're done with this client. */
  close(): void {
    this.realtime.disconnect();
  }
}
