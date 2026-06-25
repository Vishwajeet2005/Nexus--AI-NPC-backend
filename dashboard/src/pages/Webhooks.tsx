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
  const [loading, setLoading] = useState(true);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
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
    setTestResult((prev) => ({ ...prev, [webhookId]: "sending…" }));
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
    // Clear after 6 s
    setTimeout(() =>
      setTestResult((prev) => { const n = { ...prev }; delete n[webhookId]; return n; }), 6000
    );
  };

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-semibold text-white mb-6">Webhooks</h1>

      {/* Create form */}
      <div className="bg-nexus-surface border border-nexus-border rounded-xl p-5 mb-6 space-y-4">
        <p className="text-nexus-muted text-xs font-mono">REGISTER NEW WEBHOOK</p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name (optional)"
            className="bg-nexus-bg border border-nexus-border rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-nexus-accent"
          />
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://yourapp.com/hook"
            className="bg-nexus-bg border border-nexus-border rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-nexus-accent"
          />
        </div>

        <div>
          <p className="text-nexus-muted text-xs font-mono mb-2">SELECT EVENTS</p>
          <div className="flex flex-wrap gap-2">
            {AVAILABLE_EVENTS.map((ev) => (
              <button
                key={ev}
                onClick={() => toggleEvent(ev)}
                className={`px-2 py-1 rounded text-xs font-mono transition-colors ${
                  selectedEvents.includes(ev)
                    ? "bg-nexus-accent text-white"
                    : "bg-nexus-bg border border-nexus-border text-nexus-muted hover:border-nexus-accent"
                }`}
              >
                {ev}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <p className="text-nexus-red text-xs font-mono">{error}</p>
        )}

        <button
          onClick={() => { void createWebhook(); }}
          disabled={!url.trim() || selectedEvents.length === 0}
          className="px-4 py-2 bg-nexus-accent text-white rounded text-sm font-mono hover:bg-nexus-accent/80 transition-colors disabled:opacity-40"
        >
          Register webhook
        </button>
      </div>

      {/* Webhook list */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-24 bg-nexus-surface border border-nexus-border rounded-xl animate-pulse" />
          ))}
        </div>
      ) : webhooks.length === 0 ? (
        <div className="text-center py-16 text-nexus-muted font-mono">
          <p className="text-4xl mb-3">◻</p>
          <p>No webhooks registered yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {webhooks.map((hook) => (
            <div
              key={hook.id}
              className="bg-nexus-surface border border-nexus-border rounded-xl p-4"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-white font-medium truncate">{hook.name || "Unnamed"}</p>
                  <p className="text-nexus-accent text-xs font-mono truncate mt-0.5">{hook.url}</p>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {hook.events.map((ev) => (
                      <span key={ev} className="text-xs font-mono bg-nexus-bg border border-nexus-border rounded px-1.5 py-0.5 text-nexus-muted">
                        {ev}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2 shrink-0">
                  <span className={`text-xs font-mono ${hook.is_active ? "text-nexus-green" : "text-nexus-muted"}`}>
                    {hook.is_active ? "active" : "inactive"}
                  </span>
                  {hook.last_delivery_status !== null && (
                    <span className={`text-xs font-mono ${
                      hook.last_delivery_status >= 200 && hook.last_delivery_status < 300
                        ? "text-nexus-green"
                        : "text-nexus-red"
                    }`}>
                      HTTP {hook.last_delivery_status}
                    </span>
                  )}
                  <button
                    onClick={() => { void testWebhook(hook.id); }}
                    className="text-xs text-nexus-muted font-mono border border-nexus-border rounded px-2 py-1 hover:border-nexus-accent hover:text-white transition-colors"
                  >
                    Test
                  </button>
                  {testResult[hook.id] && (
                    <span className={`text-xs font-mono ${
                      testResult[hook.id]?.startsWith("✓") ? "text-nexus-green" : "text-nexus-red"
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
