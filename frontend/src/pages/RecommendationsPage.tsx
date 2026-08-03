import { useEffect, useState } from "react";
import { Target } from "lucide-react";
import { fetchDailyDigest } from "../lib/api";
import type { Bucket, DailyDigest } from "../lib/types";
import { RecommendationsWidget } from "../components/RecommendationsWidget";
import { LiveBadge } from "../components/LiveBadge";

const FILTERS: { key: Bucket | "ALL"; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "CONTACT_TODAY", label: "Contact today" },
  { key: "MONITOR", label: "Monitor" },
  { key: "IGNORE", label: "Ignore" },
];

export function RecommendationsPage({ onOpenPerson }: { onOpenPerson: (personId: string) => void }) {
  const [digest, setDigest] = useState<DailyDigest | null>(null);
  const [live, setLive] = useState(false);
  const [filter, setFilter] = useState<Bucket | "ALL">("ALL");

  useEffect(() => {
    fetchDailyDigest().then(({ data, live }) => {
      setDigest(data);
      setLive(live);
    });
  }, []);

  if (!digest) return <p className="text-sm" style={{ color: "var(--ink-faint)" }}>Loading recommendations…</p>;

  const list =
    filter === "ALL" ? digest.ranked_by_buying_intent : digest.ranked_by_buying_intent.filter((r) => r.bucket === filter);

  return (
    <div className="max-w-3xl">
      <div className="flex items-start justify-between gap-3">
        <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight">
          <Target size={19} style={{ color: "var(--signal)" }} />
          Recommendations
        </h1>
        <LiveBadge live={live} />
      </div>
      <p className="mt-1 text-sm" style={{ color: "var(--ink-dim)" }}>
        Same engine behind the daily digest, filterable by action bucket.
      </p>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className="rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide"
            style={{
              borderColor: filter === f.key ? "var(--signal)" : "var(--line-strong)",
              background: filter === f.key ? "var(--signal-ink)" : "transparent",
              color: filter === f.key ? "var(--signal)" : "var(--ink-dim)",
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="mt-4">
        <RecommendationsWidget recommendations={list} onOpenPerson={onOpenPerson} />
      </div>
    </div>
  );
}
