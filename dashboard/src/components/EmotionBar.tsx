interface EmotionBarProps {
  label: string;
  value: number;
  colour: string;
}

export function EmotionBar({ label, value, colour }: EmotionBarProps) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div>
      <div className="flex justify-between text-xs mb-1.5">
        <span className="text-ink-2">{label}</span>
        <span className="text-ink-3 tabular-nums">{pct}%</span>
      </div>
      <div className="h-1 bg-raised rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-[width] duration-500 ease-out ${colour}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
