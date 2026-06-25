import { useState } from "react";
import { api } from "../api/nexus";
import type { ApiKey } from "../api/nexus";

export default function APIKeys() {
  const [gameId, setGameId]         = useState("");
  const [keys, setKeys]             = useState<ApiKey[]>([]);
  const [newKeyName, setNewKeyName] = useState("");
  const [rawKey, setRawKey]         = useState<string | null>(null);
  const [copied, setCopied]         = useState(false);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<string | null>(null);

  const loadKeys = async () => {
    if (!gameId.trim()) return;
    setLoading(true); setError(null);
    try {
      const data = await api.apiKeys.list(gameId.trim());
      setKeys(data.keys);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load keys.");
    } finally {
      setLoading(false);
    }
  };

  const createKey = async () => {
    if (!newKeyName.trim() || !gameId.trim()) return;
    setLoading(true); setError(null);
    try {
      const result = await api.apiKeys.create(gameId.trim(), newKeyName.trim());
      setRawKey(result.key);
      setNewKeyName("");
      await loadKeys();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't create key.");
    } finally {
      setLoading(false);
    }
  };

  const revokeKey = async (keyId: string) => {
    if (!confirm("Revoke this key? It stops working immediately.")) return;
    try {
      await api.apiKeys.revoke(gameId.trim(), keyId);
      await loadKeys();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't revoke key.");
    }
  };

  const copyKey = async () => {
    if (!rawKey) return;
    await navigator.clipboard.writeText(rawKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="text-[15px] font-semibold text-ink">API Keys</h1>
        <p className="text-xs text-ink-3 mt-0.5">Manage authentication keys for your games.</p>
      </div>

      <div className="px-6 space-y-4">
        {/* Game ID lookup */}
        <div className="card p-4">
          <label className="block text-xs font-medium text-ink-2 mb-2">Game ID</label>
          <div className="flex gap-2">
            <input
              value={gameId}
              onChange={(e) => setGameId(e.target.value)}
              placeholder="Paste your game UUID here"
              className="field font-mono text-xs"
              onKeyDown={(e) => e.key === "Enter" && void loadKeys()}
            />
            <button onClick={() => { void loadKeys(); }} disabled={!gameId.trim() || loading} className="btn shrink-0">
              Load
            </button>
          </div>
        </div>

        {error && (
          <div className="text-xs text-red bg-red/8 border border-red/20 rounded-md px-3 py-2">
            {error}
          </div>
        )}

        {/* Newly created key — show once */}
        {rawKey && (
          <div className="card p-4 border-green/25 bg-green/5">
            <p className="text-xs font-medium text-green mb-2">
              Key created — copy it now. You won't see it again.
            </p>
            <div className="flex items-center gap-2 bg-base rounded-md border border-border px-3 py-2">
              <code className="flex-1 font-mono text-xs text-green break-all">{rawKey}</code>
              <button onClick={() => { void copyKey(); }} className="btn-ghost text-xs px-2 py-1 shrink-0">
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
            <button onClick={() => setRawKey(null)} className="text-2xs text-ink-3 hover:text-ink-2 mt-2">
              Dismiss
            </button>
          </div>
        )}

        {/* Create new key */}
        <div className="card p-4">
          <label className="block text-xs font-medium text-ink-2 mb-2">Create a new key</label>
          <div className="flex gap-2">
            <input
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="e.g. Production, CI, Local dev"
              className="field"
              onKeyDown={(e) => e.key === "Enter" && void createKey()}
            />
            <button
              onClick={() => { void createKey(); }}
              disabled={!newKeyName.trim() || !gameId.trim() || loading}
              className="btn shrink-0"
            >
              Create
            </button>
          </div>
        </div>

        {/* Keys table */}
        {keys.length > 0 && (
          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <p className="text-xs font-medium text-ink-2">Keys</p>
              <span className="text-2xs text-ink-3">{keys.length} total</span>
            </div>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-ink-3">
                  <th className="text-left px-4 py-2 font-medium">Name</th>
                  <th className="text-left px-4 py-2 font-medium">Prefix</th>
                  <th className="text-left px-4 py-2 font-medium">Status</th>
                  <th className="text-left px-4 py-2 font-medium">Created</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.id} className="border-b border-border/50 hover:bg-raised transition-colors">
                    <td className="px-4 py-2.5 font-medium text-ink">{k.name}</td>
                    <td className="px-4 py-2.5 font-mono text-ink-3">{k.prefix}…</td>
                    <td className="px-4 py-2.5">
                      <span className={`tag ${k.is_active ? "bg-green/10 text-green" : "bg-raised text-ink-3 line-through"}`}>
                        {k.is_active ? "Active" : "Revoked"}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-ink-3">
                      {new Date(k.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {k.is_active && (
                        <button
                          onClick={() => { void revokeKey(k.id); }}
                          className="btn-danger text-xs px-2 py-0.5"
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
