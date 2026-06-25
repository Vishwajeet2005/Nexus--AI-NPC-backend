interface LiveIndicatorProps {
  live: boolean;
}

export function LiveIndicator({ live }: LiveIndicatorProps) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span className="relative flex h-2 w-2">
        {live && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-status-green opacity-75" />
        )}
        <span
          className={`relative inline-flex rounded-full h-2 w-2 ${
            live ? "bg-status-green" : "bg-tx-muted"
          }`}
        />
      </span>
      <span className={live ? "text-status-green" : "text-tx-muted"}>
        {live ? "Live" : "Disconnected"}
      </span>
    </div>
  );
}
