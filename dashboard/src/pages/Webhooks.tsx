import { useEffect, useState } from "react";
import { api } from "../api/nexus";
import type { Webhook } from "../api/nexus";

const AVAILABLE_EVENTS = [
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
    try {
      const data = await api.webhooks.list();
      setWebhooks(data.webhooks);
    } catch {
      setWebhooks([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const toggleEvent = (ev: string) =>
    setSelectedEvents((prev) =>
      prev.includes(ev) ? prev.filter((e) => e !== ev) : [...prev, ev]
    );

  const createWebhook = async () => {
    if (!url.trim() || selectedEvents.length === 0) {
      setError("URL and at least one event are required.");
      return;
    }
    setError(null);
    try {
      await api.webhooks.create(url.trim(), selectedEvents, name.trim() || undefined);
      setUrl(""); setName(""); setSelectedEvents([]);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create webhook");
    }
  };

  const testWebhook = async (webhookId: string) => {
    setTestResult((prev) => ({ ...prev, [webhookId]: "Sending…" }));
    try {
      const result = await api.webhooks.test(webhookId);
      const d = result.delivery;
      const msg = d.success
        ? `✓ ${d.http_status} in ${d.duration_ms}ms`
        : `✗ ${d.error ?? d.http_status ?? "failed"} in ${d.duration_ms}ms`;
      setTestResult((prev) => ({ ...prev, [webhookId]: msg }));
    } catch (e) {
      setTestResult((prev) => ({
        ...prev,
        [webhookId]: `✗ ${e instanceof Error ? e.message : "error"}`,
      }));
    }
    setTimeout(() =>
      setTestResult((prev) => { const n = { ...prev }; delete n[webhookId]; return n; }), 6000
    );
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-tx-primary">Webhooks</h1>
        <p className="text-tx-muted text-sm mt-0.5">Receive real-time events from Nexus to your endpoints.</p>
      </div>

      {/* Create form */}
      <div className="card p-5 mb-5 space-y-4">
        <h2 className="text-sm font-semibold text-tx-primary">Register new webhook</h2>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <label className="text-xs font-medium text-tx-secondary block">Name <span className="text-tx-muted">(optional)</span></label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My webhook"
              className="field"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-tx-secondary block">Endpoint URL</label>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://yourapp.com/hook"
              className="field"
            />
          </div>
        </div>

        <div>
          <p className="text-xs font-medium text-tx-secondary mb-2">Events to subscribe</p>
          <div className="flex flex-wrap gap-2">
            {AVAILABLE_EVENTS.map((ev) => (
              <button
                key={ev}
                onClick={() => toggleEvent(ev)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                  selectedEvents.includes(ev)
                    ? "bg-accent text-white"
                    : "bg-surface border border-border text-tx-muted hover:border-border-strong hover:text-tx-secondary"
                }`}
              >
                {ev}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <p className="text-status-red text-xs">{error}</p>
        )}

        <button
          onClick={() => { void createWebhook(); }}
          disabled={!url.trim() || selectedEvents.length === 0}
          className="btn"
        >
          Register webhook
        </button>
      </div>

      {/* Webhook list */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-24 bg-surface-raised border border-border rounded-card animate-pulse" />
          ))}
        </div>
      ) : webhooks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-tx-muted gap-2">
          <svg width="36" height="36" fill="none" stroke="currentColor" strokeWidth="1.4" viewBox="0 0 24 24" className="opacity-40">
            <path d="M18 16.016A6 6 0 0 0 12.012 10M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM6 16.016A6 6 0 0 1 11.988 10"/>
            <path d="M12 22V12"/>
          </svg>
          <p className="text-sm font-medium">No webhooks registered</p>
        </div>
      ) : (
        <div className="space-y-3">
          {webhooks.map((hook) => (
            <div key={hook.id} className="card p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <p className="font-medium text-tx-primary text-sm truncate">{hook.name || "Unnamed"}</p>
                    <span className={`badge shrink-0 ${hook.is_active ? "bg-status-green/15 text-status-green" : "bg-surface text-tx-muted"}`}>
                      {hook.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>
                  <p className="text-accent text-xs font-mono truncate mb-2">{hook.url}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {hook.events.map((ev) => (
                      <span key={ev} className="text-xs bg-surface border border-border rounded-md px-2 py-0.5 text-tx-muted">
                        {ev}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex flex-col items-end gap-2 shrink-0">
                  {hook.last_delivery_status !== null && (
                    <span className={`text-xs font-medium ${
                      hook.last_delivery_status >= 200 && hook.last_delivery_status < 300
                        ? "text-status-green"
                        : "text-status-red"
                    }`}>
                      HTTP {hook.last_delivery_status}
                    </span>
                  )}
                  <button
                    onClick={() => { void testWebhook(hook.id); }}
                    className="btn-ghost text-xs px-3 py-1"
                  >
                    Test
                  </button>
                  {testResult[hook.id] && (
                    <span className={`text-xs font-medium ${
                      testResult[hook.id]?.startsWith("✓") ? "text-status-green" : "text-status-red"
                    }`}>
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
  );
}
