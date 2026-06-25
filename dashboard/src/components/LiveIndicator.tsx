export function LiveIndicator({ live }: { live: boolean }) {
  return (
    <div className="flex items-center gap-1.5 text-xs select-none">
      <span className="relative flex h-2 w-2">
        {live && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green opacity-60" />
        )}
        <span className={`relative rounded-full h-2 w-2 ${live ? "bg-green" : "bg-ink-3"}`} />
      </span>
      <span className={live ? "text-green" : "text-ink-3"}>
        {live ? "Live" : "Offline"}
      </span>
    </div>
  );
}
