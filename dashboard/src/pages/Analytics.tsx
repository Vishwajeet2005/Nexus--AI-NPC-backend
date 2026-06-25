import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/nexus";
import type { AnalyticsEvent } from "../api/nexus";

interface EventBucket {
  time: string;
  count: number;
  [key: string]: string | number;
}

function bucketByHour(events: AnalyticsEvent[]): EventBucket[] {
  const map = new Map<string, number>();
  events.forEach((e) => {
    const hour = new Date(e.created_at).toISOString().slice(0, 13) + ":00";
    map.set(hour, (map.get(hour) ?? 0) + 1);
  });
  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([time, count]) => ({ time: time.slice(11, 16), count }));
}

function countByType(events: AnalyticsEvent[]): Array<{ type: string; count: number }> {
  const map = new Map<string, number>();
  events.forEach((e) => map.set(e.event_type, (map.get(e.event_type) ?? 0) + 1));
  return Array.from(map.entries())
    .sort(([, a], [, b]) => b - a)
    .map(([type, count]) => ({ type, count }));
}

const CHART_COLOURS = ["#4f6ef7", "#34d399", "#fbbf24", "#f87171", "#60a5fa"];

// Tooltip styles
const tooltipStyle = {
  background: "#18181f",
  border: "1px solid #27272f",
  borderRadius: "8px",
  fontSize: 12,
  color: "#f4f4f6",
};

export default function Analytics() {
  const [events, setEvents] = useState<AnalyticsEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [limit, setLimit] = useState(200);

  useEffect(() => {
    setLoading(true);
    api.analytics.events({ limit })
      .then((r) => setEvents(r.events))
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  }, [limit]);

  const hourBuckets = bucketByHour(events);
  const typeCounts  = countByType(events);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-tx-primary">Analytics</h1>
          <p className="text-tx-muted text-sm mt-0.5">{events.length} events loaded</p>
        </div>
        <select
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          className="field w-auto"
        >
          <option value={100}>Last 100</option>
          <option value={200}>Last 200</option>
          <option value={500}>Last 500</option>
        </select>
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <div key={i} className="h-52 bg-surface-raised border border-border rounded-card animate-pulse" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-tx-muted gap-2">
          <svg width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.4" viewBox="0 0 24 24" className="opacity-40">
            <path d="M3 19h18M5 15l4-6 4 4 4-8"/>
          </svg>
          <p className="text-sm font-medium">No analytics events yet</p>
          <p className="text-xs">Events are recorded automatically as players use the API.</p>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Event volume */}
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-tx-primary mb-4">Event Volume <span className="text-tx-muted font-normal">(by hour)</span></h2>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={hourBuckets} margin={{ top: 0, right: 8, bottom: 0, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f1f27" vertical={false} />
                <XAxis dataKey="time" tick={{ fill: "#5a5a6e", fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fill: "#5a5a6e", fontSize: 11 }} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#27272f" }} />
                <Bar dataKey="count" fill="#4f6ef7" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Events by type */}
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-tx-primary mb-4">Events by Type</h2>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={typeCounts} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 80 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f1f27" horizontal={false} />
                <XAxis type="number" tick={{ fill: "#5a5a6e", fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis dataKey="type" type="category" tick={{ fill: "#8b8b9e", fontSize: 11 }} width={80} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#27272f" }} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {typeCounts.map((_entry, index) => (
                    <Cell key={index} fill={CHART_COLOURS[index % CHART_COLOURS.length] ?? "#4f6ef7"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Recent events table */}
          <div className="card overflow-hidden">
            <div className="px-5 py-4 border-b border-border">
              <h2 className="text-sm font-semibold text-tx-primary">Recent Events</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs font-medium text-tx-muted border-b border-border">
                    <th className="text-left px-5 py-3">Type</th>
                    <th className="text-left px-5 py-3">Session</th>
                    <th className="text-left px-5 py-3">Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {events.slice(0, 50).map((e) => (
                    <tr key={e.id} className="border-b border-border-subtle hover:bg-surface-overlay transition-colors">
                      <td className="px-5 py-2.5 text-accent font-medium">{e.event_type}</td>
                      <td className="px-5 py-2.5 text-tx-muted font-mono text-xs">
                        {e.session_id ? e.session_id.slice(0, 8) + "…" : "—"}
                      </td>
                      <td className="px-5 py-2.5 text-tx-muted text-xs">
                        {new Date(e.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
