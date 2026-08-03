import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { fetchResearchJobs } from "../lib/api";
import type { EntityRef, ResearchJob } from "../lib/types";
import { Badge } from "../components/Badge";
import { LiveBadge } from "../components/LiveBadge";

const STATUS_TONE: Record<ResearchJob["status"], "hot" | "cold" | "gray"> = {
  IMPORTED: "cold",
  SKIPPED: "gray",
  FAILED: "hot",
};

export function ResearchTab({ company }: { company: EntityRef }) {
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"ALL" | ResearchJob["status"]>("ALL");

  useEffect(() => {
    setLoading(true);
    fetchResearchJobs(company.id).then(({ data, live }) => {
      setJobs(data);
      setLive(live);
      setLoading(false);
    });
  }, [company.id]);

  const visible = filter === "ALL" ? jobs : jobs.filter((j) => j.status === filter);
  const counts = jobs.reduce<Record<string, number>>((acc, j) => {
    acc[j.status] = (acc[j.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="max-w-3xl">
      <div className="flex items-start justify-between gap-3">
        <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight">
          <Search size={19} style={{ color: "var(--signal)" }} />
          Research — {company.name}
        </h1>
        <LiveBadge live={live} />
      </div>
      <p className="mt-1 text-sm" style={{ color: "var(--ink-dim)" }}>
        Every Scrapegraph sync attempt for this company, newest first. Statuses will extend to
        RESEARCHING / RESEARCHED once the AI research pass ships (see ResearchJob's own docstring).
      </p>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {(["ALL", "IMPORTED", "SKIPPED", "FAILED"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className="rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide"
            style={{
              borderColor: filter === s ? "var(--signal)" : "var(--line-strong)",
              background: filter === s ? "var(--signal-ink)" : "transparent",
              color: filter === s ? "var(--signal)" : "var(--ink-dim)",
            }}
          >
            {s === "ALL" ? `All (${jobs.length})` : `${s.charAt(0)}${s.slice(1).toLowerCase()} (${counts[s] ?? 0})`}
          </button>
        ))}
      </div>

      <div className="mt-4 overflow-hidden rounded-md border" style={{ borderColor: "var(--line)" }}>
        <table className="w-full text-left text-[13px]">
          <thead>
            <tr style={{ background: "var(--canvas-raised)", borderBottom: "1px solid var(--line)" }}>
              <th className="px-3 py-2 text-[11px] font-bold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>Status</th>
              <th className="px-3 py-2 text-[11px] font-bold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>Source</th>
              <th className="px-3 py-2 text-[11px] font-bold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>Run ID</th>
              <th className="px-3 py-2 text-[11px] font-bold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>When</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-sm" style={{ color: "var(--ink-faint)" }}>
                  Loading research jobs…
                </td>
              </tr>
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-sm" style={{ color: "var(--ink-faint)" }}>
                  No research jobs {filter !== "ALL" ? `with status ${filter.toLowerCase()}` : "for this company yet"}.
                </td>
              </tr>
            ) : (
              visible.map((job, i) => (
                <tr key={job.id} style={{ borderTop: i === 0 ? undefined : "1px solid var(--line)", background: "var(--canvas-raised)" }}>
                  <td className="px-3 py-2">
                    <Badge label={job.status} tone={STATUS_TONE[job.status]} />
                  </td>
                  <td className="px-3 py-2">{job.source ?? "—"}</td>
                  <td className="px-3 py-2 font-mono-data text-xs" style={{ color: "var(--ink-faint)" }}>
                    {job.sourceRunId ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-xs" style={{ color: "var(--ink-faint)" }}>
                    {new Date(job.createdAt).toLocaleString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
