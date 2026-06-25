import type { MemoryEntry } from "../api/nexus";

interface MemoryLogProps {
  entries: MemoryEntry[];
}

export function MemoryLog({ entries }: MemoryLogProps) {
  if (entries.length === 0) {
    return (
      <p className="text-tx-muted text-sm text-center py-8">No interactions yet.</p>
    );
  }

  return (
    <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
      {entries.map((entry, i) => (
        <div key={i} className="text-sm">
          {/* Player turn */}
          <div className="flex gap-2 mb-1.5">
            <span className="shrink-0 text-xs font-medium text-tx-muted mt-0.5 w-10 text-right">You</span>
            <div className="bg-surface border border-border rounded-lg px-3 py-2 text-tx-secondary flex-1">
              {entry.player_message}
            </div>
          </div>
          {/* NPC turn */}
          <div className="flex gap-2">
            <span className="shrink-0 text-xs font-medium text-accent mt-0.5 w-10 text-right">NPC</span>
            <div className="bg-accent/10 border border-accent/20 rounded-lg px-3 py-2 text-tx-primary flex-1">
              {entry.npc_response}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
