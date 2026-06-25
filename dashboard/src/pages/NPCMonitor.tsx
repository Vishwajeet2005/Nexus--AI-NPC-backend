import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/nexus";
import type { EmotionalState, MemoryEntry, NPC, NPCBehaviour } from "../api/nexus";
import { BehaviourBadge } from "../components/BehaviourBadge";
import { EmotionBar } from "../components/EmotionBar";
import { LiveIndicator } from "../components/LiveIndicator";
import { MemoryLog } from "../components/MemoryLog";
import { useNexusWS } from "../hooks/useNexusWS";

const BARS: Array<{ key: keyof EmotionalState; label: string; colour: string }> = [
  { key: "stress",      label: "Stress",      colour: "bg-red"    },
  { key: "trust",       label: "Trust",       colour: "bg-green"  },
  { key: "suspicion",   label: "Suspicion",   colour: "bg-yellow" },
  { key: "cooperation", label: "Cooperation", colour: "bg-blue"   },
];

export default function NPCMonitor() {
  const { sessionId, npcId } = useParams<{ sessionId: string; npcId: string }>();
  const [npc, setNpc]         = useState<NPC | null>(null);
  const [state, setState]     = useState<EmotionalState | null>(null);
  const [behaviour, setBehaviour] = useState<NPCBehaviour>("cooperative");
  const [memory, setMemory]   = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNpcId, setSelectedNpcId] = useState<string | null>(npcId ?? null);
  const [sessionNpcs, setSessionNpcs]     = useState<NPC[]>([]);

  const { connected, lastNpcUpdate } = useNexusWS(sessionId ?? null);

  useEffect(() => {
    if (!sessionId) return;
    api.npcs.listInSession(sessionId)
      .then((npcs) => {
        setSessionNpcs(npcs);
        if (!selectedNpcId && npcs.length > 0) setSelectedNpcId(npcs[0]?.id ?? null);
      })
      .catch(() => {});
  }, [sessionId, selectedNpcId]);

  useEffect(() => {
    if (!selectedNpcId) return;
    setLoading(true);
    Promise.all([api.npcs.get(selectedNpcId), api.npcs.getMemory(selectedNpcId, 20)])
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
      <div className="p-6 text-xs text-ink-3">
        Navigate to a session first: <code className="font-mono text-blue">/sessions/[id]/npc-monitor</code>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="text-[15px] font-semibold text-ink">NPC Monitor</h1>
          <p className="text-xs text-ink-3 mt-0.5 font-mono">{sessionId.slice(0, 8)}…</p>
        </div>
        <LiveIndicator live={connected} />
      </div>

      <div className="px-6">
        {/* NPC tabs */}
        {sessionNpcs.length > 1 && (
          <div className="flex gap-1 mb-4 p-0.5 bg-raised border border-border rounded-lg w-fit">
            {sessionNpcs.map((n) => (
              <button
                key={n.id}
                onClick={() => setSelectedNpcId(n.id)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  selectedNpcId === n.id
                    ? "bg-hover text-ink shadow-sm"
                    : "text-ink-3 hover:text-ink-2"
                }`}
              >
                {n.name}
              </button>
            ))}
          </div>
        )}

        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-12 card animate-pulse" />)}
          </div>
        ) : !npc ? (
          <div className="text-center py-20 text-ink-3 text-sm">
            No NPCs found in this session.
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Left */}
            <div className="space-y-3">
              <div className="card p-4">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <p className="font-medium text-ink">{npc.name}</p>
                    <p className="text-xs text-ink-3 mt-0.5">Emotional state</p>
                  </div>
                  <BehaviourBadge behaviour={behaviour} />
                </div>
                <div className="space-y-3.5">
                  {BARS.map(({ key, label, colour }) => (
                    <EmotionBar key={key} label={label} value={state?.[key] ?? 0} colour={colour} />
                  ))}
                </div>
              </div>

              {lastNpcUpdate?.secret_leaked && (
                <div className="card p-3 border-red/25 bg-red/5">
                  <p className="text-xs text-red font-medium">Secret revealed</p>
                  <p className="text-xs text-ink-2 mt-0.5">{lastNpcUpdate.secret_leaked}</p>
                </div>
              )}

              <div className="card p-3">
                <p className="text-2xs text-ink-3 mb-2 font-medium uppercase tracking-wider">Raw state</p>
                <pre className="text-2xs text-green font-mono whitespace-pre-wrap overflow-auto max-h-36 leading-relaxed">
                  {JSON.stringify(state, null, 2)}
                </pre>
              </div>
            </div>

            {/* Right */}
            <div className="card p-4">
              <div className="flex items-center justify-between mb-4">
                <p className="font-medium text-ink text-sm">Interaction history</p>
                <span className="text-2xs text-ink-3">{memory.length} entries</span>
              </div>
              <MemoryLog entries={memory} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
