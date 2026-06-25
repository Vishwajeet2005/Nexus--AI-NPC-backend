interface LiveIndicatorProps {
  live: boolean;
}

export function LiveIndicator({ live }: LiveIndicatorProps) {
  if (!live) {
    return (
      <span className="flex items-center gap-1.5 text-nexus-muted text-xs font-mono">
        <span className="w-2 h-2 rounded-full bg-nexus-muted" />
        OFFLINE
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1.5 text-nexus-green text-xs font-mono">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-nexus-green opacity-75" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-nexus-green" />
      </span>
      LIVE
    </span>
  );
}
