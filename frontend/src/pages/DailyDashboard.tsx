import { useEffect, useState } from "react";
import { Flame, RefreshCw, Snowflake, Target } from "lucide-react";
import { fetchDailyDigest } from "../lib/api";
import type { DailyDigest } from "../lib/types";
import { RecommendationsWidget } from "../components/RecommendationsWidget";
import { SignalMeter } from "../components/SignalMeter";
import { LiveBadge } from "../components/LiveBadge";

function StatTile({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-md border p-3" style={{ borderColor: "var(--line)", background: "var(--canvas-raised)" }}>
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>
        {icon}
        {label}
      </div>
      <p className="mt-1 font-mono-data text-2xl font-bold" style={{ color: "var(--ink)" }}>
        {value}
      </p>
    </div>
  );
}

export function DailyDashboard({ onOpenPerson }: { onOpenPerson: (personId: string) => void }) {
  const [digest, setDigest] = useState<DailyDigest | null>(null);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const { data, live } = await fetchDailyDigest();
    setDigest(data);
    setLive(live);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  if (loading || !digest) {
    return <p className="text-sm" style={{ color: "var(--ink-faint)" }}>Loading today's digest…</p>;
  }

  return (
    <div className="max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Daily dashboard</h1>
          <p className="mt-1 text-sm" style={{ color: "var(--ink-dim)" }}>
            Generated {new Date(digest.generated_at).toLocaleString()} · {digest.considered_count} people considered
          </p>
        </div>
        <div className="flex items-center gap-2">
          <LiveBadge live={live} />
          <button
            onClick={load}
            className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-semibold"
            style={{ borderColor: "var(--line-strong)", color: "var(--ink-dim)" }}
          >
            <RefreshCw size={13} />
            Refresh
          </button>
        </div>
      </div>

      {digest.top_pick && (
        <div
          className="mt-5 rounded-lg border p-5"
          style={{ borderColor: "var(--signal)", background: "var(--signal-ink)" }}
        >
          <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider" style={{ color: "var(--signal)" }}>
            <Target size={13} />
            Today's top pick
          </div>
          <div className="mt-2.5 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-lg font-bold">{digest.top_pick.name}</p>
              <p className="text-sm" style={{ color: "var(--ink-dim)" }}>
                {digest.top_pick.company_name} — {digest.top_pick.reason}
              </p>
            </div>
            <div className="w-48">
              <SignalMeter score={digest.top_pick.buying_intent_score} />
            </div>
          </div>
        </div>
      )}

      <div className="mt-5 grid grid-cols-3 gap-3">
        <StatTile icon={<Flame size={12} />} label="Contact today" value={digest.contact_today.length} />
        <StatTile icon={<Flame size={12} />} label="Hot" value={digest.hot.length} />
        <StatTile icon={<Snowflake size={12} />} label="Cold" value={digest.cold.length} />
      </div>

      <div className="mt-6">
        <RecommendationsWidget
          title="Contact today"
          recommendations={digest.contact_today}
          emptyLabel="No one needs contact today -- check back tomorrow morning."
          onOpenPerson={onOpenPerson}
        />
      </div>

      <div className="mt-6 grid grid-cols-2 gap-6">
        <div>
          <h3 className="mb-2.5 text-[11px] font-bold uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>
            Everyone, ranked by buying intent
          </h3>
          <div className="grid gap-2">
            {digest.ranked_by_buying_intent.map((r) => (
              <button
                key={r.person_id}
                onClick={() => onOpenPerson(r.person_id)}
                className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-left text-sm"
                style={{ borderColor: "var(--line)", background: "var(--canvas-raised)" }}
              >
                <span className="truncate font-medium">{r.name}</span>
                <span className="w-28 shrink-0">
                  <SignalMeter score={r.buying_intent_score} size="sm" />
                </span>
              </button>
            ))}
          </div>
        </div>
        <div>
          <RecommendationsWidget title="Ignore" recommendations={digest.ignore} emptyLabel="Nothing to ignore." onOpenPerson={onOpenPerson} />
        </div>
      </div>
    </div>
  );
}
