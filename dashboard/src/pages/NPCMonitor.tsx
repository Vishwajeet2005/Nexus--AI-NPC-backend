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
  { key: "stress",      label: "Stress",      colour: "bg-status-red"    },
  { key: "trust",       label: "Trust",       colour: "bg-status-green"  },
  { key: "suspicion",   label: "Suspicion",   colour: "bg-status-yellow" },
  { key: "cooperation", label: "Cooperation", colour: "bg-accent"        },
];

export default function NPCMonitor() {
  const { sessionId, npcId } = useParams<{ sessionId: string; npcId: string }>();
  const [npc, setNpc]             = useState<NPC | null>(null);
  const [state, setState]         = useState<EmotionalState | null>(null);
  const [behaviour, setBehaviour] = useState<NPCBehaviour>("cooperative");
  const [memory, setMemory]       = useState<MemoryEntry[]>([]);
  const [loading, setLoading]     = useState(true);
  const [selectedNpcId, setSelectedNpcId] = useState<string | null>(npcId ?? null);
  const [sessionNpcs, setSessionNpcs]     = useState<NPC[]>([]);

  const { connected, lastNpcUpdate } = useNexusWS(sessionId ?? null);

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

  useEffect(() => {
    if (!lastNpcUpdate || lastNpcUpdate.npc_id !== selectedNpcId) return;
    setState(lastNpcUpdate.emotional_state);
    setBehaviour(lastNpcUpdate.behaviour);
  }, [lastNpcUpdate, selectedNpcId]);

  if (!sessionId) {
    return (
      <div className="p-6 text-tx-muted text-sm">
        Navigate to a session first: <code className="font-mono text-accent">/sessions/[id]/npc-monitor</code>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-tx-primary">NPC Monitor</h1>
          <p className="text-tx-muted text-xs mt-0.5 font-mono">Session {sessionId.slice(0, 8)}…</p>
        </div>
        <LiveIndicator live={connected} />
      </div>

      {/* NPC selector */}
      {sessionNpcs.length > 1 && (
        <div className="flex gap-1.5 mb-5 flex-wrap p-1 bg-surface-raised border border-border rounded-lg w-fit">
          {sessionNpcs.map((n) => (
            <button
              key={n.id}
              onClick={() => setSelectedNpcId(n.id)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                selectedNpcId === n.id
                  ? "bg-surface-overlay text-tx-primary shadow-sm"
                  : "text-tx-muted hover:text-tx-secondary"
              }`}
            >
              {n.name}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 bg-surface-raised border border-border rounded-card animate-pulse" />
          ))}
        </div>
      ) : !npc ? (
        <div className="flex flex-col items-center justify-center py-24 text-tx-muted gap-2">
          <p className="text-sm">No NPCs found in this session.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Left: state panel */}
          <div className="space-y-4">
            <div className="card p-5">
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h2 className="font-semibold text-tx-primary">{npc.name}</h2>
                  <p className="text-tx-muted text-xs mt-0.5">Emotional State</p>
                </div>
                <BehaviourBadge behaviour={behaviour} />
              </div>
              <div className="space-y-4">
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
              <div className="bg-status-red/10 border border-status-red/20 rounded-card p-4 text-sm text-status-red">
                <span className="font-medium">Secret revealed:</span> {lastNpcUpdate.secret_leaked}
              </div>
            )}

            <div className="card p-4">
              <p className="text-xs font-medium text-tx-muted mb-2">Raw State</p>
              <pre className="text-xs text-status-green font-mono whitespace-pre-wrap overflow-auto max-h-40">
                {JSON.stringify(state, null, 2)}
              </pre>
            </div>
          </div>

          {/* Right: memory log */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-tx-primary">Interaction History</h2>
              <span className="text-tx-muted text-xs">{memory.length} entries</span>
            </div>
            <MemoryLog entries={memory} />
          </div>
        </div>
      )}
    </div>
  );
}
