# nexus-js

JavaScript/TypeScript SDK for the Nexus AI-native game backend — Promise-based, fully typed, zero `any`, works in both browsers and Node.js.

---

## Installation

```bash
npm install nexus-js
```

For local development against an editable Nexus checkout:

```bash
cd sdk/javascript
npm install
npm run build
npm link  # then `npm link nexus-js` in your consuming project
```

Requires Node.js 18+ (for native `fetch`) or any modern browser. Node.js 22+ also ships a native `WebSocket` global; on Node 18–21 you'll need a `WebSocket` polyfill (e.g. `undici` or `ws` with `globalThis.WebSocket` assigned) since this SDK intentionally uses the browser-native API rather than bundling a Node-specific WebSocket client.

---

## Quick Start

```typescript
import { NexusClient } from "nexus-js";

const nexus = new NexusClient({ host: "localhost:8000" });
await nexus.auth.login("dev", "password123");
const session = await nexus.sessions.create("your-game-id");
const npc = await nexus.npcs.create({ /* ...marcusWebbData */ });

nexus.realtime.on("npc_state_changed", (event) => {
  console.log("NPC behaviour:", event.payload.behaviour);
});
await nexus.realtime.connect(session.id);

const response = await nexus.npcs.interact(npc.id, "Where were you on the 14th?");
console.log(response.npc_response);
```

That's the entire integration — ten lines, fully typed, no manual fetch calls or response parsing.

---

## Authentication

`nexus.auth` exposes five methods. Any method returning a `TokenResponse`
automatically attaches the access token to all future requests made by this
`NexusClient` instance.

```typescript
// Register a new account (does not log in)
const player = await nexus.auth.register("alice", "alice@example.com", "SecurePass123!");

// Log in — access token is now active on this client
const tokens = await nexus.auth.login("alice", "SecurePass123!");

// Or skip registration entirely with an anonymous guest account
const guestTokens = await nexus.auth.guest();

// Refresh before the access token expires (15 min default lifetime)
const refreshed = await nexus.auth.refresh(); // uses the stored refresh token
// or explicitly: await nexus.auth.refresh(tokens.refresh_token);

// Log out — blacklists both tokens server-side, clears local state
await nexus.auth.logout();
console.log(nexus.accessToken); // null
```

**Account lockout:** after 5 consecutive failed login attempts, the account
locks and `login()` throws `NexusError` (code `"ACCOUNT_LOCKED"`) even with
the correct password afterward.

---

## Sessions

`nexus.sessions` manages multiplayer game session lifecycle.

```typescript
// Create a session
const session = await nexus.sessions.create("game-uuid", {
  mode: "interrogation",
  max_players: 4,
  region: "us-east-1",
});
console.log(session.join_code); // "NEXUS-7742"

// A second client joins by UUID or by the human-readable code
await nexus.sessions.join(session.id);
await nexus.sessions.joinByCode("NEXUS-7742");

// Inspect current session state
const current = await nexus.sessions.get(session.id);
const players = await nexus.sessions.listPlayers(session.id);

// Merge game state (shallow merge — top-level keys overwrite, not deep merge)
const updated = await nexus.sessions.updateState(session.id, { phase: "interrogation", round: 2 });

// Host-only actions
await nexus.sessions.lock(session.id); // stop new players from joining
await nexus.sessions.end(session.id);  // permanently end the session

// Leave a session you're a member of
await nexus.sessions.leave(session.id);
```

---

## NPCs

`nexus.npcs` is the core gameplay surface — spawning NPCs and driving
conversations with them.

```typescript
// Spawn an NPC (full personality + secrets definition)
const npc = await nexus.npcs.create({
  session_id: session.id,
  name: "Marcus Webb",
  personality: {
    traits: ["calculated", "defensive"],
    motivation: "Protect his brother",
    fear: "Prison",
    background: "Mid-level accountant for 15 years.",
    speech_style: "Terse, precise.",
    tells: {
      cooperative: "Leans back. Makes eye contact.",
      deflecting: "Answers a question with a question.",
      nervous: "Uses filler phrases.",
      hostile: "Goes monosyllabic.",
    },
  },
  secrets: [
    {
      id: "alibi_weakness",
      content: "Left the bar 105 minutes before he claims.",
      reveal_threshold: 0.65,
      reveal_trigger: "Player presents CCTV evidence.",
    },
  ],
  initial_emotional_state: { stress: 0.2, trust: 0.4, suspicion: 0.35, cooperation: 0.55 },
});

// Talk to the NPC
const response = await nexus.npcs.interact(npc.id, "Where were you on the night of the 14th?");
console.log(response.npc_response);    // in-character reply
console.log(response.behaviour);       // "cooperative" | "deflecting" | "nervous" | "hostile" | "confessing"
console.log(response.emotional_state); // { stress, trust, suspicion, cooperation }
console.log(response.secret_leaked);   // null, or the secret's id if revealed this turn

// Read interaction history (paginated, always from durable storage)
const memory = await nexus.npcs.getMemory(npc.id, 20, 0);
for (const entry of memory.entries) {
  console.log(entry.player_message, "→", entry.npc_response);
}

// List every NPC currently in a session
const npcsInSession = await nexus.npcs.listInSession(session.id);
```

