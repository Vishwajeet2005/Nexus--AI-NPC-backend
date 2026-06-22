# nexus-py

Python SDK for the Nexus AI-native game backend — async, fully typed with Pydantic, zero raw dicts.

---

## Installation

```bash
pip install nexus-py
```

For local development against an editable Nexus checkout:

```bash
pip install -e sdk/python
```

Requires Python 3.12+.

---

## Quick Start

```python
import asyncio
from nexus_py import NexusClient

async def main():
    async with NexusClient(host="localhost:8000") as nexus:
        await nexus.auth.login("dev", "password123")
        session = await nexus.sessions.create(game_id="your-game-id")
        npc = await nexus.npcs.create({
            "session_id": session.id,
            "name": "Marcus Webb",
            "personality": {
                "traits": ["calculated", "defensive"],
                "motivation": "Protect his brother",
                "fear": "Prison",
                "background": "Mid-level accountant for 15 years.",
                "speech_style": "Terse, precise.",
                "tells": {
                    "cooperative": "Leans back. Makes eye contact.",
                    "deflecting": "Answers a question with a question.",
                    "nervous": "Uses filler phrases.",
                    "hostile": "Goes monosyllabic.",
                },
            },
            "secrets": [],
        })
        response = await nexus.npcs.interact(npc.id, "Where were you on the 14th?")
        print(response.npc_response)
        print(response.behaviour)  # "deflecting"

asyncio.run(main())
```

That's the entire integration — no manual HTTP calls, no response parsing, no token bookkeeping.

---

## Authentication

`NexusClient.auth` exposes five methods. Any method returning a `TokenResponse`
automatically attaches the access token to all future requests made by this
client instance — you never manually set headers.

```python
# Register a new account (does not log in)
player = await nexus.auth.register(
    username="alice", email="alice@example.com", password="SecurePass123!"
)

# Log in — access token is now active on this client
tokens = await nexus.auth.login("alice", "SecurePass123!")

# Or skip registration entirely with an anonymous guest account
tokens = await nexus.auth.guest()

# Refresh before the access token expires (15 min default lifetime)
tokens = await nexus.auth.refresh()  # uses the stored refresh token
# or explicitly: await nexus.auth.refresh(tokens.refresh_token)

# Log out — blacklists both tokens server-side, clears local state
await nexus.auth.logout()
assert nexus.access_token is None
```

**Account lockout:** after 5 consecutive failed login attempts, the account
locks and `login()` raises `AuthError` even with the correct password
afterward. This mirrors the server's brute-force protection.

---

## Sessions

`NexusClient.sessions` manages multiplayer game session lifecycle.

```python
# Create a session
session = await nexus.sessions.create(
    game_id="game-uuid",
    config={"mode": "interrogation", "max_players": 4, "region": "us-east-1"},
)
print(session.join_code)  # "NEXUS-7742"

# A second player joins by UUID or by the human-readable code
await nexus.sessions.join(session.id)
await nexus.sessions.join_by_code("NEXUS-7742")

# Inspect current session state
session = await nexus.sessions.get(session.id)
players = await nexus.sessions.list_players(session.id)

# Merge game state (shallow merge — top-level keys overwrite, not deep merge)
session = await nexus.sessions.update_state(session.id, {"phase": "interrogation", "round": 2})

# Host-only actions
await nexus.sessions.lock(session.id)   # stop new players from joining
await nexus.sessions.end(session.id)    # permanently end the session

# Leave a session you're a member of
await nexus.sessions.leave(session.id)
```

---

## NPCs

`NexusClient.npcs` is the core gameplay surface — spawning NPCs and driving
conversations with them.

