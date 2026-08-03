/**
 * The one recurring visual signature of this UI: a cold -> hot gradient
 * strength meter. It exists because the domain already scores everything
 * on a 0-100 "buying intent" axis with a HOT/WARM/COLD read at the end --
 * this makes that axis literally visible everywhere a score appears,
 * rather than illustrating it with an unrelated icon or generic progress
 * bar color.
 */
export function SignalMeter({ score, size = "md" }: { score: number; size?: "sm" | "md" }) {
  const clamped = Math.max(0, Math.min(100, score));
  const height = size === "sm" ? "h-1.5" : "h-2";
  return (
    <div className="flex items-center gap-2">
      <div
        className={`relative ${height} flex-1 min-w-[64px] rounded-full overflow-hidden`}
        style={{ background: "var(--line)" }}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${clamped}%`,
            background: "linear-gradient(90deg, var(--cold), var(--warm) 55%, var(--hot))",
          }}
        />
        <div
          className="absolute inset-y-0 w-px bg-black/15"
          style={{ left: `${clamped}%` }}
        />
      </div>
      <span className="font-mono-data text-xs font-semibold" style={{ color: "var(--ink-dim)" }}>
        {Math.round(clamped)}
      </span>
    </div>
  );
}
