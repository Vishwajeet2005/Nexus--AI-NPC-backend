import { Suspense, lazy, useState } from "react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { api, setToken } from "./api/nexus";

const Sessions   = lazy(() => import("./pages/Sessions"));
const NPCMonitor = lazy(() => import("./pages/NPCMonitor"));
const Analytics  = lazy(() => import("./pages/Analytics"));
const APIKeys    = lazy(() => import("./pages/APIKeys"));
const Webhooks   = lazy(() => import("./pages/Webhooks"));

const NAV = [
  {
    to: "/",
    label: "Sessions",
    icon: (
      <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.75" viewBox="0 0 24 24">
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
      <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.75" viewBox="0 0 24 24">
        <path d="M3 19h18M5 15l4-6 4 4 4-8"/>
      </svg>
    ),
  },
  {
    to: "/api-keys",
    label: "API Keys",
    icon: (
      <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.75" viewBox="0 0 24 24">
        <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/>
      </svg>
    ),
  },
  {
    to: "/webhooks",
    label: "Webhooks",
    icon: (
      <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.75" viewBox="0 0 24 24">
        <path d="M18 16.016A6 6 0 0 0 12.012 10M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM6 16.016A6 6 0 0 1 11.988 10"/>
        <path d="M12 22V12"/>
      </svg>
    ),
  },
] as const;

// ── Login ──────────────────────────────────────────────────────────────────────
function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);
  const [guestLoading, setGuestLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError(null);
    try {
      const tokens = await api.auth.login(username, password);
      setToken(tokens.access_token);
      onLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleGuest = async () => {
    setGuestLoading(true);
    try {
      const tokens = await api.auth.guest();
      setToken(tokens.access_token);
      onLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create guest session.");
    } finally {
      setGuestLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-base flex items-center justify-center p-6">
      <div className="w-full max-w-[340px]">
        {/* Wordmark */}
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-6 h-6 rounded-md bg-blue flex items-center justify-center">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
              </svg>
            </div>
            <span className="font-semibold text-ink tracking-tight">Nexus</span>
            <span className="text-2xs text-ink-3 border border-border rounded px-1 py-px mt-0.5">dev</span>
          </div>
          <p className="text-ink-2 text-sm mt-3">Sign in to continue to the dashboard.</p>
        </div>

        <form onSubmit={(e) => { void handleLogin(e); }} className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-ink-2 mb-1.5">Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="field"
              autoComplete="username"
              autoFocus
              required
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-ink-2 mb-1.5">Password</label>
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
            <div className="flex items-start gap-2 text-xs text-red bg-red/8 border border-red/20 rounded-md px-3 py-2">
              <span className="shrink-0 mt-0.5">!</span>
              <span>{error}</span>
            </div>
          )}

          <button type="submit" disabled={loading || guestLoading} className="btn w-full mt-1">
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="relative my-5">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-border" />
          </div>
          <div className="relative flex justify-center">
            <span className="bg-base px-2 text-xs text-ink-3">or</span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => { void handleGuest(); }}
          disabled={loading || guestLoading}
          className="btn-ghost w-full"
        >
          {guestLoading ? "Creating session…" : "Continue as guest"}
        </button>

        <p className="text-center text-2xs text-ink-3 mt-6">
          Nexus AI NPC Platform · Phase 3
        </p>
      </div>
    </div>
  );
}

// ── Sidebar ────────────────────────────────────────────────────────────────────
function Sidebar() {
  return (
    <aside className="w-52 shrink-0 flex flex-col bg-panel border-r border-border">
      {/* Logo */}
      <div className="h-12 flex items-center px-4 border-b border-border gap-2">
        <div className="w-5 h-5 rounded bg-blue flex items-center justify-center shrink-0">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.6">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        </div>
        <span className="font-semibold text-ink text-sm tracking-tight">Nexus</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-2 space-y-0.5 mt-1">
        {NAV.map(({ to, icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-2.5 py-2 rounded-md text-[13px] transition-colors ${
                isActive
                  ? "bg-raised text-ink font-medium"
                  : "text-ink-2 hover:bg-hover hover:text-ink"
              }`
            }
          >
            <span className="shrink-0 opacity-80">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-border">
        <div className="flex items-center justify-between">
          <span className="text-2xs text-ink-3">v0.1.0</span>
          <span className="tag bg-green/10 text-green text-2xs">Phase 3</span>
        </div>
      </div>
    </aside>
  );
}

// ── Shell ──────────────────────────────────────────────────────────────────────
function Shell() {
  return (
    <div className="flex h-screen bg-base overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto min-w-0">
        <Suspense
          fallback={
            <div className="p-6 space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-14 bg-panel border border-border rounded-lg animate-pulse" />
              ))}
            </div>
          }
        >
          <Routes>
            <Route path="/"                                      element={<Sessions />} />
            <Route path="/sessions/:sessionId/npc-monitor"      element={<NPCMonitor />} />
            <Route path="/sessions/:sessionId/npc-monitor/:npcId" element={<NPCMonitor />} />
            <Route path="/analytics"                            element={<Analytics />} />
            <Route path="/api-keys"                             element={<APIKeys />} />
            <Route path="/webhooks"                             element={<Webhooks />} />
            <Route path="*" element={
              <div className="flex flex-col items-center justify-center h-full text-ink-3 gap-2 text-sm">
                <span className="text-4xl">404</span>
                <p>Nothing here.</p>
              </div>
            } />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(false);

  if (!authed) return <LoginScreen onLogin={() => setAuthed(true)} />;

  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
