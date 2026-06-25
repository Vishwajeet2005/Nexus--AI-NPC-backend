import { Suspense, lazy, useState } from "react";
import { BrowserRouter, Link, NavLink, Route, Routes } from "react-router-dom";
import { api, setToken } from "./api/nexus";

const Sessions   = lazy(() => import("./pages/Sessions"));
const NPCMonitor = lazy(() => import("./pages/NPCMonitor"));
const Analytics  = lazy(() => import("./pages/Analytics"));
const APIKeys    = lazy(() => import("./pages/APIKeys"));
const Webhooks   = lazy(() => import("./pages/Webhooks"));

// ── Nav items ──────────────────────────────────────────────────────────────────
const NAV = [
  {
    to: "/",
    label: "Sessions",
    icon: (
      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
        <rect x="3" y="3" width="7" height="7" rx="1.5"/>
        <rect x="14" y="3" width="7" height="7" rx="1.5"/>
        <rect x="3" y="14" width="7" height="7" rx="1.5"/>
        <rect x="14" y="14" width="7" height="7" rx="1.5"/>
      </svg>
    ),
  },
  {
    to: "/analytics",
    label: "Analytics",
    icon: (
      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
        <path d="M3 19h18M5 15l4-6 4 4 4-8"/>
      </svg>
    ),
  },
  {
    to: "/api-keys",
    label: "API Keys",
    icon: (
      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
        <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/>
      </svg>
    ),
  },
  {
    to: "/webhooks",
    label: "Webhooks",
    icon: (
      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
        <path d="M18 16.016A6 6 0 0 0 12.012 10M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM6 16.016A6 6 0 0 1 11.988 10"/>
        <path d="M12 22V12"/>
      </svg>
    ),
  },
] as const;

// ── Login ───────────────────────────────────────────────────────────────────────
function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]     = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError(null);
    try {
      const tokens = await api.auth.login(username, password);
      setToken(tokens.access_token);
      onLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleGuest = async () => {
    setLoading(true);
    try {
      const tokens = await api.auth.guest();
      setToken(tokens.access_token);
      onLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Guest login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        {/* Logo mark */}
        <div className="flex flex-col items-center mb-8 gap-2">
          <div className="w-10 h-10 rounded-xl bg-accent flex items-center justify-center shadow-lg">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-tx-primary tracking-tight">Nexus Dashboard</h1>
          <p className="text-tx-muted text-sm">Sign in to your developer account</p>
        </div>

        <form
          onSubmit={(e) => { void handleLogin(e); }}
          className="card p-6 space-y-4"
        >
          <div className="space-y-1">
            <label className="text-xs font-medium text-tx-secondary block">Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="field"
              autoComplete="username"
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-tx-secondary block">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field"
              autoComplete="current-password"
              required
            />
          </div>

          {error && (
            <p className="text-status-red text-xs">{error}</p>
          )}

          <button type="submit" disabled={loading} className="btn w-full">
            {loading ? "Signing in…" : "Sign in"}
          </button>

          <button
            type="button"
            onClick={() => { void handleGuest(); }}
            disabled={loading}
            className="btn-ghost w-full"
          >
            Continue as guest
          </button>
        </form>

        <p className="text-center text-tx-muted text-xs mt-5">
          Nexus · AI NPC Platform · v0.1.0
        </p>
      </div>
    </div>
  );
}

// ── Sidebar ────────────────────────────────────────────────────────────────────
function Sidebar() {
  return (
    <aside className="w-[220px] shrink-0 flex flex-col bg-surface-raised border-r border-border">
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-border">
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center shrink-0">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.4">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <span className="font-semibold text-tx-primary text-sm tracking-tight">Nexus</span>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-3 space-y-0.5">
        <p className="text-[10px] font-semibold text-tx-muted uppercase tracking-widest px-2 pt-1 pb-2">
          Platform
        </p>
        {NAV.map(({ to, icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-accent-muted text-accent font-medium"
                  : "text-tx-secondary hover:text-tx-primary hover:bg-surface-overlay"
              }`
            }
          >
            <span className="shrink-0">{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-status-green" />
          <span className="text-tx-muted text-xs">Phase 3 Complete</span>
        </div>
      </div>
    </aside>
  );
}

// ── Page shell ─────────────────────────────────────────────────────────────────
function Shell() {
  return (
    <div className="flex h-screen bg-surface text-tx-primary overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Suspense
          fallback={
            <div className="p-6 space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 bg-surface-raised border border-border rounded-card animate-pulse" />
              ))}
            </div>
          }
        >
          <Routes>
            <Route path="/"                                 element={<Sessions />} />
            <Route path="/sessions/:sessionId/npc-monitor" element={<NPCMonitor />} />
            <Route path="/sessions/:sessionId/npc-monitor/:npcId" element={<NPCMonitor />} />
            <Route path="/analytics"                        element={<Analytics />} />
            <Route path="/api-keys"                         element={<APIKeys />} />
            <Route path="/webhooks"                         element={<Webhooks />} />
            <Route path="*" element={
              <div className="flex flex-col items-center justify-center h-full text-tx-muted gap-3">
                <span className="text-5xl">404</span>
                <p className="text-sm">Page not found.</p>
              </div>
            } />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}

// ── Root App ───────────────────────────────────────────────────────────────────
export default function App() {
  const [authed, setAuthed] = useState(false);

  if (!authed) return <LoginScreen onLogin={() => setAuthed(true)} />;

  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
