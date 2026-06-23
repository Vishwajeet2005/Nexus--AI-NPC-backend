/**
 * sdk/javascript/tests/client.test.ts
 * ─────────────────────────────────────
 * Vitest suite for the nexus-js SDK.
 *
 * Spec test cases (from NEXUS_PHASE3_MEGAPROMPT.md):
 *   - auth.login sets accessToken
 *   - sessions.create returns SessionResponse
 *   - npcs.interact returns InteractResponse
 *   - realtime.on("npc_state_changed") handler called on WS message
 *   - NexusError thrown on 4xx responses
 *
 * Mocking strategy:
 *   - `fetch` is mocked globally via `vi.stubGlobal("fetch", ...)` so no
 *     real HTTP calls are made. Each test registers exactly the responses
 *     it expects, in call order.
 *   - `WebSocket` is mocked with a minimal in-memory fake that implements
 *     the same event-handler-property interface (onopen/onmessage/onerror/
 *     onclose) the SDK's realtime.ts relies on, plus a `send()` spy and a
 *     test-only `__serverSend()` helper to simulate inbound server frames.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NexusClient, NexusError } from "../src/index";
import type { NexusEvent } from "../src/types";

// ── Fake WebSocket ──────────────────────────────────────────────────────────────

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  url: string;
  sent: string[] = [];
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent<string>) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    // Mimic real WebSocket: closing triggers onclose asynchronously.
    queueMicrotask(() => {
      this.onclose?.(new CloseEvent("close", { code: 1000, reason: "client closed" }));
    });
  }

  /** Test helper: simulate the connection opening. */
  __open(): void {
    this.onopen?.(new Event("open"));
  }

  /** Test helper: simulate the server pushing a JSON frame. */
  __serverSend(payload: unknown): void {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(payload) }) as MessageEvent<string>,
    );
  }

  /** Test helper: simulate the server closing the connection with a specific code. */
  __serverClose(code: number, reason = ""): void {
    // CloseEvent is not available in the Node/vitest environment, so we
    // construct a minimal duck-typed object that satisfies the SDK's handler.
    const ev = { type: "close", code, reason, wasClean: code === 1000 } as unknown as CloseEvent;
    this.onclose?.(ev);
  }
}

// ── Test helpers ────────────────────────────────────────────────────────────────

function mockFetchOnce(status: number, body: unknown, headers?: Record<string, string>): void {
  const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  fetchMock.mockResolvedValueOnce(
    new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json", ...headers },
    }),
  );
}

