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
    <div>
      {/* Header */}
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="text-[15px] font-semibold text-ink">Sessions</h1>
          <p className="text-xs text-ink-3 mt-0.5">
            {sessions.length} total &middot; {activeCount} active right now
          </p>
        </div>
        <div className="flex items-center gap-1 bg-raised border border-border rounded-md p-0.5">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded text-xs font-medium capitalize transition-colors ${
                filter === f
                  ? "bg-hover text-ink shadow-sm"
                  : "text-ink-3 hover:text-ink-2"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="px-6">
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-[88px] bg-panel border border-border rounded-lg animate-pulse" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
            <div className="w-10 h-10 rounded-lg bg-raised border border-border flex items-center justify-center text-ink-3">
              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" viewBox="0 0 24 24">
                <rect x="3" y="3" width="7" height="7" rx="1.5"/>
                <rect x="14" y="3" width="7" height="7" rx="1.5"/>
                <rect x="3" y="14" width="7" height="7" rx="1.5"/>
                <rect x="14" y="14" width="7" height="7" rx="1.5"/>
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-ink-2">No sessions yet</p>
              <p className="text-xs text-ink-3 mt-1">
                {filter !== "all"
                  ? `No ${filter} sessions found. Try switching the filter.`
                  : "Sessions show up here once created via the API."}
              </p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {filtered.map((s) => (
              <SessionCard key={s.id} session={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
