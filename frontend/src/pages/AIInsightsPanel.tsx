import { useEffect, useState } from "react";
import { Gauge, Sparkles } from "lucide-react";
import { fetchCompanyInsights } from "../lib/api";
import type { CompanyInsights, EntityRef } from "../lib/types";
import { Badge, toneForInterest } from "../components/Badge";
import { LiveBadge } from "../components/LiveBadge";

function ScoreGauge({ score, priority }: { score?: number | null; priority?: string | null }) {
  if (score == null) {
    return (
      <div className="rounded-md border border-dashed p-4 text-center text-xs" style={{ borderColor: "var(--line)", color: "var(--ink-faint)" }}>
        Not scored yet — ICP Scoring is a scaffolded milestone; this fills in once that logic function starts writing{" "}
        <code className="font-mono-data">Company.latestIcpScore</code>.
      </div>
    );
  }
  const circumference = 2 * Math.PI * 34;
  const offset = circumference * (1 - score / 100);
  const tone = priority === "HIGH" ? "var(--hot)" : priority === "MEDIUM" ? "var(--warm)" : "var(--cold)";
  return (
    <div className="flex items-center gap-4">
      <svg width="84" height="84" viewBox="0 0 84 84">
        <circle cx="42" cy="42" r="34" fill="none" stroke="var(--line)" strokeWidth="8" />
        <circle
          cx="42"
          cy="42"
          r="34"
          fill="none"
          stroke={tone}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 42 42)"
        />
        <text x="42" y="47" textAnchor="middle" className="font-mono-data" fontSize="20" fontWeight="700" fill="var(--ink)">
          {Math.round(score)}
        </text>
      </svg>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>
          ICP score
        </p>
        {priority && <Badge label={`${priority} priority`} tone={priority === "HIGH" ? "hot" : priority === "MEDIUM" ? "warm" : "cold"} />}
      </div>
    </div>
  );
}

export function AIInsightsPanel({ company }: { company: EntityRef }) {
  const [insights, setInsights] = useState<CompanyInsights | null>(null);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchCompanyInsights(company.id).then(({ data, live }) => {
      setInsights(data);
      setLive(live);
      setLoading(false);
    });
  }, [company.id]);

  if (loading || !insights) {
    return <p className="text-sm" style={{ color: "var(--ink-faint)" }}>Loading insights…</p>;
  }

  const interestEntries = Object.entries(insights.people_by_interest_level);

  return (
    <div className="max-w-2xl">
      <div className="flex items-start justify-between gap-3">
        <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight">
          <Sparkles size={19} style={{ color: "var(--signal)" }} />
          {insights.company_name ?? company.name}
        </h1>
        <LiveBadge live={live} />
      </div>
      <p className="mt-1 text-sm" style={{ color: "var(--ink-dim)" }}>
        AI insights roll-up — snapshot at {new Date(insights.generated_at).toLocaleString()}
      </p>

      <div className="mt-5 rounded-md border p-4" style={{ borderColor: "var(--line)", background: "var(--canvas-raised)" }}>
        <ScoreGauge score={insights.latest_icp_score} priority={insights.latest_icp_priority} />
        {insights.icp_reasoning && (
          <p className="mt-3 text-[13px] leading-relaxed" style={{ color: "var(--ink-dim)" }}>
            {insights.icp_reasoning}
          </p>
        )}
        {insights.icp_rubric_version && (
          <p className="mt-1 font-mono-data text-[11px]" style={{ color: "var(--ink-faint)" }}>
            rubric {insights.icp_rubric_version}
          </p>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-md border p-3.5" style={{ borderColor: "var(--line)", background: "var(--canvas-raised)" }}>
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>
            <Gauge size={12} />
            Research activity
          </div>
          <p className="mt-1 font-mono-data text-2xl font-bold">{insights.research_job_count}</p>
          <p className="text-xs" style={{ color: "var(--ink-faint)" }}>
            {insights.last_research_at ? `last run ${new Date(insights.last_research_at).toLocaleDateString()}` : "no research runs yet"}
          </p>
        </div>
        <div className="rounded-md border p-3.5" style={{ borderColor: "var(--line)", background: "var(--canvas-raised)" }}>
          <div className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>
            Enrichment
          </div>
          <p className="mt-1 text-sm font-semibold">
            {insights.last_enriched_at ? new Date(insights.last_enriched_at).toLocaleDateString() : "Not enriched yet"}
          </p>
          <p className="text-xs" style={{ color: "var(--ink-faint)" }}>
            {insights.last_enriched_at ? "last enrichment pass" : "scaffolded, milestone pending"}
          </p>
        </div>
      </div>

      <div className="mt-4">
        <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>
          Contacts by interest level ({insights.person_count})
        </h3>
        {interestEntries.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--ink-faint)" }}>No contacts on file for this company.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {interestEntries.map(([level, count]) => (
              <Badge key={level} label={`${level} × ${count}`} tone={toneForInterest(level)} />
            ))}
          </div>
        )}
        {insights.most_recent_signal_at && (
          <p className="mt-2 text-xs" style={{ color: "var(--ink-faint)" }}>
            Most recent reply analyzed {new Date(insights.most_recent_signal_at).toLocaleString()}
          </p>
        )}
      </div>
    </div>
  );
}
