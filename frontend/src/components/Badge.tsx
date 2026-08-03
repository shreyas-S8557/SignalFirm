type Tone = "hot" | "warm" | "cold" | "signal" | "gray";

const TONE_STYLES: Record<Tone, { bg: string; fg: string; dot: string }> = {
  hot: { bg: "var(--hot-ink)", fg: "var(--hot)", dot: "var(--hot)" },
  warm: { bg: "var(--warm-ink)", fg: "var(--warm)", dot: "var(--warm)" },
  cold: { bg: "var(--cold-ink)", fg: "var(--cold)", dot: "var(--cold)" },
  signal: { bg: "var(--signal-ink)", fg: "var(--signal)", dot: "var(--signal)" },
  gray: { bg: "var(--gray-ink)", fg: "var(--gray)", dot: "var(--gray)" },
};

export function toneForTemperature(t?: string | null): Tone {
  if (t === "HOT") return "hot";
  if (t === "WARM") return "warm";
  if (t === "COLD") return "cold";
  return "gray";
}

export function toneForBucket(b?: string | null): Tone {
  if (b === "CONTACT_TODAY") return "hot";
  if (b === "MONITOR") return "warm";
  return "gray";
}

export function toneForInterest(level?: string | null): Tone {
  if (level === "HIGH") return "hot";
  if (level === "MEDIUM") return "warm";
  if (level === "LOW") return "cold";
  return "gray";
}

export function Badge({
  label,
  tone = "gray",
  dot = true,
}: {
  label: string;
  tone?: Tone;
  dot?: boolean;
}) {
  const s = TONE_STYLES[tone];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide"
      style={{ background: s.bg, color: s.fg }}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.dot }} />}
      {label}
    </span>
  );
}
