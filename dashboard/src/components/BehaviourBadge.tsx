import type { NPCBehaviour } from "../api/nexus";

const COLOURS: Record<NPCBehaviour, string> = {
  cooperative: "bg-nexus-green/20 text-nexus-green border-nexus-green/40",
  deflecting:  "bg-nexus-yellow/20 text-nexus-yellow border-nexus-yellow/40",
  nervous:     "bg-orange-400/20 text-orange-400 border-orange-400/40",
  hostile:     "bg-nexus-red/20 text-nexus-red border-nexus-red/40",
  confessing:  "bg-nexus-accent/20 text-nexus-accent border-nexus-accent/40",
};

export function BehaviourBadge({ behaviour }: { behaviour: NPCBehaviour }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded border text-xs font-mono uppercase tracking-wider ${COLOURS[behaviour]}`}
    >
      {behaviour}
    </span>
  );
}
