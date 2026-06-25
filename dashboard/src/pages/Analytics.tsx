import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api/nexus";
import type { AnalyticsEvent } from "../api/nexus";

interface Bucket { time: string; count: number; [k: string]: string | number }

function byHour(events: AnalyticsEvent[]): Bucket[] {
  const m = new Map<string, number>();
  events.forEach((e) => {
    const h = new Date(e.created_at).toISOString().slice(0, 13);
    m.set(h, (m.get(h) ?? 0) + 1);
  });
  return [...m.entries()].sort().map(([t, count]) => ({ time: t.slice(11) + ":00", count }));
}

function byType(events: AnalyticsEvent[]) {
  const m = new Map<string, number>();
  events.forEach((e) => m.set(e.event_type, (m.get(e.event_type) ?? 0) + 1));
  return [...m.entries()].sort(([,a],[,b]) => b - a).map(([type, count]) => ({ type, count }));
}

const COLORS = ["#4c7cf4", "#3ecf8e", "#f5a623", "#f16a50", "#9d7aea"];
const TIP_STYLE = { background: "#1c1c1f", border: "1px solid #2a2a2e", borderRadius: 6, fontSize: 12, color: "#eeeef0" };

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

  const hours = byHour(events);
  const types = byType(events);

  return (
    <div>
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="text-[15px] font-semibold text-ink">Analytics</h1>
          <p className="text-xs text-ink-3 mt-0.5">{events.length} events loaded</p>
        </div>
        <select
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          className="field w-auto text-xs"
        >
          <option value={100}>Last 100</option>
          <option value={200}>Last 200</option>
          <option value={500}>Last 500</option>
        </select>
      </div>

      <div className="px-6 space-y-4">
        {loading ? (
          <>
            <div className="h-56 card animate-pulse" />
            <div className="h-56 card animate-pulse" />
          </>
        ) : events.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
            <div className="w-10 h-10 rounded-lg bg-raised border border-border flex items-center justify-center text-ink-3">
              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" viewBox="0 0 24 24">
                <path d="M3 19h18M5 15l4-6 4 4 4-8"/>
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-ink-2">No events yet</p>
              <p className="text-xs text-ink-3 mt-1">Events are recorded automatically as players use the API.</p>
            </div>
          </div>
        ) : (
          <>
            {/* Volume chart */}
            <div className="card p-4">
              <p className="text-xs font-medium text-ink-2 mb-3">Event volume by hour</p>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={hours} margin={{ top: 0, right: 4, bottom: 0, left: -16 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#222226" vertical={false} />
                  <XAxis dataKey="time" tick={{ fill: "#5c5c6e", fontSize: 10 }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fill: "#5c5c6e", fontSize: 10 }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={TIP_STYLE} cursor={{ fill: "#1c1c1f" }} />
                  <Bar dataKey="count" fill="#4c7cf4" radius={[3, 3, 0, 0]} maxBarSize={32} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* By type chart */}
            <div className="card p-4">
              <p className="text-xs font-medium text-ink-2 mb-3">Events by type</p>
              <ResponsiveContainer width="100%" height={Math.max(160, types.length * 34)}>
                <BarChart data={types} layout="vertical" margin={{ top: 0, right: 4, bottom: 0, left: 90 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#222226" horizontal={false} />
                  <XAxis type="number" tick={{ fill: "#5c5c6e", fontSize: 10 }} tickLine={false} axisLine={false} />
                  <YAxis dataKey="type" type="category" tick={{ fill: "#9898a6", fontSize: 10 }} width={90} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={TIP_STYLE} cursor={{ fill: "#1c1c1f" }} />
                  <Bar dataKey="count" radius={[0, 3, 3, 0]} maxBarSize={20}>
                    {types.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length] ?? "#4c7cf4"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Raw table */}
            <div className="card overflow-hidden">
              <div className="px-4 py-3 border-b border-border">
                <p className="text-xs font-medium text-ink-2">Recent events</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border text-ink-3">
                      <th className="text-left px-4 py-2 font-medium">Type</th>
                      <th className="text-left px-4 py-2 font-medium">Session</th>
                      <th className="text-left px-4 py-2 font-medium">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.slice(0, 50).map((e) => (
                      <tr key={e.id} className="border-b border-border/50 hover:bg-raised transition-colors">
                        <td className="px-4 py-2 text-blue font-medium">{e.event_type}</td>
                        <td className="px-4 py-2 text-ink-3 font-mono">
                          {e.session_id ? e.session_id.slice(0, 8) + "…" : "—"}
                        </td>
                        <td className="px-4 py-2 text-ink-3">
                          {new Date(e.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
