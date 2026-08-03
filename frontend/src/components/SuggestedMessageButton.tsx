import { useState } from "react";
import { Check, Copy, MessageSquareText } from "lucide-react";

/**
 * Never sends anything on its own -- mirrors the backend's own boundary
 * (`recommendedReplyDraft` / `best_message` are drafts for a human to
 * review, see worker's README on why MARK_WON/MARK_LOST/SCHEDULE_FOLLOW_UP
 * are recommendations, not automatic writes). This button only reveals and
 * copies text; it never fires an API call that sends a message.
 */
export function SuggestedMessageButton({
  message,
  label = "Suggested message",
}: {
  message: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard API can be unavailable (permissions, non-secure context);
      // the text is still visible in the panel below, so nothing is lost.
    }
  }

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-semibold transition-colors"
        style={{
          borderColor: "var(--line-strong)",
          background: open ? "var(--signal-ink)" : "var(--canvas-raised)",
          color: "var(--signal)",
        }}
      >
        <MessageSquareText size={13} strokeWidth={2.25} />
        {label}
      </button>

      {open && (
        <div
          className="mt-2 rounded-md border p-3 text-[13px] leading-relaxed"
          style={{ borderColor: "var(--line)", background: "var(--canvas-raised)", color: "var(--ink)" }}
        >
          <p>{message}</p>
          <button
            onClick={copy}
            className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold"
            style={{ color: copied ? "var(--signal)" : "var(--ink-dim)" }}
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
            {copied ? "Copied" : "Copy to clipboard"}
          </button>
        </div>
      )}
    </div>
  );
}
