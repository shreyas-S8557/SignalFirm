"""Prompt construction for reply analysis.

The system prompt pins down the exact enum vocabulary and JSON shape once,
in one place, so `analyzer.py`'s parsing/normalization step has a single
contract to validate against. The model is still free-text underneath (it
can and will drift on wording), which is exactly why analyzer.py never
writes its enum fields straight through -- see normalize_result there.
"""

from __future__ import annotations

from .models import ReplyAnalysisRequest

SYSTEM_PROMPT = """\
You are a sales conversation analyst. You will be given the text of an \
inbound email reply from a prospect. Analyze it and respond with ONLY a \
single JSON object (no markdown fences, no commentary) with exactly these \
keys:

{
  "interest_level": one of "HIGH" | "MEDIUM" | "LOW" | "NONE",
  "urgency": one of "HIGH" | "MEDIUM" | "LOW",
  "sentiment": one of "POSITIVE" | "NEUTRAL" | "NEGATIVE" | "MIXED",
  "objections": array of short strings, each one distinct objection or \
concern raised (empty array if none),
  "recommended_next_action": one of "SEND_REPLY" | "SCHEDULE_FOLLOW_UP" | \
"ESCALATE_TO_HUMAN" | "MARK_WON" | "MARK_LOST" | "NO_ACTION",
  "recommended_reply_draft": a short (2-5 sentence) draft reply a human \
sales rep could review and send, in a professional but warm tone. Address \
any objections raised. Use empty string if recommended_next_action is \
MARK_WON, MARK_LOST, or NO_ACTION,
  "follow_up_in_days": integer number of days from now to follow up, ONLY \
present and meaningful when recommended_next_action is SCHEDULE_FOLLOW_UP \
(otherwise omit this key or set it to null),
  "confidence": your confidence in this analysis as a number between 0 and 1
}

Guidance:
- HIGH interest: explicit next steps requested, pricing/contract questions, \
asks to involve others on their side.
- Silence, generic pleasantries, or "not right now" with no reason given: \
LOW or NONE interest, not NEGATIVE sentiment by default.
- A clear "no", unsubscribe request, or hostility: recommend NO_ACTION or \
MARK_LOST as appropriate, and do not draft a reply that re-pitches them.
- ESCALATE_TO_HUMAN when the reply raises something outside a normal sales \
conversation (legal threat, compliance question, an angry escalation, \
pricing outside normal authority) rather than drafting a reply yourself.
- Never invent facts, pricing, or commitments in the draft reply that \
weren't in the original thread context provided.
"""


def build_user_prompt(request: ReplyAnalysisRequest) -> str:
    parts = [f"Subject: {request.subject or '(no subject)'}", "", "Reply text:", request.text.strip()]
    return "\n".join(parts)
