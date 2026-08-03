import { ArrowRight, Clock } from "lucide-react";
import type { PersonRecommendation } from "../lib/types";
import { Badge, toneForBucket, toneForTemperature } from "./Badge";
import { SignalMeter } from "./SignalMeter";
import { SuggestedMessageButton } from "./SuggestedMessageButton";

function daysAgoLabel(days?: number | null) {
  if (days == null) return null;
  if (days < 1) return `${Math.round(days * 24)}h ago`;
  return `${Math.round(days)}d ago`;
}

export function RecommendationCard({
  rec,
  onOpenPerson,
}: {
  rec: PersonRecommendation;
  onOpenPerson?: (personId: string) => void;
}) {
  return (
    <div
      className="rounded-md border p-3.5"
      style={{ borderColor: "var(--line)", background: "var(--canvas-raised)" }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => onOpenPerson?.(rec.person_id)}
              className="truncate text-[14px] font-semibold hover:underline"
              style={{ color: "var(--ink)" }}
              title={rec.name}
            >
              {rec.name}
            </button>
            <Badge label={rec.temperature} tone={toneForTemperature(rec.temperature)} />
            <Badge label={rec.bucket.replace("_", " ")} tone={toneForBucket(rec.bucket)} dot={false} />
          </div>
          {rec.company_name && (
            <p className="mt-0.5 text-xs" style={{ color: "var(--ink-faint)" }}>
              {rec.company_name}
            </p>
          )}
        </div>
        {rec.days_since_signal != null && (
          <div className="flex shrink-0 items-center gap-1 text-[11px]" style={{ color: "var(--ink-faint)" }}>
            <Clock size={11} />
            {daysAgoLabel(rec.days_since_signal)}
          </div>
        )}
      </div>

      <div className="mt-3">
        <SignalMeter score={rec.buying_intent_score} size="sm" />
      </div>

      <p className="mt-2.5 text-[13px] leading-relaxed" style={{ color: "var(--ink-dim)" }}>
        {rec.reason}
      </p>

      {rec.latest_objections && (
        <p className="mt-1.5 text-[12px] italic" style={{ color: "var(--warm)" }}>
          Objection: {rec.latest_objections}
        </p>
      )}

      <div className="mt-3 flex items-center justify-between gap-2">
        <SuggestedMessageButton message={rec.best_message} />
        {onOpenPerson && (
          <button
            onClick={() => onOpenPerson(rec.person_id)}
            className="inline-flex items-center gap-1 text-xs font-semibold"
            style={{ color: "var(--signal)" }}
          >
            Open conversation <ArrowRight size={13} />
          </button>
        )}
      </div>
    </div>
  );
}

export function RecommendationsWidget({
  title,
  recommendations,
  emptyLabel = "Nothing here right now.",
  onOpenPerson,
}: {
  title?: string;
  recommendations: PersonRecommendation[];
  emptyLabel?: string;
  onOpenPerson?: (personId: string) => void;
}) {
  return (
    <div>
      {title && (
        <h3 className="mb-2.5 text-[11px] font-bold uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>
          {title} <span className="font-mono-data font-normal">({recommendations.length})</span>
        </h3>
      )}
      {recommendations.length === 0 ? (
        <p className="rounded-md border border-dashed p-4 text-center text-sm" style={{ borderColor: "var(--line)", color: "var(--ink-faint)" }}>
          {emptyLabel}
        </p>
      ) : (
        <div className="grid gap-2.5">
          {recommendations.map((rec) => (
            <RecommendationCard key={rec.person_id} rec={rec} onOpenPerson={onOpenPerson} />
          ))}
        </div>
      )}
    </div>
  );
}
