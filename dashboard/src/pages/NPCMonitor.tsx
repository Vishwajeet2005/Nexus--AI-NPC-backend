import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/nexus";
import type { EmotionalState, MemoryEntry, NPC, NPCBehaviour } from "../api/nexus";
import { BehaviourBadge } from "../components/BehaviourBadge";
import { EmotionBar } from "../components/EmotionBar";
import { LiveIndicator } from "../components/LiveIndicator";
import { MemoryLog } from "../components/MemoryLog";
import { useNexusWS } from "../hooks/useNexusWS";

const EMOTION_BARS: Array<{ key: keyof EmotionalState; label: string; colour: string }> = [
  { key: "stress",      label: "Stress",      colour: "bg-nexus-red" },
  { key: "trust",       label: "Trust",       colour: "bg-nexus-green" },
  { key: "suspicion",   label: "Suspicion",   colour: "bg-nexus-yellow" },
  { key: "cooperation", label: "Cooperation", colour: "bg-nexus-accent" },
];

export default function NPCMonitor() {
  const { sessionId, npcId } = useParams<{ sessionId: string; npcId: string }>();
  const [npc, setNpc] = useState<NPC | null>(null);
  const [state, setState] = useState<EmotionalState | null>(null);
  const [behaviour, setBehaviour] = useState<NPCBehaviour>("cooperative");
  const [memory, setMemory] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNpcId, setSelectedNpcId] = useState<string | null>(npcId ?? null);
  const [sessionNpcs, setSessionNpcs] = useState<NPC[]>([]);

  const { connected, lastNpcUpdate } = useNexusWS(sessionId ?? null);

  // Load session NPCs for selector
  useEffect(() => {
    if (!sessionId) return;
    api.npcs.listInSession(sessionId)
      .then((npcs) => {
        setSessionNpcs(npcs);
        if (!selectedNpcId && npcs.length > 0) {
          setSelectedNpcId(npcs[0]?.id ?? null);
        }
      })
      .catch(() => {});
  }, [sessionId, selectedNpcId]);

  // Load selected NPC
  useEffect(() => {
    if (!selectedNpcId) return;
    setLoading(true);
    Promise.all([
      api.npcs.get(selectedNpcId),
      api.npcs.getMemory(selectedNpcId, 20),
    ])
      .then(([npcData, memData]) => {
        setNpc(npcData);
        setState(npcData.current_emotional_state);
        setBehaviour(npcData.current_behaviour);
        setMemory(memData.entries);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedNpcId]);

  // Apply live WebSocket updates
  useEffect(() => {
    if (!lastNpcUpdate || lastNpcUpdate.npc_id !== selectedNpcId) return;
    setState(lastNpcUpdate.emotional_state);
    setBehaviour(lastNpcUpdate.behaviour);
  }, [lastNpcUpdate, selectedNpcId]);

  if (!sessionId) {
    return (
      <div className="p-6 text-nexus-muted font-mono">
        Navigate to a session first: <code>/sessions/[id]/npc-monitor</code>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">NPC Monitor</h1>
          <p className="text-nexus-muted text-xs font-mono mt-1">
            Session {sessionId.slice(0, 8)}…
          </p>
        </div>
        <LiveIndicator live={connected} />
      </div>

      {/* NPC selector */}
      {sessionNpcs.length > 1 && (
        <div className="flex gap-2 mb-6 flex-wrap">
          {sessionNpcs.map((n) => (
            <button
              key={n.id}
              onClick={() => setSelectedNpcId(n.id)}
              className={`px-3 py-1 rounded text-sm font-mono transition-colors ${
                selectedNpcId === n.id
                  ? "bg-nexus-accent text-white"
                  : "bg-nexus-surface border border-nexus-border text-nexus-muted hover:border-nexus-accent"
              }`}
            >
              {n.name}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 bg-nexus-surface border border-nexus-border rounded-xl animate-pulse" />
          ))}
        </div>
      ) : !npc ? (
        <div className="text-nexus-muted font-mono text-center py-20">
          No NPCs found in this session.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: state panel */}
          <div className="space-y-4">
            <div className="bg-nexus-surface border border-nexus-border rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-white font-semibold">{npc.name}</h2>
                <BehaviourBadge behaviour={behaviour} />
              </div>
              <div className="space-y-3">
                {EMOTION_BARS.map(({ key, label, colour }) => (
                  <EmotionBar
                    key={key}
                    label={label}
                    value={state?.[key] ?? 0}
                    colour={colour}
                  />
                ))}
              </div>
            </div>

            {lastNpcUpdate?.secret_leaked && (
              <div className="bg-nexus-red/10 border border-nexus-red/30 rounded-xl p-4 font-mono text-sm text-nexus-red">
                🔓 Secret revealed: <strong>{lastNpcUpdate.secret_leaked}</strong>
              </div>
            )}

            <div className="bg-nexus-surface border border-nexus-border rounded-xl p-4">
              <p className="text-nexus-muted text-xs font-mono mb-2">RAW STATE</p>
              <pre className="text-xs text-nexus-green font-mono whitespace-pre-wrap">
                {JSON.stringify(state, null, 2)}
              </pre>
            </div>
          </div>

          {/* Right: memory log */}
          <div className="bg-nexus-surface border border-nexus-border rounded-xl p-5">
            <h2 className="text-white font-semibold mb-4">
              Interaction History
              <span className="ml-2 text-nexus-muted text-xs font-mono">({memory.length})</span>
            </h2>
            <MemoryLog entries={memory} />
          </div>
        </div>
      )}
    </div>
  );
}