**On LLM failure:** `interact()` always resolves (HTTP 200), even if the
server's internal LLM call times out. Check `response.state_delta` — if
every field is `0`, the server returned a graceful fallback and the NPC's
emotional state did not change. This is not an SDK-level error; secret
revelation and state drift remain guaranteed-consistent either way.

---

## Real-Time Events

`nexus.realtime` is a WebSocket-based event emitter for live session
updates — player joins/leaves, session state changes, and NPC behaviour
shifts — without polling.

```typescript
nexus.realtime.on("npc_state_changed", (event) => {
  const { npc_name, behaviour } = event.payload as { npc_name: string; behaviour: string };
  console.log(`${npc_name} is now ${behaviour}`);
});

nexus.realtime.on("*", (event) => {
  console.log("Event:", event.type); // fires for every event type
});

await nexus.realtime.connect(session.id);

// ... interact with NPCs, join/leave players — events stream to your handlers ...

nexus.realtime.disconnect();
```

Handlers are plain functions taking one `NexusEvent` argument — no async
required, though your handler body can be async if you don't need the SDK
to await it. Multiple handlers can be registered per event type; all are
called in registration order. The SDK handles the connection's auth
handshake and ping/pong heartbeat automatically — you only write handler
logic.

`nexus.close()` automatically disconnects any open realtime connection.

`connect()` returns a `Promise<void>` that resolves once the server confirms
the connection (the `"connected"` frame) and rejects if authentication fails
(close code `4001`) or the session is invalid (close code `4002`):

```typescript
try {
  await nexus.realtime.connect(session.id);
  console.log("Connected!");
} catch (err) {
  if (err instanceof NexusError) {
    console.error("Connection failed:", err.message, err.code);
  }
}
```

---

## Error Handling

Every SDK method throws a single `NexusError` class on failure — never a raw
`Response`, never an untyped object.

```typescript
import { NexusClient, NexusError } from "nexus-js";

const nexus = new NexusClient({ host: "localhost:8000" });

try {
  await nexus.auth.login("alice", "wrong-password");
} catch (err) {
  if (err instanceof NexusError) {
    console.log(`Auth failed: ${err.message} (code=${err.code})`);
    // e.g. "Invalid username or password." (code="INVALID_CREDENTIALS")
    // or "Account locked..." (code="ACCOUNT_LOCKED") after 5 failures
  }
}

try {
  await nexus.sessions.join(fullSessionId);
} catch (err) {
  if (err instanceof NexusError) {
    console.log(`Could not join: ${err.message}`); // "Session is full." etc.
  }
}

try {
  await nexus.npcs.get("00000000-0000-0000-0000-000000000000");
} catch (err) {
  if (err instanceof NexusError) {
    console.log(`NPC error: ${err.message}`); // "NPC not found." (code="NPC_NOT_FOUND")
  }
}
```

| Failure                                    | `err.code`                  |
|---------------------------------------------|------------------------------|
| Bad credentials                             | `INVALID_CREDENTIALS`       |
| Account locked (5 failed logins)            | `ACCOUNT_LOCKED`            |
| Missing/expired/revoked access token        | `INVALID_TOKEN` / `TOKEN_EXPIRED` / `TOKEN_REVOKED` |
| Session full                                | `SESSION_FULL`              |
| Already a member of the session             | `ALREADY_IN_SESSION`        |
| Session already ended                       | `SESSION_ENDED`             |
| NPC not found                               | `NPC_NOT_FOUND`             |
| WebSocket auth handshake failed             | `WS_AUTH_FAILED`            |
| WebSocket session invalid/not found         | `WS_SESSION_INVALID`        |
| Anything else (validation errors, 5xx, etc.) | may be `undefined`         |

`NexusError` is a real `Error` subclass — `err instanceof Error` is also
true, and `err.message`/`err.stack` behave normally for logging.

---

## Development

```bash
cd sdk/javascript
npm install
npm run build       # compiles src/ → dist/ with tsc, zero errors required
npm test            # runs the vitest suite once
npm run test:watch  # runs vitest in watch mode
```

## License

MIT
