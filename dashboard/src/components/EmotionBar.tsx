interface EmotionBarProps {
  label: string;
  value: number;
  colour: string;
}

export function EmotionBar({ label, value, colour }: EmotionBarProps) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-center">
        <span className="text-xs font-medium text-tx-secondary">{label}</span>
        <span className="text-xs text-tx-muted tabular-nums">{pct}%</span>
      </div>
      <div className="h-1.5 bg-surface rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${colour}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
