<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0D1117,40:0a0a1a,80:0f1a2e,100:162040&height=250&section=header&text=NEXUS&fontSize=90&fontColor=4fa3e0&fontAlignY=45&desc=AI-Native%20Game%20Backend%20Platform&descAlignY=63&descColor=6e8aad&fontStyle=bold" />

<br/>

<a href="#">
  <img src="https://img.shields.io/badge/%F0%9F%94%A8%20Status-Actively%20Building-FFB300?style=for-the-badge&labelColor=0D1117" />
</a>
&nbsp;
<a href="#">
  <img src="https://img.shields.io/badge/Phase-1%20%E2%80%94%20Foundation-4fa3e0?style=for-the-badge&labelColor=0D1117" />
</a>
&nbsp;
<a href="#">
  <img src="https://img.shields.io/badge/Stack-Python%20%C2%B7%20FastAPI%20%C2%B7%20React-58a6ff?style=for-the-badge&labelColor=0D1117" />
</a>
&nbsp;
<a href="#">
  <img src="https://img.shields.io/badge/License-MIT-00C853?style=for-the-badge&labelColor=0D1117" />
</a>

<br/><br/>

<img src="https://img.shields.io/badge/building%20in%20public-%E2%9C%94-58a6ff?style=flat-square&labelColor=0D1117" />
&nbsp;
<img src="https://img.shields.io/badge/watch%20this%20repo%20to%20follow%20progress-%F0%9F%94%94-8b949e?style=flat-square&labelColor=0D1117" />

<br/><br/>

<blockquote>
<strong>The backend platform that gives every game an AI brain.</strong><br/>
Multiplayer infrastructure + stateful AI NPC service — managed, scalable, and developer-first.
</blockquote>

<br/>

