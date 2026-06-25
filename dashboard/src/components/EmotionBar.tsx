interface EmotionBarProps {
  label: string;
  value: number;   // 0.0 – 1.0
  colour: string;  // Tailwind bg-* class
}

export function EmotionBar({ label, value, colour }: EmotionBarProps) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-xs text-nexus-muted font-mono">
        <span>{label.toUpperCase()}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 bg-nexus-border rounded-full overflow-hidden">
        <div
          className={`h-full ${colour} rounded-full transition-all duration-700 ease-in-out`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
