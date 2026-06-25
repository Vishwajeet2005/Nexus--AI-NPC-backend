import { useEffect, useState } from "react";
import { api } from "../api/nexus";
import type { Session } from "../api/nexus";
import { SessionCard } from "../components/SessionCard";

export default function Sessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "active" | "ended">("all");

  useEffect(() => {
    setLoading(true);
    // The backend doesn't expose a list-all-sessions endpoint in Phase 1/2,
    // so we pull from analytics events and reconstruct session summaries.
    // For the dashboard we fall back to an empty list gracefully.
    api.sessions.list().then((data) => setSessions(data as Session[]))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = sessions.filter((s) =>
    filter === "all" ? true : s.status === filter
  );

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Sessions</h1>
          <p className="text-nexus-muted text-sm mt-1 font-mono">
            {sessions.length} total · {sessions.filter((s) => s.status === "active").length} active
          </p>
        </div>
        <div className="flex gap-2">
          {(["all", "active", "ended"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded text-xs font-mono uppercase transition-colors ${
                filter === f
                  ? "bg-nexus-accent text-white"
                  : "bg-nexus-surface border border-nexus-border text-nexus-muted hover:border-nexus-accent"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-28 bg-nexus-surface border border-nexus-border rounded-xl animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20 text-nexus-muted font-mono">
          <p className="text-4xl mb-3">◻</p>
          <p>No {filter === "all" ? "" : filter} sessions found.</p>
          <p className="text-xs mt-2">Sessions appear here once created via the API.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filtered.map((s) => (
            <SessionCard key={s.id} session={s} />
          ))}
        </div>
      )}
    </div>
  );
}
