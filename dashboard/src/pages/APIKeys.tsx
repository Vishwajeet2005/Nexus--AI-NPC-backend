import { useState } from "react";
import { api } from "../api/nexus";
import type { ApiKey } from "../api/nexus";

export default function APIKeys() {
  const [gameId, setGameId]       = useState("");
  const [keys, setKeys]           = useState<ApiKey[]>([]);
  const [newKeyName, setNewKeyName] = useState("");
  const [rawKey, setRawKey]       = useState<string | null>(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);

  const loadKeys = async () => {
    if (!gameId.trim()) return;
    setLoading(true); setError(null);
    try {
      const data = await api.apiKeys.list(gameId.trim());
      setKeys(data.keys);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load keys");
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
      setError(e instanceof Error ? e.message : "Failed to create key");
    } finally {
      setLoading(false);
    }
  };

  const revokeKey = async (keyId: string) => {
    if (!confirm("Revoke this API key? This cannot be undone.")) return;
    try {
      await api.apiKeys.revoke(gameId.trim(), keyId);
      await loadKeys();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to revoke key");
    }
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-tx-primary">API Keys</h1>
        <p className="text-tx-muted text-sm mt-0.5">Manage authentication keys for your games.</p>
      </div>

      {/* Game ID */}
      <div className="card p-5 mb-5">
        <label className="text-xs font-medium text-tx-secondary block mb-2">Game ID</label>
        <div className="flex gap-2">
          <input
            value={gameId}
            onChange={(e) => setGameId(e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            className="field font-mono text-xs"
          />
          <button
            onClick={() => { void loadKeys(); }}
            disabled={!gameId.trim() || loading}
            className="btn shrink-0"
          >
            Load keys
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-status-red/10 border border-status-red/20 rounded-lg text-status-red text-sm">
          {error}
        </div>
      )}

      {/* New key success banner */}
      {rawKey && (
        <div className="mb-5 bg-status-green/10 border border-status-green/20 rounded-lg p-4">
          <p className="text-status-green text-xs font-medium mb-2">
            ✓ New API key created — copy it now. It won't be shown again.
          </p>
          <code className="block bg-surface rounded-lg px-3 py-2.5 text-status-green font-mono text-xs break-all">
            {rawKey}
          </code>
          <div className="flex gap-3 mt-2">
            <button
              onClick={() => { void navigator.clipboard.writeText(rawKey); }}
              className="text-xs text-tx-muted hover:text-tx-primary transition-colors"
            >
              Copy to clipboard
            </button>
            <button
              onClick={() => setRawKey(null)}
              className="text-xs text-tx-muted hover:text-status-red transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Create key */}
      <div className="card p-5 mb-5">
        <label className="text-xs font-medium text-tx-secondary block mb-2">Create new key</label>
        <div className="flex gap-2">
          <input
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            placeholder="e.g. Production Server"
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
          <div className="px-5 py-3.5 border-b border-border">
            <h2 className="text-sm font-semibold text-tx-primary">Keys ({keys.length})</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs font-medium text-tx-muted border-b border-border">
                <th className="text-left px-5 py-3">Name</th>
                <th className="text-left px-5 py-3">Prefix</th>
                <th className="text-left px-5 py-3">Status</th>
                <th className="text-left px-5 py-3">Created</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} className="border-b border-border-subtle hover:bg-surface-overlay transition-colors">
                  <td className="px-5 py-3 font-medium text-tx-primary">{k.name}</td>
                  <td className="px-5 py-3 font-mono text-xs text-tx-secondary">{k.prefix}…</td>
                  <td className="px-5 py-3">
                    <span className={`badge ${k.is_active ? "bg-status-green/15 text-status-green" : "bg-surface text-tx-muted line-through"}`}>
                      {k.is_active ? "Active" : "Revoked"}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-tx-muted text-xs">
                    {new Date(k.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-5 py-3 text-right">
                    {k.is_active && (
                      <button
                        onClick={() => { void revokeKey(k.id); }}
                        className="text-xs text-tx-muted hover:text-status-red transition-colors"
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
  );
}
