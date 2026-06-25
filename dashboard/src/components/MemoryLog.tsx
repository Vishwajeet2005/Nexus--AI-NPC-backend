import type { MemoryEntry } from "../api/nexus";
import { BehaviourBadge } from "./BehaviourBadge";

interface MemoryLogProps {
  entries: MemoryEntry[];
}

export function MemoryLog({ entries }: MemoryLogProps) {
  if (entries.length === 0) {
    return (
      <p className="text-nexus-muted text-sm font-mono text-center py-8">
        No interactions yet.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3 max-h-[480px] overflow-y-auto pr-1">
      {entries.map((entry) => (
        <div
          key={entry.id}
          className="bg-nexus-surface border border-nexus-border rounded-lg p-3 flex flex-col gap-2"
        >
          <div className="flex items-center justify-between">
            <BehaviourBadge behaviour={entry.behaviour} />
            {entry.secret_leaked && (
              <span className="text-xs font-mono text-nexus-red bg-nexus-red/10 border border-nexus-red/30 px-2 py-0.5 rounded">
                🔓 {entry.secret_leaked}
              </span>
            )}
            <span className="text-nexus-muted text-xs font-mono ml-auto">
              {new Date(entry.created_at).toLocaleTimeString()}
            </span>
          </div>

          <div className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-sm">
            <span className="text-nexus-accent font-mono text-xs mt-0.5 shrink-0">P›</span>
            <p className="text-gray-300">{entry.player_message}</p>
            <span className="text-nexus-green font-mono text-xs mt-0.5 shrink-0">N›</span>
            <p className="text-gray-100">{entry.npc_response}</p>
          </div>

          <div className="flex gap-4 text-xs font-mono text-nexus-muted">
            <span>Δ stress {entry.state_after.stress.toFixed(2)} → {entry.state_after.stress.toFixed(2)}</span>
            <span>Δ trust {entry.state_after.trust.toFixed(2)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
