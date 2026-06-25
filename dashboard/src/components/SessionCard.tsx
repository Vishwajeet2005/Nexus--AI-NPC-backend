import { Link } from "react-router-dom";
import type { Session } from "../api/nexus";

const STATUS_STYLES: Record<string, { dot: string; text: string; label: string }> = {
  created: { dot: "bg-status-yellow", text: "text-status-yellow", label: "Created" },
  active:  { dot: "bg-status-green",  text: "text-status-green",  label: "Active"  },
  ended:   { dot: "bg-tx-muted",      text: "text-tx-muted",      label: "Ended"   },
};

interface SessionCardProps {
  session: Session;
}

export function SessionCard({ session }: SessionCardProps) {
  const activeCount = session.players.filter((p) => !p.left_at).length;
  const s = STATUS_STYLES[session.status] ?? STATUS_STYLES.ended;

  return (
    <Link
      to={`/sessions/${session.id}`}
      className="card block p-4 hover:shadow-card-hover hover:border-border-strong transition-all duration-150 group"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <p className="font-mono text-sm font-medium text-tx-primary group-hover:text-accent transition-colors">
            {session.join_code}
          </p>
          <p className="text-tx-muted text-xs mt-0.5">
            {session.game_mode ?? "—"} · {session.region}
          </p>
        </div>
        <span className={`badge ${s.text} bg-surface text-xs shrink-0`}>
          <span className={`w-1.5 h-1.5 rounded-full ${s.dot} inline-block`} />
          {s.label}
        </span>
      </div>

      <div className="flex items-center gap-3 text-xs text-tx-muted pt-3 border-t border-border-subtle">
        <span>{activeCount}/{session.max_players} players</span>
        {session.is_locked && (
          <span className="text-status-yellow">Locked</span>
        )}
        <span className="ml-auto">{new Date(session.created_at).toLocaleDateString()}</span>
      </div>
    </Link>
  );
}
