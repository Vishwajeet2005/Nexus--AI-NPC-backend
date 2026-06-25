import type { NPCBehaviour } from "../api/nexus";

const BEHAVIOUR_STYLES: Partial<Record<string, { label: string; classes: string }>> = {
  cooperative: { label: "Cooperative", classes: "bg-status-green/15  text-status-green"  },
  deflecting:  { label: "Deflecting",  classes: "bg-status-yellow/15 text-status-yellow" },
  nervous:     { label: "Nervous",     classes: "bg-status-blue/15   text-status-blue"   },
  hostile:     { label: "Hostile",     classes: "bg-status-red/15    text-status-red"    },
  confessing:  { label: "Confessing",  classes: "bg-accent/15        text-accent"        },
};

export function BehaviourBadge({ behaviour }: { behaviour: NPCBehaviour }) {
  const style = BEHAVIOUR_STYLES[behaviour] ?? {
    label: behaviour,
    classes: "bg-surface text-tx-muted",
  };
  return (
    <span className={`badge font-medium ${style.classes}`}>
      {style.label}
    </span>
  );
}
