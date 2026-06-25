import { useEffect, useState } from "react";
import { api } from "../api/nexus";
import type { Session } from "../api/nexus";
import { SessionCard } from "../components/SessionCard";

const FILTERS = ["all", "active", "ended"] as const;
type Filter = typeof FILTERS[number];

export default function Sessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading]   = useState(true);
  const [filter, setFilter]     = useState<Filter>("all");

  useEffect(() => {
    setLoading(true);
    api.sessions.list()
      .then((data) => setSessions(data as Session[]))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = sessions.filter((s) =>
    filter === "all" ? true : s.status === filter
  );

  const activeCount = sessions.filter((s) => s.status === "active").length;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-tx-primary">Sessions</h1>
          <p className="text-tx-muted text-sm mt-0.5">
            {sessions.length} total &middot; {activeCount} active
          </p>
        </div>
        <div className="flex gap-1.5 p-1 bg-surface-raised border border-border rounded-lg">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors capitalize ${
                filter === f
                  ? "bg-surface-overlay text-tx-primary shadow-sm"
                  : "text-tx-muted hover:text-tx-secondary"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 bg-surface-raised border border-border rounded-card animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-tx-muted gap-2">
          <svg width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.4" viewBox="0 0 24 24" className="opacity-40">
            <rect x="3" y="3" width="7" height="7" rx="1.5"/>
            <rect x="14" y="3" width="7" height="7" rx="1.5"/>
            <rect x="3" y="14" width="7" height="7" rx="1.5"/>
            <rect x="14" y="14" width="7" height="7" rx="1.5"/>
          </svg>
          <p className="text-sm font-medium">No {filter === "all" ? "" : filter} sessions found</p>
          <p className="text-xs">Sessions appear here once created via the API.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filtered.map((s) => (
            <SessionCard key={s.id} session={s} />
          ))}
        </div>
      )}
    </div>
  );
}
