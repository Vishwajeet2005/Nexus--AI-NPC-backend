import { useEffect, useState } from "react";
import { api } from "../api/nexus";
import type { Webhook } from "../api/nexus";

const EVENTS = [
  "session.created", "session.ended", "session.state_updated",
  "player.joined", "player.left",
  "npc_state_changed", "npc.interaction",
];

export default function Webhooks() {
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [loading, setLoading]   = useState(true);
  const [url, setUrl]           = useState("");
  const [name, setName]         = useState("");
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [error, setError]       = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, string>>({});

  const load = async () => {
    try { setWebhooks((await api.webhooks.list()).webhooks); }
    catch { setWebhooks([]); }
    finally { setLoading(false); }
  };

  useEffect(() => { void load(); }, []);

  const toggle = (ev: string) =>
    setSelectedEvents((p) => p.includes(ev) ? p.filter((e) => e !== ev) : [...p, ev]);

  const create = async () => {
    if (!url.trim() || selectedEvents.length === 0) {
      setError("You need a URL and at least one event.");
      return;
    }
    setError(null);
    try {
      await api.webhooks.create(url.trim(), selectedEvents, name.trim() || undefined);
      setUrl(""); setName(""); setSelectedEvents([]);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create webhook.");
    }
  };

  const test = async (id: string) => {
    setTestResult((p) => ({ ...p, [id]: "Sending…" }));
    try {
      const r = await api.webhooks.test(id);
      const d = r.delivery;
      setTestResult((p) => ({
        ...p,
        [id]: d.success ? `✓ ${d.http_status} (${d.duration_ms}ms)` : `✗ ${d.error ?? d.http_status} (${d.duration_ms}ms)`,
      }));
    } catch (e) {
      setTestResult((p) => ({ ...p, [id]: `✗ ${e instanceof Error ? e.message : "error"}` }));
    }
    setTimeout(() => setTestResult((p) => { const n = { ...p }; delete n[id]; return n; }), 6000);
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="text-[15px] font-semibold text-ink">Webhooks</h1>
        <p className="text-xs text-ink-3 mt-0.5">Receive real-time events from Nexus at your endpoints.</p>
      </div>

      <div className="px-6 space-y-4">
        {/* Create */}
        <div className="card p-4 space-y-3">
          <p className="text-xs font-medium text-ink-2">Register a new webhook</p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <label className="text-2xs text-ink-3 block mb-1">Name <span className="opacity-60">(optional)</span></label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="My hook" className="field" />
            </div>
            <div>
              <label className="text-2xs text-ink-3 block mb-1">Endpoint URL</label>
              <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://yourapp.com/hook" className="field" />
            </div>
          </div>

          <div>
            <p className="text-2xs text-ink-3 mb-2">Events to receive</p>
            <div className="flex flex-wrap gap-1.5">
              {EVENTS.map((ev) => (
                <button
                  key={ev}
                  onClick={() => toggle(ev)}
                  className={`px-2 py-1 rounded text-2xs font-medium transition-colors ${
                    selectedEvents.includes(ev)
                      ? "bg-blue text-white"
                      : "bg-raised border border-border text-ink-3 hover:text-ink-2 hover:border-border-light"
                  }`}
                >
                  {ev}
                </button>
              ))}
            </div>
          </div>

          {error && <p className="text-xs text-red">{error}</p>}

          <button onClick={() => { void create(); }} disabled={!url.trim() || selectedEvents.length === 0} className="btn">
            Register webhook
          </button>
        </div>

        {/* List */}
        {loading ? (
          <div className="space-y-2">
            {[1, 2].map((i) => <div key={i} className="h-20 card animate-pulse" />)}
          </div>
        ) : webhooks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
            <div className="w-10 h-10 rounded-lg bg-raised border border-border flex items-center justify-center text-ink-3">
              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" viewBox="0 0 24 24">
                <path d="M18 16.016A6 6 0 0 0 12.012 10M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM6 16.016A6 6 0 0 1 11.988 10"/>
                <path d="M12 22V12"/>
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-ink-2">No webhooks yet</p>
              <p className="text-xs text-ink-3 mt-1">Register one above to start receiving events.</p>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {webhooks.map((hook) => (
              <div key={hook.id} className="card p-4">
                <div className="flex items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <p className="text-sm font-medium text-ink truncate">{hook.name || "Unnamed"}</p>
                      <span className={`tag text-2xs shrink-0 ${hook.is_active ? "bg-green/10 text-green" : "bg-raised text-ink-3"}`}>
                        {hook.is_active ? "Active" : "Inactive"}
                      </span>
                      {hook.last_delivery_status != null && (
                        <span className={`tag text-2xs shrink-0 ${hook.last_delivery_status >= 200 && hook.last_delivery_status < 300 ? "bg-green/10 text-green" : "bg-red/10 text-red"}`}>
                          HTTP {hook.last_delivery_status}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-blue font-mono truncate mb-2">{hook.url}</p>
                    <div className="flex flex-wrap gap-1">
                      {hook.events.map((ev) => (
                        <span key={ev} className="text-2xs bg-raised border border-border rounded px-1.5 py-0.5 text-ink-3">{ev}</span>
                      ))}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1.5 shrink-0">
                    <button onClick={() => { void test(hook.id); }} className="btn-ghost text-xs px-2.5 py-1">
                      Test
                    </button>
                    {testResult[hook.id] && (
                      <span className={`text-2xs font-medium ${testResult[hook.id]?.startsWith("✓") ? "text-green" : "text-red"}`}>
                        {testResult[hook.id]}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
