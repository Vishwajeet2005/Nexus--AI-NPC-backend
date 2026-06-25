import type { MemoryEntry } from "../api/nexus";

export function MemoryLog({ entries }: { entries: MemoryEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-xs text-ink-3 text-center py-10">
        No interactions recorded yet.
      </p>
    );
  }

  return (
    <div className="space-y-4 max-h-[500px] overflow-y-auto pr-1">
      {entries.map((entry, i) => (
        <div key={i} className="space-y-2 text-sm">
          <div className="flex gap-2 items-start">
            <span className="shrink-0 text-2xs font-medium text-ink-3 w-7 text-right pt-1.5">you</span>
            <div className="bg-raised border border-border rounded-lg px-3 py-2 text-xs text-ink-2 flex-1 leading-relaxed">
              {entry.player_message}
            </div>
          </div>
          <div className="flex gap-2 items-start">
            <span className="shrink-0 text-2xs font-medium text-blue w-7 text-right pt-1.5">npc</span>
            <div className="bg-blue/5 border border-blue/15 rounded-lg px-3 py-2 text-xs text-ink flex-1 leading-relaxed">
              {entry.npc_response}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
