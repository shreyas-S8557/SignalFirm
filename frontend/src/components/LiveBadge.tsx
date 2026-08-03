export function LiveBadge({ live }: { live: boolean }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wider"
      style={{
        borderColor: live ? "var(--signal)" : "var(--line-strong)",
        color: live ? "var(--signal)" : "var(--ink-faint)",
      }}
      title={live ? "Live data from the worker API" : "Sample data -- no VITE_API_BASE_URL configured or worker unreachable"}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: live ? "var(--signal)" : "var(--ink-faint)" }}
      />
      {live ? "Live" : "Sample data"}
    </span>
  );
}
