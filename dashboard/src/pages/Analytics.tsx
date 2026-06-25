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

const CHART_COLOURS = ["#6c63ff", "#4ade80", "#fbbf24", "#f87171", "#60a5fa"];

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
  const typeCounts = countByType(events);

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Analytics</h1>
          <p className="text-nexus-muted text-sm font-mono mt-1">
            {events.length} events loaded
          </p>
        </div>
        <select
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          className="bg-nexus-surface border border-nexus-border text-nexus-muted rounded px-3 py-1 text-sm font-mono focus:outline-none focus:border-nexus-accent"
        >
          <option value={100}>Last 100</option>
          <option value={200}>Last 200</option>
          <option value={500}>Last 500</option>
        </select>
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <div key={i} className="h-48 bg-nexus-surface border border-nexus-border rounded-xl animate-pulse" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="text-center py-20 text-nexus-muted font-mono">
          <p className="text-4xl mb-3">◻</p>
          <p>No analytics events yet.</p>
          <p className="text-xs mt-2">Events are recorded automatically as players use the API.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Event volume over time */}
          <div className="bg-nexus-surface border border-nexus-border rounded-xl p-5">
            <h2 className="text-white font-medium mb-4">Event Volume (by hour)</h2>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={hourBuckets} margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                <XAxis dataKey="time" tick={{ fill: "#6b7280", fontSize: 11, fontFamily: "monospace" }} />
                <YAxis tick={{ fill: "#6b7280", fontSize: 11, fontFamily: "monospace" }} />
                <Tooltip
                  contentStyle={{ background: "#12121a", border: "1px solid #1e1e2e", fontFamily: "monospace", fontSize: 12 }}
                  labelStyle={{ color: "#6c63ff" }}
                />
                <Bar dataKey="count" fill="#6c63ff" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Events by type */}
          <div className="bg-nexus-surface border border-nexus-border rounded-xl p-5">
            <h2 className="text-white font-medium mb-4">Events by Type</h2>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={typeCounts} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 80 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                <XAxis type="number" tick={{ fill: "#6b7280", fontSize: 11, fontFamily: "monospace" }} />
                <YAxis
                  dataKey="type"
                  type="category"
                  tick={{ fill: "#6b7280", fontSize: 10, fontFamily: "monospace" }}
                  width={80}
                />
                <Tooltip
                  contentStyle={{ background: "#12121a", border: "1px solid #1e1e2e", fontFamily: "monospace", fontSize: 12 }}
                />
                <Bar dataKey="count" radius={[0, 3, 3, 0]}>
                  {typeCounts.map((_entry, index) => (
                    <Cell key={index} fill={CHART_COLOURS[index % CHART_COLOURS.length] ?? "#6c63ff"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Raw event table */}
          <div className="bg-nexus-surface border border-nexus-border rounded-xl p-5">
            <h2 className="text-white font-medium mb-4">Recent Events</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="text-nexus-muted border-b border-nexus-border">
                    <th className="text-left py-2 pr-4">TYPE</th>
                    <th className="text-left py-2 pr-4">SESSION</th>
                    <th className="text-left py-2">TIMESTAMP</th>
                  </tr>
                </thead>
                <tbody>
                  {events.slice(0, 50).map((e) => (
                    <tr key={e.id} className="border-b border-nexus-border/50 hover:bg-nexus-border/20">
                      <td className="py-1.5 pr-4 text-nexus-accent">{e.event_type}</td>
                      <td className="py-1.5 pr-4 text-nexus-muted">
                        {e.session_id ? e.session_id.slice(0, 8) + "…" : "—"}
                      </td>
                      <td className="py-1.5 text-nexus-muted">
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
