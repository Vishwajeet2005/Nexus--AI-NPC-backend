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
  { to: "/",          icon: "⬡", label: "Sessions"  },
  { to: "/analytics", icon: "∿", label: "Analytics" },
  { to: "/api-keys",  icon: "⌗", label: "API Keys"  },
  { to: "/webhooks",  icon: "↬", label: "Webhooks"  },
] as const;

// ── Login screen ───────────────────────────────────────────────────────────────
function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
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
    <div className="min-h-screen bg-nexus-bg flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-mono font-semibold text-white tracking-tight">
            <span className="text-nexus-accent">⬡</span> NEXUS
          </h1>
          <p className="text-nexus-muted text-sm mt-1 font-mono">Developer Dashboard</p>
        </div>

        <form
          onSubmit={(e) => { void handleLogin(e); }}
          className="bg-nexus-surface border border-nexus-border rounded-2xl p-6 space-y-4"
        >
          <div>
            <label className="text-nexus-muted text-xs font-mono block mb-1">USERNAME</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-nexus-bg border border-nexus-border rounded px-3 py-2 text-white text-sm font-mono focus:outline-none focus:border-nexus-accent"
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="text-nexus-muted text-xs font-mono block mb-1">PASSWORD</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-nexus-bg border border-nexus-border rounded px-3 py-2 text-white text-sm font-mono focus:outline-none focus:border-nexus-accent"
              autoComplete="current-password"
              required
            />
          </div>

          {error && (
            <p className="text-nexus-red text-xs font-mono">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-nexus-accent text-white rounded font-mono text-sm hover:bg-nexus-accent/80 transition-colors disabled:opacity-50"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>

          <button
            type="button"
            onClick={() => { void handleGuest(); }}
            disabled={loading}
            className="w-full py-2 border border-nexus-border text-nexus-muted rounded font-mono text-sm hover:border-nexus-accent hover:text-white transition-colors disabled:opacity-50"
          >
            Continue as guest
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Sidebar ────────────────────────────────────────────────────────────────────
function Sidebar() {
  // const location = useLocation();

  return (
    <aside className="w-14 md:w-52 flex flex-col bg-nexus-surface border-r border-nexus-border shrink-0">
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-nexus-border">
        <Link to="/" className="flex items-center gap-2 group">
          <span className="text-nexus-accent text-xl group-hover:scale-110 transition-transform">⬡</span>
          <span className="hidden md:block font-mono font-semibold text-white tracking-tight text-sm">
            NEXUS
          </span>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 space-y-1 px-2">
        {NAV.map(({ to, icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-2 py-2 rounded-lg text-sm font-mono transition-colors ${
                isActive
                  ? "bg-nexus-accent/20 text-nexus-accent"
                  : "text-nexus-muted hover:text-white hover:bg-nexus-border"
              }`
            }
          >
            <span className="text-lg w-5 text-center shrink-0">{icon}</span>
            <span className="hidden md:block">{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-nexus-border">
        <p className="hidden md:block text-nexus-muted text-xs font-mono text-center">
          v0.1.0 · Phase 3
        </p>
      </div>
    </aside>
  );
}

// ── Page shell ─────────────────────────────────────────────────────────────────
function Shell() {
  return (
    <div className="flex h-screen bg-nexus-bg text-gray-100 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Suspense
          fallback={
            <div className="p-6">
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-12 bg-nexus-surface border border-nexus-border rounded-xl animate-pulse" />
                ))}
              </div>
            </div>
          }
        >
          <Routes>
            <Route path="/"                                  element={<Sessions />} />
            <Route path="/sessions/:sessionId/npc-monitor"  element={<NPCMonitor />} />
            <Route path="/sessions/:sessionId/npc-monitor/:npcId" element={<NPCMonitor />} />
            <Route path="/analytics"                         element={<Analytics />} />
            <Route path="/api-keys"                          element={<APIKeys />} />
            <Route path="/webhooks"                          element={<Webhooks />} />
            <Route path="*"                                  element={
              <div className="p-6 text-nexus-muted font-mono">
                <p className="text-4xl mb-2">◻</p>
                <p>Page not found.</p>
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
