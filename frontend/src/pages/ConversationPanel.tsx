import { useEffect, useState } from "react";
import { AlertTriangle, MessagesSquare } from "lucide-react";
import { fetchConversationSignals } from "../lib/api";
import type { ConversationSignal } from "../lib/types";
import { Badge, toneForInterest } from "../components/Badge";
import { SuggestedMessageButton } from "../components/SuggestedMessageButton";
import { LiveBadge } from "../components/LiveBadge";
import type { EntityRef } from "../lib/types";

const SENTIMENT_TONE: Record<string, "hot" | "warm" | "cold" | "gray"> = {
  POSITIVE: "hot",
  MIXED: "warm",
  NEGATIVE: "cold",
  NEUTRAL: "gray",
};

function SignalRow({ signal }: { signal: ConversationSignal }) {
  return (
    <div className="relative pl-6">
      <div
        className="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full border-2"
        style={{ borderColor: "var(--signal)", background: "var(--canvas)" }}
      />
      <div className="rounded-md border p-3.5" style={{ borderColor: "var(--line)", background: "var(--canvas-raised)" }}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge label={`${signal.interestLevel} interest`} tone={toneForInterest(signal.interestLevel)} />
            <Badge label={`${signal.urgency.toLowerCase()} urgency`} tone="gray" dot={false} />
            <Badge label={signal.sentiment.toLowerCase()} tone={SENTIMENT_TONE[signal.sentiment] ?? "gray"} dot={false} />
          </div>
          <span className="text-[11px]" style={{ color: "var(--ink-faint)" }}>
            {new Date(signal.createdAt).toLocaleString()}
          </span>
        </div>

        {signal.rawExcerpt && (
          <p className="mt-2.5 text-[13px] italic leading-relaxed" style={{ color: "var(--ink-dim)" }}>
            "{signal.rawExcerpt}"
          </p>
        )}

        {signal.objections && (
          <div className="mt-2 flex items-start gap-1.5 text-[12px]" style={{ color: "var(--warm)" }}>
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
            <span>{signal.objections}</span>
          </div>
        )}

        <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>
            Next action: {signal.recommendedNextAction.replace(/_/g, " ").toLowerCase()}
          </span>
          <span className="font-mono-data text-[11px]" style={{ color: "var(--ink-faint)" }}>
            confidence {Math.round(signal.confidence * 100)}%
          </span>
        </div>

        {signal.recommendedReplyDraft && (
          <div className="mt-2.5">
            <SuggestedMessageButton message={signal.recommendedReplyDraft} label="Suggested reply" />
          </div>
        )}
      </div>
    </div>
  );
}

export function ConversationPanel({ person }: { person: EntityRef }) {
  const [signals, setSignals] = useState<ConversationSignal[]>([]);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchConversationSignals(person.id).then(({ data, live }) => {
      setSignals(data);
      setLive(live);
      setLoading(false);
    });
  }, [person.id]);

  return (
    <div className="max-w-2xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight">
            <MessagesSquare size={19} style={{ color: "var(--signal)" }} />
            {person.name}
          </h1>
          {person.companyName && (
            <p className="mt-0.5 text-sm" style={{ color: "var(--ink-dim)" }}>
              {person.companyName}
            </p>
          )}
        </div>
        <LiveBadge live={live} />
      </div>

      <p className="mt-4 text-[11px] font-bold uppercase tracking-wider" style={{ color: "var(--ink-faint)" }}>
        Conversation history ({signals.length})
      </p>

      <div className="relative mt-3 grid gap-3 border-l pl-0" style={{ borderColor: "transparent" }}>
        {loading ? (
          <p className="text-sm" style={{ color: "var(--ink-faint)" }}>Loading conversation signals…</p>
        ) : signals.length === 0 ? (
          <p className="rounded-md border border-dashed p-4 text-center text-sm" style={{ borderColor: "var(--line)", color: "var(--ink-faint)" }}>
            No analyzed replies yet for this person.
          </p>
        ) : (
          signals.map((s) => <SignalRow key={s.id} signal={s} />)
        )}
      </div>
    </div>
  );
}
