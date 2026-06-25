import { useState } from "react";
import { api } from "../api/nexus";
import type { ApiKey } from "../api/nexus";

// In a real dashboard the game_id would come from the user's context/auth.
// For Phase 3 we allow the developer to paste their game ID.
export default function APIKeys() {
  const [gameId, setGameId] = useState("");
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [newKeyName, setNewKeyName] = useState("");
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadKeys = async () => {
    if (!gameId.trim()) return;
    setLoading(true);
    setError(null);
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
    setLoading(true);
    setError(null);
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
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-semibold text-white mb-6">API Keys</h1>

      {/* Game ID input */}
      <div className="bg-nexus-surface border border-nexus-border rounded-xl p-5 mb-6">
        <p className="text-nexus-muted text-xs font-mono mb-2">GAME ID</p>
        <div className="flex gap-3">
          <input
            value={gameId}
            onChange={(e) => setGameId(e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            className="flex-1 bg-nexus-bg border border-nexus-border rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-nexus-accent"
          />
          <button
            onClick={() => { void loadKeys(); }}
            className="px-4 py-2 bg-nexus-accent text-white rounded text-sm font-mono hover:bg-nexus-accent/80 transition-colors"
          >
            Load
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 px-4 py-2 bg-nexus-red/10 border border-nexus-red/30 rounded text-nexus-red text-sm font-mono">
          {error}
        </div>
      )}

      {/* Raw key display (one-time) */}
      {rawKey && (
        <div className="mb-6 bg-nexus-green/10 border border-nexus-green/30 rounded-xl p-4">
          <p className="text-nexus-green text-xs font-mono mb-2">
            ✓ NEW API KEY — Copy now. This will not be shown again.
          </p>
          <code className="block bg-nexus-bg rounded px-3 py-2 text-nexus-green font-mono text-sm break-all">
            {rawKey}
          </code>
          <button
            onClick={() => {
              void navigator.clipboard.writeText(rawKey);
            }}
            className="mt-2 text-xs text-nexus-muted font-mono hover:text-white"
          >
            Copy to clipboard
          </button>
          <button
            onClick={() => setRawKey(null)}
            className="mt-2 ml-4 text-xs text-nexus-muted font-mono hover:text-nexus-red"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Create key form */}
      <div className="bg-nexus-surface border border-nexus-border rounded-xl p-5 mb-6">
        <p className="text-nexus-muted text-xs font-mono mb-3">CREATE NEW KEY</p>
        <div className="flex gap-3">
          <input
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            placeholder="e.g. Production Server"
            className="flex-1 bg-nexus-bg border border-nexus-border rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-nexus-accent"
            onKeyDown={(e) => e.key === "Enter" && void createKey()}
          />
          <button
            onClick={() => { void createKey(); }}
            disabled={!newKeyName.trim() || !gameId.trim() || loading}
            className="px-4 py-2 bg-nexus-accent text-white rounded text-sm font-mono hover:bg-nexus-accent/80 transition-colors disabled:opacity-40"
          >
            Create
          </button>
        </div>
      </div>

      {/* Keys table */}
      {keys.length > 0 && (
        <div className="bg-nexus-surface border border-nexus-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-nexus-border text-nexus-muted text-xs font-mono">
                <th className="text-left px-4 py-3">NAME</th>
                <th className="text-left px-4 py-3">PREFIX</th>
                <th className="text-left px-4 py-3">STATUS</th>
                <th className="text-left px-4 py-3">CREATED</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} className="border-b border-nexus-border/50">
                  <td className="px-4 py-3 text-white font-medium">{k.name}</td>
                  <td className="px-4 py-3 font-mono text-nexus-accent text-xs">{k.prefix}…</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-mono ${k.is_active ? "text-nexus-green" : "text-nexus-muted line-through"}`}>
                      {k.is_active ? "active" : "revoked"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-nexus-muted text-xs font-mono">
                    {new Date(k.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    {k.is_active && (
                      <button
                        onClick={() => { void revokeKey(k.id); }}
                        className="text-xs text-nexus-red font-mono hover:underline"
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