```python
# Spawn an NPC (full personality + secrets definition)
npc = await nexus.npcs.create({
    "session_id": session.id,
    "name": "Marcus Webb",
    "personality": {...},
    "secrets": [
        {
            "id": "alibi_weakness",
            "content": "Left the bar 105 minutes before he claims.",
            "reveal_threshold": 0.65,
            "reveal_trigger": "Player presents CCTV evidence.",
        }
    ],
    "initial_emotional_state": {"stress": 0.2, "trust": 0.4, "suspicion": 0.35, "cooperation": 0.55},
})

# Talk to the NPC
response = await nexus.npcs.interact(npc.id, "Where were you on the night of the 14th?")
print(response.npc_response)        # in-character reply
print(response.behaviour)           # "cooperative" | "deflecting" | "nervous" | "hostile" | "confessing"
print(response.emotional_state)     # NPCEmotionalState(stress=..., trust=..., ...)
print(response.secret_leaked)       # None, or the secret's id if revealed this turn

# Read interaction history (paginated, always from durable storage)
memory = await nexus.npcs.get_memory(npc.id, limit=20, offset=0)
for entry in memory.entries:
    print(entry.player_message, "→", entry.npc_response)

# List every NPC currently in a session
npcs = await nexus.npcs.list_in_session(session.id)
```

**On LLM failure:** `interact()` always returns HTTP 200, even if the
server's internal LLM call times out. Check `response.state_delta` — if
every field is `0.0`, the server returned a graceful fallback and the NPC's
emotional state did not change. This is not an SDK-level error; secret
revelation and state drift are guaranteed consistent.

---

## Real-Time Events

`NexusClient.realtime` is a WebSocket-based event emitter for live session
updates — player joins/leaves, session state changes, and NPC behaviour
shifts — without polling.

```python
async def on_npc_changed(event: dict) -> None:
    payload = event["payload"]
    print(f"{payload['npc_name']} is now {payload['behaviour']}")

async def on_any_event(event: dict) -> None:
    print("Event:", event["type"])

nexus.realtime.on("npc_state_changed", on_npc_changed)
nexus.realtime.on("*", on_any_event)  # fires for every event type

await nexus.realtime.connect(session.id)

# ... interact with NPCs, join/leave players — events stream to your handlers ...

await nexus.realtime.disconnect()
```

Handlers are `async def` functions taking one `dict` argument. Multiple
handlers can be registered per event type; all are awaited in registration
order. The SDK handles the connection's auth handshake and ping/pong
heartbeat automatically — you only write handler logic.

`NexusClient.close()` (and the `async with` context manager exit) automatically
disconnects any open realtime connection, so you don't need to call
`disconnect()` manually in typical usage.

---

## Error Handling

Every SDK method raises a typed exception from `nexus_py` instead of
returning `None` or a raw error dict. All exceptions inherit from `NexusError`.

```python
from nexus_py import NexusClient, AuthError, SessionError, NPCError, NexusError

async with NexusClient(host="localhost:8000") as nexus:
    try:
        await nexus.auth.login("alice", "wrong-password")
    except AuthError as e:
        print(f"Auth failed: {e.message} (code={e.code})")
        # e.g. "Invalid username or password." (code="INVALID_CREDENTIALS")
        # or "Account locked..." (code="ACCOUNT_LOCKED") after 5 failures

    try:
        await nexus.sessions.join(full_session_id)
    except SessionError as e:
        print(f"Could not join: {e.message}")  # "Session is full." etc.

    try:
        await nexus.npcs.get("00000000-0000-0000-0000-000000000000")
    except NPCError as e:
        print(f"NPC error: {e.message}")  # "NPC not found." (code="NPC_NOT_FOUND")

    try:
        await nexus.sessions.create(game_id="...")
    except NexusError as e:
        # Catch-all for anything not covered above (validation errors, 5xx, etc.)
        print(f"Unexpected error: {e.message}")
```

| Exception       | Raised on                                                        |
|-----------------|--------------------------------------------------------------------|
| `AuthError`     | 401 (bad/expired/missing/revoked token, wrong credentials), 423 (account locked) |
| `SessionError`  | 409 on session endpoints (full, already joined, ended, not a member) |
| `NPCError`      | 404 on `/npcs/*` endpoints                                        |
| `TimeoutError`  | The SDK's own HTTP request timed out client-side (default 30s)    |
| `NexusError`    | Base class; also raised directly for anything not in the above categories |

---

## Development

```bash
cd sdk/python
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