function lastFetchCall(): [string, RequestInit] {
  const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const calls = fetchMock.mock.calls;
  return calls[calls.length - 1] as [string, RequestInit];
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  vi.stubGlobal("WebSocket", FakeWebSocket);
  FakeWebSocket.instances = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ═══════════════════════════════════════════════════════════════════════════════
// auth.login sets accessToken
// ═══════════════════════════════════════════════════════════════════════════════

describe("auth.login", () => {
  it("sets accessToken on the client after a successful login", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    expect(nexus.accessToken).toBeNull();

    mockFetchOnce(200, {
      access_token: "fake-access-token",
      refresh_token: "fake-refresh-token",
      token_type: "bearer",
      expires_in: 900,
    });

    const tokens = await nexus.auth.login("alice", "SecurePass123!");

    expect(tokens.access_token).toBe("fake-access-token");
    expect(nexus.accessToken).toBe("fake-access-token");
    expect(nexus.refreshToken).toBe("fake-refresh-token");
  });

  it("sends the username/password in the request body", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    mockFetchOnce(200, {
      access_token: "t",
      refresh_token: "r",
      token_type: "bearer",
      expires_in: 900,
    });

    await nexus.auth.login("bob", "hunter2");

    const [url, options] = lastFetchCall();
    expect(url).toBe("http://test.local:8000/v1/auth/login");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body as string)).toEqual({
      username: "bob",
      password: "hunter2",
    });
  });

  it("attaches the access token to subsequent requests via Authorization header", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    mockFetchOnce(200, {
      access_token: "header-token",
      refresh_token: "r",
      token_type: "bearer",
      expires_in: 900,
    });
    await nexus.auth.login("alice", "pw");

    mockFetchOnce(200, {
      id: "s-1",
      game_id: "g-1",
      join_code: "NEXUS-AB23",
      status: "created",
      max_players: 4,
      region: "us-east-1",
      game_mode: null,
      is_locked: false,
      config: {},
      state: {},
      players: [],
      created_at: "2025-01-01T00:00:00",
      ended_at: null,
    });
    await nexus.sessions.get("s-1");

    const [, options] = lastFetchCall();
    const headers = options.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer header-token");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// sessions.create returns SessionResponse
// ═══════════════════════════════════════════════════════════════════════════════

describe("sessions.create", () => {
  it("returns a fully typed SessionResponse with a join_code", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });

    mockFetchOnce(201, {
      id: "s-0001",
      game_id: "g-0001",
      join_code: "NEXUS-7742",
      status: "created",
      max_players: 4,
      region: "us-east-1",
      game_mode: "interrogation",
      is_locked: false,
      config: { mode: "interrogation" },
      state: {},
      players: [],
      created_at: "2025-01-01T00:00:00",
      ended_at: null,
    });

    const session = await nexus.sessions.create("g-0001", { mode: "interrogation" });

    expect(session.id).toBe("s-0001");
    expect(session.join_code).toBe("NEXUS-7742");
    expect(session.status).toBe("created");
    expect(session.max_players).toBe(4);
    expect(session.players).toEqual([]);
  });

  it("sends game_id and config in the request body", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    mockFetchOnce(201, {
      id: "s-1",
      game_id: "g-1",
      join_code: "NEXUS-ZZZZ",
      status: "created",
      max_players: 4,
      region: "us-east-1",
      game_mode: null,
      is_locked: false,
      config: {},
      state: {},
      players: [],
      created_at: "2025-01-01T00:00:00",
      ended_at: null,
    });

    await nexus.sessions.create("g-1", { region: "eu-west-1" });

    const [url, options] = lastFetchCall();
    expect(url).toBe("http://test.local:8000/v1/sessions");
    expect(JSON.parse(options.body as string)).toEqual({
      game_id: "g-1",
      config: { region: "eu-west-1" },
    });
  });

  it("defaults config to an empty object when omitted", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    mockFetchOnce(201, {
      id: "s-1",
      game_id: "g-1",
      join_code: "NEXUS-ZZZZ",
      status: "created",
      max_players: 4,
      region: "us-east-1",
      game_mode: null,
      is_locked: false,
      config: {},
      state: {},
      players: [],
      created_at: "2025-01-01T00:00:00",
      ended_at: null,
    });

    await nexus.sessions.create("g-1");

    const [, options] = lastFetchCall();
    expect(JSON.parse(options.body as string).config).toEqual({});
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// npcs.interact returns InteractResponse
// ═══════════════════════════════════════════════════════════════════════════════

describe("npcs.interact", () => {
  it("returns a fully typed InteractResponse", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });

    mockFetchOnce(200, {
      npc_response: "I was at The Anchor bar all evening.",
      behaviour: "deflecting",
      emotional_state: { stress: 0.35, trust: 0.35, suspicion: 0.45, cooperation: 0.5 },
      state_delta: { stress: 0.15, trust: -0.05, suspicion: 0.1, cooperation: -0.05 },
      secret_leaked: null,
      interaction_id: "i-0001",
    });

    const response = await nexus.npcs.interact("npc-0001", "Where were you?");

    expect(response.npc_response).toBe("I was at The Anchor bar all evening.");
    expect(response.behaviour).toBe("deflecting");
    expect(response.emotional_state.stress).toBe(0.35);
    expect(response.state_delta.stress).toBe(0.15);
    expect(response.secret_leaked).toBeNull();
    expect(response.interaction_id).toBe("i-0001");
  });

  it("sends player_message in the request body", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    mockFetchOnce(200, {
      npc_response: "...",
      behaviour: "cooperative",
      emotional_state: { stress: 0.2, trust: 0.5, suspicion: 0.3, cooperation: 0.6 },
      state_delta: { stress: 0, trust: 0, suspicion: 0, cooperation: 0 },
      secret_leaked: null,
      interaction_id: "i-1",
    });

    await nexus.npcs.interact("npc-1", "We have CCTV footage.");

    const [url, options] = lastFetchCall();
    expect(url).toBe("http://test.local:8000/v1/npcs/npc-1/interact");
    expect(JSON.parse(options.body as string)).toEqual({
      player_message: "We have CCTV footage.",
    });
  });

  it("correctly types secret_leaked when a secret is revealed", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    mockFetchOnce(200, {
      npc_response: "All right. I left at 10:15, not midnight.",
      behaviour: "nervous",
      emotional_state: { stress: 0.7, trust: 0.3, suspicion: 0.55, cooperation: 0.4 },
      state_delta: { stress: 0.05, trust: 0, suspicion: 0, cooperation: 0 },
      secret_leaked: "alibi_weakness",
      interaction_id: "i-2",
    });

    const response = await nexus.npcs.interact("npc-1", "We have CCTV showing 10:15.");
    expect(response.secret_leaked).toBe("alibi_weakness");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// realtime.on("npc_state_changed") handler called on WS message
// ═══════════════════════════════════════════════════════════════════════════════

describe("realtime.on", () => {
  it("calls the registered handler when a matching event arrives over the WebSocket", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    nexus.accessToken = "ws-test-token"; // bypass login for this WS-only test

    const received: NexusEvent[] = [];
    nexus.realtime.on("npc_state_changed", (event) => {
      received.push(event);
    });

    const connectPromise = nexus.realtime.connect("s-0001");

    // Grab the FakeWebSocket instance the SDK just constructed.
    const fakeWs = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    expect(fakeWs.url).toBe("ws://test.local:8000/v1/realtime/s-0001");

    fakeWs.__open();
    // Auth frame should have been sent immediately on open.
    expect(JSON.parse(fakeWs.sent[0])).toEqual({ type: "auth", token: "ws-test-token" });

    // Server confirms the connection.
    fakeWs.__serverSend({ type: "connected", session_id: "s-0001", player_id: "p-0001" });
    await connectPromise;

    // Server pushes the event under test.
    fakeWs.__serverSend({
      type: "npc_state_changed",
      payload: {
        npc_id: "npc-0001",
        npc_name: "Marcus Webb",
        behaviour: "deflecting",
        emotional_state: { stress: 0.35, trust: 0.35, suspicion: 0.45, cooperation: 0.5 },
        secret_leaked: null,
      },
      timestamp: "2025-01-01T00:00:00",
    });

    expect(received).toHaveLength(1);
    expect(received[0].type).toBe("npc_state_changed");
    expect(received[0].payload.npc_name).toBe("Marcus Webb");
    expect(received[0].payload.behaviour).toBe("deflecting");
  });

  it("dispatches to '*' wildcard handlers for every event type", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    nexus.accessToken = "ws-test-token";

    const types: string[] = [];
    nexus.realtime.on("*", (event) => types.push(event.type));

    const connectPromise = nexus.realtime.connect("s-0001");
    const fakeWs = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    fakeWs.__open();
    fakeWs.__serverSend({ type: "connected", session_id: "s-1", player_id: "p-1" });
    await connectPromise;

    fakeWs.__serverSend({ type: "player.joined", payload: {} });
    fakeWs.__serverSend({ type: "session.state_updated", payload: {} });

    expect(types).toEqual(["connected", "player.joined", "session.state_updated"]);
  });

  it("automatically replies to server ping frames with pong", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    nexus.accessToken = "ws-test-token";

    const connectPromise = nexus.realtime.connect("s-0001");
    const fakeWs = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    fakeWs.__open();
    fakeWs.__serverSend({ type: "connected", session_id: "s-1", player_id: "p-1" });
    await connectPromise;

    fakeWs.__serverSend({ type: "ping" });

    const sentTypes = fakeWs.sent.map((s) => JSON.parse(s).type);
    expect(sentTypes).toContain("pong");
  });

  it("removes a handler via off() so it no longer fires", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    nexus.accessToken = "ws-test-token";

    const received: string[] = [];
    const handler = (event: NexusEvent): void => {
      received.push(event.type);
    };
    nexus.realtime.on("player.joined", handler);
    nexus.realtime.off("player.joined", handler);

    const connectPromise = nexus.realtime.connect("s-0001");
    const fakeWs = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    fakeWs.__open();
    fakeWs.__serverSend({ type: "connected", session_id: "s-1", player_id: "p-1" });
    await connectPromise;

    fakeWs.__serverSend({ type: "player.joined", payload: {} });

    expect(received).toEqual([]);
  });

  it("rejects connect() if no access token is set", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    await expect(nexus.realtime.connect("s-0001")).rejects.toThrow(NexusError);
  });

  it("rejects connect() when the server closes with code 4001 (auth failed)", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    nexus.accessToken = "bad-token";

    const connectPromise = nexus.realtime.connect("s-0001");
    const fakeWs = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    fakeWs.__open();
    fakeWs.__serverClose(4001, "Authentication failed");

    await expect(connectPromise).rejects.toThrow(NexusError);
    await expect(connectPromise).rejects.toMatchObject({ code: "WS_AUTH_FAILED" });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// NexusError thrown on 4xx responses
// ═══════════════════════════════════════════════════════════════════════════════

describe("NexusError on 4xx responses", () => {
  it("throws NexusError with message and code on 401", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });

    mockFetchOnce(401, {
      error: "Invalid username or password.",
      code: "INVALID_CREDENTIALS",
      request_id: "11111111-1111-1111-1111-111111111111",
    });

    await expect(nexus.auth.login("alice", "wrong")).rejects.toThrow(NexusError);

    mockFetchOnce(401, {
      error: "Invalid username or password.",
      code: "INVALID_CREDENTIALS",
      request_id: "11111111-1111-1111-1111-111111111111",
    });
    try {
      await nexus.auth.login("alice", "wrong");
      expect.unreachable("Expected login() to throw");
    } catch (err) {
      expect(err).toBeInstanceOf(NexusError);
      expect((err as NexusError).message).toBe("Invalid username or password.");
      expect((err as NexusError).code).toBe("INVALID_CREDENTIALS");
    }
  });

  it("throws NexusError with code ACCOUNT_LOCKED on 423", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });

    mockFetchOnce(423, {
      error: "Account locked due to too many failed login attempts.",
      code: "ACCOUNT_LOCKED",
      request_id: "22222222-2222-2222-2222-222222222222",
    });

    try {
      await nexus.auth.login("locked_user", "whatever");
      expect.unreachable("Expected login() to throw");
    } catch (err) {
      expect(err).toBeInstanceOf(NexusError);
      expect((err as NexusError).code).toBe("ACCOUNT_LOCKED");
    }
  });

  it("throws NexusError with code SESSION_FULL on 409", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    nexus.accessToken = "valid-token";

    mockFetchOnce(409, {
      error: "Session is full.",
      code: "SESSION_FULL",
      request_id: "33333333-3333-3333-3333-333333333333",
    });

    try {
      await nexus.sessions.join("full-session-id");
      expect.unreachable("Expected join() to throw");
    } catch (err) {
      expect(err).toBeInstanceOf(NexusError);
      expect((err as NexusError).code).toBe("SESSION_FULL");
    }
  });

  it("throws NexusError with code NPC_NOT_FOUND on 404", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    nexus.accessToken = "valid-token";

    mockFetchOnce(404, {
      error: "NPC not found.",
      code: "NPC_NOT_FOUND",
      request_id: "44444444-4444-4444-4444-444444444444",
    });

    try {
      await nexus.npcs.get("00000000-0000-0000-0000-000000000000");
      expect.unreachable("Expected get() to throw");
    } catch (err) {
      expect(err).toBeInstanceOf(NexusError);
      expect((err as NexusError).code).toBe("NPC_NOT_FOUND");
    }
  });

  it("falls back to a generic message when the error body is not JSON", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(
      new Response("Internal Server Error", {
        status: 500,
        headers: { "Content-Type": "text/plain" },
      }),
    );

    try {
      await nexus.auth.login("alice", "pw");
      expect.unreachable("Expected login() to throw");
    } catch (err) {
      expect(err).toBeInstanceOf(NexusError);
      expect((err as NexusError).message).toBe("HTTP 500");
      expect((err as NexusError).code).toBeUndefined();
    }
  });

  it("does not throw on 204 No Content and resolves with undefined", async () => {
    const nexus = new NexusClient({ host: "test.local:8000" });
    nexus.accessToken = "valid-token";
    nexus.refreshToken = "valid-refresh";

    mockFetchOnce(204, null);

    await expect(nexus.auth.logout()).resolves.toBeUndefined();
    expect(nexus.accessToken).toBeNull();
  });
});
