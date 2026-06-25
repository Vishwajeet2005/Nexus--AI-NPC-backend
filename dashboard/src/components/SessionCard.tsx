import { Link } from "react-router-dom";
import type { Session } from "../api/nexus";

const STATUS_COLOURS = {
  created: "text-nexus-yellow",
  active:  "text-nexus-green",
  ended:   "text-nexus-muted",
};

interface SessionCardProps {
  session: Session;
}

export function SessionCard({ session }: SessionCardProps) {
  const activeCount = session.players.filter((p) => !p.left_at).length;

  return (
    <Link
      to={`/sessions/${session.id}`}
      className="block bg-nexus-surface border border-nexus-border rounded-xl p-4 hover:border-nexus-accent transition-colors group"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-lg text-white group-hover:text-nexus-accent transition-colors">
            {session.join_code}
          </p>
          <p className="text-nexus-muted text-xs font-mono mt-0.5">
            {session.game_mode ?? "—"} · {session.region}
          </p>
        </div>
        <span className={`text-xs font-mono uppercase tracking-wider ${STATUS_COLOURS[session.status]}`}>
          {session.status}
        </span>
      </div>

      <div className="flex items-center gap-4 mt-4 text-sm text-nexus-muted font-mono">
        <span>{activeCount}/{session.max_players} players</span>
        {session.is_locked && (
          <span className="text-nexus-red">🔒 locked</span>
        )}
        <span className="ml-auto text-xs">
          {new Date(session.created_at).toLocaleDateString()}
        </span>
      </div>
    </Link>
  );
}
