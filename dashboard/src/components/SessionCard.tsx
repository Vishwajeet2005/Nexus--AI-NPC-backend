import { Link } from "react-router-dom";
import type { Session } from "../api/nexus";

const STATUS: Record<string, { dot: string; label: string; text: string }> = {
  created: { dot: "bg-yellow",      label: "Created", text: "text-yellow"      },
  active:  { dot: "bg-green",       label: "Active",  text: "text-green"       },
  ended:   { dot: "bg-ink-3",       label: "Ended",   text: "text-ink-3"       },
};

export function SessionCard({ session }: { session: Session }) {
  const s = STATUS[session.status] ?? STATUS.ended;
  const active = session.players.filter((p) => !p.left_at).length;

  return (
    <Link
      to={`/sessions/${session.id}`}
      className="card block p-4 hover:border-border-light hover:bg-raised transition-all duration-150 group"
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <p className="font-mono text-[13px] font-medium text-ink truncate group-hover:text-blue transition-colors">
            {session.join_code}
          </p>
          <p className="text-xs text-ink-3 mt-0.5 truncate">
            {session.game_mode ?? "default mode"} · {session.region}
          </p>
        </div>
        <div className={`flex items-center gap-1.5 tag shrink-0 ${s.text} bg-transparent`}>
          <span className={`w-1.5 h-1.5 rounded-full ${s.dot} shrink-0`} />
          <span className="text-xs">{s.label}</span>
        </div>
      </div>

      <div className="flex items-center gap-3 text-xs text-ink-3 pt-3 border-t border-border">
        <span>{active}/{session.max_players} players</span>
        {session.is_locked && (
          <span className="text-yellow">· locked</span>
        )}
        <span className="ml-auto">{new Date(session.created_at).toLocaleDateString()}</span>
      </div>
    </Link>
  );
}
