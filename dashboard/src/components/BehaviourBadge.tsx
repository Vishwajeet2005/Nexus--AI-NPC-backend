import type { NPCBehaviour } from "../api/nexus";

const STYLES: Partial<Record<string, { label: string; cls: string }>> = {
  cooperative:  { label: "Cooperative",  cls: "bg-green/10  text-green"  },
  deflecting:   { label: "Deflecting",   cls: "bg-yellow/10 text-yellow" },
  nervous:      { label: "Nervous",      cls: "bg-blue/10   text-blue"   },
  hostile:      { label: "Hostile",      cls: "bg-red/10    text-red"    },
  confessing:   { label: "Confessing",   cls: "bg-purple/10 text-purple" },
};

export function BehaviourBadge({ behaviour }: { behaviour: NPCBehaviour }) {
  const s = STYLES[behaviour] ?? { label: behaviour, cls: "bg-raised text-ink-2" };
  return <span className={`tag text-xs font-medium ${s.cls}`}>{s.label}</span>;
}