[The Problem](#-the-problem) · [What is Nexus](#-what-is-nexus) · [Features](#-platform-features) · [Architecture](#-architecture) · [SDK](#-developer-sdk) · [Roadmap](#-roadmap) · [Echoes of Truth](#-echoes-of-truth)

</div>

---

## ⚠️ Build Status

> **Nexus is currently being actively built.** This README is the blueprint — the vision document that drives development. Code is being written, architecture is being validated, and the platform is taking shape.
>
> This repo is public intentionally. Building in public keeps me accountable, attracts early collaborators, and lets game developers follow along and give input before launch.
>
> **Star ⭐ and Watch 👁️ to follow the journey.**

| Phase | Status | Description |
|---|---|---|
| Phase 1 — Foundation | ✅ **Complete** | API design, FastAPI skeleton, DB schema, WebSocket server |
| Phase 2 — NPC Service | ✅ **Complete** | Personality engine, memory layer, emotional state, LLM integration |
| Phase 3 — SDK & DX | ✅ **Complete** | Python + JS SDKs, developer dashboard, full API docs |
| Phase 4 — Echoes of Truth | 🔨 **In Progress** | Flagship game built entirely on Nexus as proof-of-concept |
| Phase 5 — Public Launch | 📋 Planned | Open access, usage-based pricing, YC Startup School |

---

## 🔥 The Problem

Building a multiplayer game with AI characters in 2026 means stitching together at least **five separate systems** that were never designed to talk to each other:

```
What you actually need:          What you end up building:
──────────────────────           ──────────────────────────────────────────
Multiplayer sessions      →      AWS GameLift (complex, expensive, AWS lock-in)
AI NPCs                   →      Raw OpenAI API calls (stateless, no game context)
Real-time sync            →      Custom WebSocket server (fragile, hard to scale)
Player auth               →      Roll your own JWT system (security minefield)
Game analytics            →      Another third-party service (yet another SDK)
Anti-cheat                →      Either SentinelX or nothing
```

And the worst part: **the AI layer and the game layer never talk to each other.** Your NPC doesn't know what the player just did. It doesn't remember what was said five minutes ago. Every message is a fresh API call with no context — just a prompt you manually crafted and hoped for the best.

The result is NPCs that feel hollow. Players ask a question, the NPC answers, but it doesn't *feel* like talking to a real character. It feels like talking to ChatGPT wearing a costume.

**This is the exact problem Nexus is built to solve.**

---

## 🧠 What is Nexus?

Nexus is an **AI-native game backend platform** — a single managed service that handles everything a modern multiplayer game needs, with AI as a first-class citizen, not an afterthought.

The key word is **AI-native**. Other backend platforms (GameLift, Photon, PlayFab) were built for traditional multiplayer games and added AI integrations later. Nexus is designed from day one around the idea that **every game session will have intelligent, stateful NPCs** — and the entire infrastructure is built to support that.

```
┌──────────────────────────────────────────────────┐
│                   Your Game                      │
│              (One SDK · One API)                 │
└──────────────────────┬───────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │         NEXUS             │
         │                           │
         │  Sessions  ←→  NPC AI     │
         │     ↕              ↕      │
         │  Realtime  ←→  Analytics  │
         │                           │
         │  Auth · Anti-Cheat · SDK  │
         └───────────────────────────┘
```

Everything shares the same session context. Your NPC knows what's happening in the game because Nexus feeds it that context automatically. No manual prompt engineering. No stateless API calls. No stitching together five different services.

---

## ✨ Platform Features

### 🎮 1. Multiplayer Session Management

The core primitive that everything else in Nexus is built on. A **Session** is a live game instance — it has players, state, NPCs, and a lifecycle (created → active → ended). Nexus manages all of it.

**What Nexus handles automatically:**
- Session creation with configurable parameters (max players, region, game mode, NPC roster)
- Player join / leave events with callbacks
- Session state persistence — resume from any point
- Graceful teardown with automatic state archiving
- Region-aware routing — players connect to the nearest session host
- Session locking — prevents joins after game-critical moments

```python
import nexus

# Create a session with NPCs pre-configured
session = await nexus.sessions.create(
    game_id="your-game-id",
    config={
        "mode": "interrogation",
        "max_players": 4,
        "region": "ap-south-1",
        "npcs": ["marcus_webb", "detective_lena"],
        "difficulty": "adaptive"
    }
)

print(session.id)           # "sess_8f3a2b..."
print(session.join_code)    # "NEXUS-7742"

# Player joins via code
await nexus.sessions.join(session.id, player_id="player_001")

# Listen to session events
@nexus.sessions.on("player_joined")
async def on_join(event):
    print(f"{event.player_id} joined session {event.session_id}")
```

---

### 🤖 2. AI NPC Service — The Heart of Nexus

This is what makes Nexus fundamentally different from every other game backend. Nexus NPCs are not chatbots. They are **stateful AI agents** with:

- A **personality profile** — core traits, values, fears, motivations
- A **secret layer** — information the NPC holds, with thresholds for revealing it
- A **memory system** — every player interaction is remembered and influences future responses
- An **emotional state engine** — stress, trust, suspicion, and confidence that shift dynamically during a session
- **Game context awareness** — the NPC always knows the current game state (evidence found, time elapsed, player actions)

**Why this matters — the difference in practice:**

| Scenario | Raw OpenAI API | Nexus NPC Service |
|---|---|---|
| Player accuses NPC of lying | Generic denial | NPC recalls the specific lie from 3 exchanges ago, defensive response adjusted to current stress level |
| Player finds new evidence | You manually re-inject context into every call | Nexus automatically feeds new evidence into NPC context |
| Player leaves and comes back | NPC has no memory | NPC remembers everything, picks up exactly where it left off |
| NPC under sustained pressure | Flat responses | Stress accumulates, tells emerge, story starts to crack |
| Multiple players talking to same NPC | Inconsistent across calls | Single consistent NPC state shared across all players |
| Cost | Pay full token price every message | Context cached, only deltas sent — dramatically cheaper |

```python
# Define a fully-featured NPC
npc = await nexus.npcs.create(
    name="Marcus Webb",
    session_id=session.id,
    personality={
        "traits": ["calculated", "defensive", "intelligent"],
        "motivation": "protect his brother at any cost",
        "fear": "being exposed before his lawyer arrives",
        "tells": {
            "under_high_stress": "references his alibi unprompted",
            "near_confession": "asks about witness protection"
        }
    },
    secrets=[
        {
            "id": "alibi_weakness",
            "content": "He was not at the restaurant — he was at the warehouse",
            "reveal_threshold": 0.85,       # only reveals under extreme pressure
            "reveal_trigger": "direct confrontation with CCTV evidence"
        },
        {
            "id": "brothers_involvement",
            "content": "His brother drove the getaway car",
            "reveal_threshold": 0.95,
            "reveal_trigger": "player mentions his brother by name"
        }
    ],
    initial_state={
        "stress": 0.2,
        "trust": 0.1,
        "suspicion": 0.6,
        "cooperation": 0.3
    },
    memory_scope="persistent"    # survives across multiple sessions
)

# Interact — Nexus handles memory, context, and emotional drift automatically
response = await nexus.npcs.interact(
    npc_id=npc.id,
    player_id="player_001",
    message="We have you on CCTV three blocks from the warehouse at 11:42 PM."
)

print(response.text)           # NPC's in-character reply
print(response.state_delta)    # { "stress": +0.18, "trust": -0.05 }
print(response.behaviour)      # "deflecting" | "nervous" | "hostile" | "confessing"
print(response.secret_leaked)  # None | "alibi_weakness"
```

**Emotional state drift — how it works:**

```
Session Start                                    Session End
     │                                                │
stress: 0.2 ──────────────────────────────► stress: 0.91
     │                                                │
     ├─ Player finds evidence     (+0.15 stress)      │
     ├─ Player bluffs badly       (-0.08 stress)      │
     ├─ Player names accomplice   (+0.22 stress)      │
     ├─ Lawyer mention (anchor)   (+0.12 stress)      │
     └─ Direct CCTV confrontation (+0.20 stress)      │
                                                      │
                                             CONFESSION THRESHOLD
                                             reached at 0.85 stress
```

---

### ⚡ 3. Real-Time WebSocket Infrastructure

Every Nexus session has a managed WebSocket room. Players, NPCs, and the game server all communicate through it — Nexus handles connection pooling, reconnection, delivery guarantees, and message ordering.

**You never write WebSocket boilerplate again.**

```python
# Server → broadcast NPC state change to all players in session
await nexus.realtime.broadcast(
    session_id=session.id,
    event="npc_behaviour_changed",
    payload={
        "npc_id": npc.id,
        "new_behaviour": "nervous",
        "stress_level": 0.74,
        "visible_tell": "references alibi unprompted"
    }
)

# Server → send to specific player only
await nexus.realtime.send(
    session_id=session.id,
    player_id="player_001",
    event="private_tip",
    payload={"message": "He flinched when you mentioned the warehouse."}
)

# Client-side (JavaScript SDK)
nexus.on("npc_behaviour_changed", ({ npc_id, new_behaviour, visible_tell }) => {
    updateNPCPortrait(npc_id, new_behaviour);
    showPlayerHint(visible_tell);
});
```

**Reliability guarantees:**
- Messages delivered in order within a session
- Automatic reconnection with state replay on disconnect
- Heartbeat-based connection health monitoring
- Dead session cleanup after configurable timeout

---

### 🧩 4. AI-Powered Matchmaking

Traditional matchmaking is ELO and ping. Nexus matchmaking adds a **play style dimension** — so players are matched not just by skill, but by how they play, creating sessions where the dynamic between players makes the game better.

```python
await nexus.matchmaking.queue(
    player_id="player_001",
    game_id="echoes-of-truth",
    preferences={
        "skill_bracket": "intermediate",
        "play_style": "methodical",        # aggressive | methodical | social | explorer
        "npc_difficulty": "adaptive",      # easy | medium | hard | adaptive
        "session_length": "short",         # short | medium | long
        "region_preference": "ap-south-1"
    }
)

# Nexus fires a webhook when a match is found
@nexus.matchmaking.on("match_found")
async def on_match(event):
    print(event.session_id)      # ready-to-join session
    print(event.matched_players) # who you're playing with
    print(event.npc_roster)      # which NPCs are in this session
```

**Matchmaking algorithm factors:**
- ELO-equivalent skill rating per game mode
- Play style compatibility scoring
- Session history (avoid rematching same group too soon)
- NPC difficulty calibration per skill level
- Geographic latency optimisation

---

### 📊 5. Behavioural Analytics & Game Intelligence

Every player action, NPC interaction, game event, and session outcome is automatically captured. Nexus surfaces insights you would never think to instrument manually — because it understands the game structure, not just raw events.

**What the dashboard shows:**

```
Session Heatmaps
  Where do players spend most of their time?
  Which questions do they ask first vs. last?
  Where do sessions typically break down?

NPC Interaction Funnels
  Which dialogue paths lead to confession?
  Which questions players never think to ask?
  At what stress level do NPCs typically crack?

Player Progression
  Win rate by play style
  Average session length by difficulty
  Most common failure patterns

AI Performance Metrics
  NPC response latency (p50 / p95 / p99)
  Coherence score per NPC over time
  Memory retrieval accuracy
  Emotional drift distribution

Custom Events
  Track anything with one line
```

```python
# Track any custom game event
await nexus.analytics.track(
    session_id=session.id,
    player_id="player_001",
    event="player_used_bluff",
    properties={
        "target_npc": npc.id,
        "bluff_type": "false_evidence",
        "npc_response": "believed",
        "game_time_seconds": 342
    }
)
```

---

### 🔒 6. Player Auth & Identity

Production-grade authentication with zero setup. Nexus manages player accounts, sessions, and identity so you don't have to build it or worry about getting it wrong.

**Features:**
- JWT access tokens (15-minute expiry) + refresh token rotation
- bcrypt password hashing (cost-12)
- Account lockout after failed attempts
- Guest play support (anonymous sessions with optional upgrade to full account)
- Per-game player profiles (separate identity per game you build on Nexus)
- Webhook on login/logout for your game to react to

```python
# Register a player
player = await nexus.auth.register(
    username="vishwajeet",
    email="v@example.com",
    password="SecurePass123!"
)

# Authenticate
token = await nexus.auth.login(username="vishwajeet", password="SecurePass123!")

# Verify token in your game middleware
player = await nexus.auth.verify(token.access_token)
print(player.id, player.username, player.game_profile)
```

---

### 🛡️ 7. Anti-Cheat Integration (via SentinelX)

Nexus natively integrates with **[SentinelX](https://github.com/Vishwajeet2005/SentinelX)** — an open-source enterprise anti-cheat system built alongside Nexus. One configuration flag enables telemetry collection, ML-based anomaly detection (speedhacks, aim-snapping), and a live SOC dashboard for your game.

```python
# In your Nexus project config
nexus_config = {
    "anti_cheat": {
        "enabled": True,
        "provider": "sentinelx",
        "sensitivity": "medium",        # low | medium | high | paranoid
        "auto_action": "flag",          # flag | warn | kick | ban
        "alert_webhook": "https://your-game.com/webhooks/cheat-detected"
    }
}
```

When a player is flagged, Nexus fires a webhook to your game with full context — player ID, session ID, anomaly type, confidence score, and a link to the SentinelX SOC dashboard for manual review.

---

## 🏗️ Architecture

```
                        ┌───────────────────────────────┐
                        │         Game Clients          │
                        │  Web · Desktop · Mobile · UE5 │
                        │     (Nexus SDK per platform)  │
                        └───────────────┬───────────────┘
                                        │
                           HTTPS + WebSocket (WSS)
                                        │
              ┌─────────────────────────▼──────────────────────────┐
              │                  API Gateway                       │
              │   FastAPI · JWT Auth · Rate Limiting · CORS        │
              └──────┬──────────┬───────────────┬──────────────────┘
                     │          │               │
         ┌───────────▼──┐  ┌────▼──────┐  ┌────▼──────────────┐
         │   Session    │  │    NPC    │  │    Realtime        │
         │   Service    │  │  Service  │  │    WS Server       │
         │              │  │           │  │                    │
         │ Create/Join  │  │ Stateful  │  │ Session rooms      │
         │ State mgmt   │  │ agents    │  │ Event broadcast    │
         │ Lifecycle    │  │ Memory    │  │ Reconnect logic    │
         │ Matchmaking  │  │ Emotion   │  │ Message ordering   │
         └──────┬───────┘  └────┬──────┘  └────────────────────┘
                │               │
         ┌──────▼───────────────▼──────────────────────────────┐
         │                   Data Layer                        │
         │                                                     │
         │  PostgreSQL          Redis               Event Log  │
         │  (persistent         (session state,    (analytics  │
         │   player data,        NPC memory         pipeline)  │
         │   session archive)    hot cache)                    │
         └─────────────────────────┬───────────────────────────┘
                                   │
         ┌─────────────────────────▼───────────────────────────┐
         │               Analytics Pipeline                    │
         │   Event ingestion · Dashboard API · Alerts          │
         └─────────────────────────────────────────────────────┘
                                   │
         ┌─────────────────────────▼───────────────────────────┐
         │             Developer Dashboard (React)             │
         │   Session monitor · NPC stats · Player analytics    │
         │   API key management · Webhook config · Billing     │
         └─────────────────────────────────────────────────────┘
```

**Technology decisions and why:**

| Choice | Technology | Reason |
|---|---|---|
| API framework | Python / FastAPI | Async-first, WebSocket support, Pydantic validation, fast iteration |
| Database | PostgreSQL | Relational integrity for sessions + players, JSONB for flexible NPC state |
| Cache / Pub-Sub | Redis | Session state hot cache, WebSocket pub-sub across server instances |
| AI provider | Provider-agnostic (OpenAI / Groq / Anthropic) | No vendor lock-in, swap models without changing game code |
| Frontend | React + Tailwind | Fast dashboard development |
| Deployment | Docker + Docker Compose | Consistent local dev, easy production deploy |

---

## 🔧 Developer SDK

Nexus will ship official SDKs for the most common game environments. The design goal: a developer should be able to create their first NPC-powered session in **under 10 minutes** from first `pip install`.

| SDK | Language | Environments | Status |
|---|---|---|---|
| `nexus-py` | Python | FastAPI, Django, scripts | ✅ Complete |
| `nexus-js` | JavaScript / TypeScript | Browser, Node.js, Vite | ✅ Complete |
| `nexus-cpp` | C++ | Unreal Engine 5, native | 📋 Planned |
| `nexus-cs` | C# | Unity, .NET | 📋 Planned |

**SDK design principles:**
- Every method is `async` — no blocking calls in game loops
- Strongly typed (TypeScript types, Python type hints) — IDE autocomplete everywhere
- Sensible defaults — the minimum viable call should work out of the box
- Explicit errors — no silent failures, every exception is descriptive
- Offline mode — SDK works with a local Nexus instance for development

---

## 🕵️ Echoes of Truth

**Echoes of Truth** is the game being built on top of Nexus — its purpose is to prove that the platform works by being a real, shippable product built entirely on it.

An AI interrogation game. Players question a suspect whose story, emotional state, memory, and behavior adapt dynamically based on how the interrogation unfolds. The suspect is not scripted — they run on the Nexus NPC service with a full personality, a set of secrets with reveal thresholds, and accumulated stress across the session.

**Every feature used in Echoes of Truth is a Nexus feature being battle-tested:**

| Game Feature | Nexus Feature Used |
|---|---|
| Suspect's changing behaviour | NPC emotional state engine |
| Suspect remembers your accusations | NPC memory system |
| Multiple suspects per session | Multi-NPC session management |
| Evidence updates suspect's responses | Real-time game context injection |
| Multiplayer co-interrogation | Session management + WebSocket sync |
| Case replay after session | Session state persistence + analytics |
| Leaderboards | Analytics pipeline |

Echoes of Truth is the answer to the question every developer will ask: *"Does Nexus actually work?"*

→ **[Echoes of Truth Repository](#)** *(coming soon)*

---

## 🗺️ Roadmap

```
PHASE 1 — Foundation                              ✅ COMPLETE
────────────────────────────────────────────────────────────────
 ✅  Architecture design & system diagram
 ✅  API contract design (sessions, NPC, auth, realtime)
 ✅  Database schema design (PostgreSQL)
 ✅  FastAPI project skeleton + middleware
 ✅  PostgreSQL integration + migrations (Alembic)
 ✅  Redis integration (session cache + pub-sub)
 ✅  WebSocket server — session rooms + event broadcasting
 ✅  Basic session CRUD endpoints
 ✅  Player auth endpoints (register, login, refresh, logout)
 ✅  Docker + docker-compose dev environment


PHASE 2 — NPC Service                             ✅ COMPLETE
────────────────────────────────────────────────────────────────
 ✅  NPC personality profile schema (Pydantic models)
 ✅  NPC memory persistence layer (PostgreSQL + Redis cache)
 ✅  Emotional state engine (stress, trust, suspicion drift)
 ✅  LLM integration layer (provider-agnostic abstraction)
 ✅  Automatic game context injection pipeline
 ✅  Secret reveal threshold system
 ✅  NPC behaviour classification (deflecting, nervous, confessing...)
 ✅  Multi-NPC session support (multiple agents, shared context)


PHASE 3 — SDK & Developer Experience             ✅ COMPLETE
────────────────────────────────────────────────────────────────
 ✅  nexus-py SDK (pip installable)
 ✅  nexus-js SDK (npm installable)
 ✅  Developer dashboard — React frontend
         └── Session monitor
         └── NPC state visualiser
         └── Analytics dashboard
         └── API key management
         └── Webhook configuration
 ✅  Full API documentation (auto-generated)
 ✅  Local development mode (run full Nexus stack locally)
 📋  SDK quickstart — first NPC session in < 10 minutes


PHASE 4 — Echoes of Truth                        🔨 IN PROGRESS
────────────────────────────────────────────────────────────────
 📋  Game design document finalised
 📋  Core interrogation loop (React frontend + Nexus backend)
 📋  First NPC: Marcus Webb (full personality + secrets)
 📋  Evidence system (feeds into NPC context automatically)
 📋  Closed alpha (friends + early followers)
 📋  Public demo deployed


PHASE 5 — Platform Launch                        📋 FUTURE
────────────────────────────────────────────────────────────────
 📋  Public API access (open signups)
 📋  Usage-based pricing model
 📋  nexus-cpp SDK (Unreal Engine 5)
 📋  nexus-cs SDK (Unity)
 📋  YC Startup School application
 📋  First external game built on Nexus (not Echoes of Truth)
```

---

## 🧰 Full Tech Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| API | Python + FastAPI | 3.12 / 0.110+ | Core platform backend, async endpoints |
| Validation | Pydantic v2 | 2.x | Request/response models, NPC schema |
| Realtime | WebSockets + Redis Pub-Sub | — | Live game events, cross-instance messaging |
| Database | PostgreSQL | 16 | Sessions, players, NPC state, event log |
| Cache | Redis | 7 | Session hot state, NPC memory cache, matchmaking queue |
| Migrations | Alembic | — | Database schema versioning |
| AI / LLM | Provider-agnostic | — | OpenAI / Groq / Anthropic (swappable) |
| Dashboard | React + Tailwind CSS | 18 / 3.x | Developer control panel |
| Containerisation | Docker + Docker Compose | — | Local dev + production deployment |
| CI/CD | GitHub Actions | — | Automated testing + deployment |

---

## 📂 Planned Project Structure

```
nexus/
│
├── api/                          # FastAPI application
│   ├── main.py                   # App entry point
│   ├── config.py                 # Environment config
│   ├── dependencies.py           # Shared FastAPI dependencies
│   │
│   ├── routers/
│   │   ├── sessions.py           # Session CRUD + lifecycle
│   │   ├── npcs.py               # NPC create, interact, state
│   │   ├── realtime.py           # WebSocket endpoints
│   │   ├── matchmaking.py        # Queue, match, dequeue
│   │   ├── auth.py               # Register, login, refresh
│   │   └── analytics.py          # Event tracking, dashboard data
│   │
│   ├── models/
│   │   ├── session.py            # SQLAlchemy session model
│   │   ├── player.py             # Player + auth model
│   │   ├── npc.py                # NPC + personality + memory
│   │   └── event.py              # Analytics event model
│   │
│   ├── schemas/
│   │   ├── session.py            # Pydantic request/response schemas
│   │   ├── npc.py                # NPC schemas (personality, secrets, state)
│   │   └── auth.py               # Auth schemas
│   │
│   └── services/
│       ├── session_service.py    # Session business logic
│       ├── npc_service.py        # NPC state machine + LLM orchestration
│       ├── memory_service.py     # NPC memory read/write
│       ├── emotion_service.py    # Emotional state drift engine
│       ├── matchmaking_service.py
│       ├── realtime_service.py   # WebSocket room management
│       └── analytics_service.py
│
├── sdk/
│   ├── python/                   # nexus-py SDK
│   └── javascript/               # nexus-js SDK
│
├── dashboard/                    # React developer dashboard
│   └── src/
│       ├── pages/
│       │   ├── Sessions.tsx
│       │   ├── NPCs.tsx
│       │   ├── Analytics.tsx
│       │   └── Settings.tsx
│       └── components/
│
├── migrations/                   # Alembic DB migrations
├── tests/                        # Pytest test suite
├── docker-compose.yml            # Full local stack
├── docker-compose.prod.yml       # Production config
└── README.md
```

---

## 🤝 Building in Public

Nexus is being built entirely in public. Every architectural decision, every tradeoff, every mistake — it will all be visible in the commit history.

If you're a **game developer** who would actually use this — open an issue and tell me what you need. Your feedback before launch is worth more than any feature I could build in isolation.

If you're a **backend / AI engineer** who wants to contribute — watch the repo. Contribution guide will be up with Phase 1 completion.

```bash
# Get the code when it's ready
git clone https://github.com/Vishwajeet2005/nexus
cd nexus

# Full local stack (one command)
docker-compose up --build

# API will be at   → http://localhost:8000
# Dashboard at     → http://localhost:3000
# API Docs at      → http://localhost:8000/docs
```

---

## 📫 Contact

Built by **[Vishwajeet Vikram Borade](https://github.com/Vishwajeet2005)** · India 🇮🇳

Game developer who wants early access → open an issue.
Want to collaborate or give feedback → open an issue.
Found a flaw in the architecture → please, open an issue.

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:162040,50:0f1a2e,100:0D1117&height=140&section=footer" />

<sub>
  <strong>Nexus</strong> · AI-Native Game Backend Platform · Building in public from India 🇮🇳<br/>
  Star ⭐ to follow progress · Watch 👁️ to get notified
</sub>

</div>
