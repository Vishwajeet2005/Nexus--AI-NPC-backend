/**
 * nexus-js / realtime.ts
 * ─────────────────────────
 * RealtimeClient — WebSocket event subscription with an event-emitter API.
 *
 * Usage:
 *   nexus.realtime.on("npc_state_changed", (event) => {
 *     console.log(event.payload.behaviour);
 *   });
 *   await nexus.realtime.connect(session.id);
 *   ...
 *   nexus.realtime.disconnect();
 *
 * Uses the browser-native `WebSocket` global, so this file works unmodified
 * in browsers, Node 22+ (which ships WebSocket natively), and any bundler
 * target — no `ws` package dependency required.
 *
 * Connection lifecycle (mirrors the server's documented WS protocol):
 *   1. Open WebSocket to `${wsUrl}/realtime/${sessionId}`
 *   2. On open, immediately send `{"type": "auth", "token": accessToken}`
 *   3. Server replies `{"type": "connected", ...}` on success, or closes
 *      with code 4001 (auth failure) / 4002 (session not found/ended)
 *   4. Server sends `{"type": "ping"}` periodically — SDK auto-replies "pong"
 *   5. All events are dispatched to handlers registered via `.on(type, fn)`;
 *      a handler registered for `"*"` receives every event regardless of type
 */

import type { NexusClient } from "./client";
import type { NexusEvent, NexusEventHandler } from "./types";
import { NexusError } from "./types";

export class RealtimeClient {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, NexusEventHandler[]>();
  /** True once the "connected" confirmation frame has been received. */
  private connected = false;

  constructor(private c: NexusClient) {}

  /**
   * Register a handler for a specific event type.
   *
   * Pass "*" to receive every event regardless of type. Multiple handlers
   * may be registered for the same event type — all are called, in
   * registration order, when a matching event arrives.
   *
   * Returns `this` so calls can be chained:
   *   nexus.realtime.on("a", h1).on("b", h2);
   */
  on(eventType: string, handler: NexusEventHandler): this {
    const existing = this.handlers.get(eventType) ?? [];
    this.handlers.set(eventType, [...existing, handler]);
    return this;
  }

  /**
   * Remove a previously registered handler for the given event type.
   * Returns `this` so calls can be chained.
   */
  off(eventType: string, handler: NexusEventHandler): this {
    const existing = this.handlers.get(eventType) ?? [];
    this.handlers.set(
      eventType,
      existing.filter((h) => h !== handler),
    );
    return this;
  }

  /**
   * Connect to the session's WebSocket channel and perform the auth handshake.
   *
   * The returned Promise resolves once the server confirms the connection
   * (receives the `{"type": "connected", ...}` frame), or rejects if the
   * connection fails, the auth handshake is rejected (close code 4001), or
   * the session is not found / already ended (close code 4002).
   *
   * Uses the access token currently stored on the parent NexusClient (set
   * by a prior `login()`, `guest()`, or `refresh()` call).
   */
  connect(sessionId: string): Promise<void> {
    if (this.c.accessToken === null) {
      return Promise.reject(
        new NexusError(
          "Cannot connect to realtime channel without an access token. Call login() or guest() first.",
        ),
      );
    }

    return new Promise<void>((resolve, reject) => {
      this.connected = false;
      const socket = new WebSocket(`${this.c.wsUrl}/realtime/${sessionId}`);
      this.ws = socket;

      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "auth", token: this.c.accessToken }));
      };

      socket.onmessage = (rawEvent: MessageEvent<string>) => {
        let message: NexusEvent;
        try {
          message = JSON.parse(rawEvent.data) as NexusEvent;
        } catch {
          // Malformed frame — ignore rather than crashing the connection.
          return;
        }

        if (message.type === "connected" && !this.connected) {
          this.connected = true;
          resolve();
        }

        // Auto-reply to server heartbeat pings — keeps the connection alive
        // without requiring every consumer to handle "ping" themselves.
        if (message.type === "ping") {
          socket.send(JSON.stringify({ type: "pong" }));
        }

        this._dispatch(message);
      };

      socket.onerror = () => {
        const err = new NexusError("WebSocket connection failed");
        if (!this.connected) {
          reject(err);
        }
        // Errors after a successful connect are surfaced as a synthetic
        // "error" event rather than thrown, since there's no Promise left
        // to reject at that point — consumers can `.on("error", ...)`.
        this._dispatch({
          type: "error",
          payload: { message: err.message },
          timestamp: new Date().toISOString(),
        });
      };

      socket.onclose = (closeEvent: CloseEvent) => {
        if (!this.connected) {
          // Connection was rejected before the handshake completed.
          if (closeEvent.code === 4001) {
            reject(new NexusError("WebSocket authentication failed", "WS_AUTH_FAILED"));
            return;
          }
          if (closeEvent.code === 4002) {
            reject(new NexusError("Session not found or already ended", "WS_SESSION_INVALID"));
            return;
          }
          reject(new NexusError(`WebSocket closed before connecting (code ${closeEvent.code})`));
          return;
        }

        this.connected = false;
        this._dispatch({
          type: "disconnected",
          payload: { code: closeEvent.code, reason: closeEvent.reason },
          timestamp: new Date().toISOString(),
        });
      };
    });
  }

  /**
   * Close the WebSocket connection.
   *
   * Safe to call even if not currently connected (no-op in that case).
   * Does not throw.
   */
  disconnect(): void {
    if (this.ws !== null) {
      // Detach handlers before closing so a close triggered by disconnect()
      // doesn't fire a spurious "disconnected" event dispatch mid-teardown
      // for consumers who only care about server-initiated disconnects.
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onmessage = null;
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
  }

  /** True if the WebSocket connection is open and the auth handshake completed. */
  get isConnected(): boolean {
    return this.connected;
  }

  /** Dispatch an event to all handlers registered for its type, plus all "*" handlers. */
  private _dispatch(event: NexusEvent): void {
    const typed = this.handlers.get(event.type) ?? [];
    const wildcard = this.handlers.get("*") ?? [];
    [...typed, ...wildcard].forEach((handler) => handler(event));
  }
}
