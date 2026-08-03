"""Deterministic scoring for the Recommendation Engine.

Every input here is already a validated enum or a plain number by the time
it arrives (see package docstring) -- this module is arithmetic and
templating on known-safe categories, not another LLM call. That means it's
pure, has no network/IO, and is fully unit-testable (see
`tests/test_recommendations_scorer.py`).
"""

from __future__ import annotations

from typing import Optional

from .models import Bucket, Temperature

_INTEREST_WEIGHTS = {"HIGH": 40.0, "MEDIUM": 25.0, "LOW": 10.0, "NONE": 0.0}
_URGENCY_WEIGHTS = {"HIGH": 25.0, "MEDIUM": 15.0, "LOW": 5.0}
_SENTIMENT_ADJUSTMENTS = {"POSITIVE": 10.0, "NEUTRAL": 0.0, "MIXED": 2.0, "NEGATIVE": -15.0}
_ICP_PRIORITY_BONUS = {"HIGH": 10.0, "MEDIUM": 5.0, "LOW": 0.0}

# A signal from today gets full recency weight; past this many days it
# decays to zero -- a HIGH-interest reply from six weeks ago shouldn't
# outrank a LOW-interest one from yesterday just because of the label.
_RECENCY_FULL_WEIGHT_DAYS = 2.0
_RECENCY_ZERO_WEIGHT_DAYS = 21.0

# Past this many days with no new signal, the thread is treated as gone
# cold regardless of how promising the last signal looked -- reopening it
# is a deliberate human call, not an every-morning list item.
STALE_AFTER_DAYS = 45.0

HOT_THRESHOLD = 65.0
WARM_THRESHOLD = 35.0

_RESOLVED_ACTIONS = {"MARK_WON", "MARK_LOST"}
_CONTACT_ACTIONS = {"SEND_REPLY", "ESCALATE_TO_HUMAN"}


def recency_weight(days_since_signal: Optional[float]) -> float:
    """1.0 for a signal from today/yesterday, decaying linearly to 0.0 by
    `_RECENCY_ZERO_WEIGHT_DAYS`. `None` (no signal at all) is 0.0 -- there's
    nothing to react to.
    """
    if days_since_signal is None:
        return 0.0
    if days_since_signal <= _RECENCY_FULL_WEIGHT_DAYS:
        return 1.0
    if days_since_signal >= _RECENCY_ZERO_WEIGHT_DAYS:
        return 0.0
    span = _RECENCY_ZERO_WEIGHT_DAYS - _RECENCY_FULL_WEIGHT_DAYS
    return 1.0 - (days_since_signal - _RECENCY_FULL_WEIGHT_DAYS) / span


def score_person(
    *,
    interest_level: str,
    urgency: str,
    sentiment: Optional[str],
    confidence: Optional[float],
    days_since_signal: Optional[float],
    icp_score: Optional[float] = None,
    icp_priority: Optional[str] = None,
) -> float:
    """Returns a 0-100 buying-intent score.

    `confidence` dampens rather than zeroes the result -- a 0.4-confidence
    HIGH-interest read is still more promising than nothing, just
    discounted. `icp_score`/`icp_priority` are additive bonuses layered on
    top, not multipliers, so a company with no ICP data yet (the common
    case today -- see package docstring) is scored purely on conversation
    signal rather than being penalized for a missing field.
    """
    base = _INTEREST_WEIGHTS.get(interest_level, 0.0) + _URGENCY_WEIGHTS.get(urgency, 0.0)
    base += _SENTIMENT_ADJUSTMENTS.get(sentiment or "NEUTRAL", 0.0)

    scored = base * recency_weight(days_since_signal)

    conf = confidence if confidence is not None else 0.5
    conf = max(0.0, min(1.0, conf))
    scored *= 0.5 + 0.5 * conf

    if icp_score is not None:
        scored += max(0.0, min(100.0, icp_score)) / 100.0 * 15.0
    elif icp_priority:
        scored += _ICP_PRIORITY_BONUS.get(icp_priority, 0.0)

    return round(max(0.0, min(100.0, scored)), 1)


def classify_temperature(score: float) -> Temperature:
    if score >= HOT_THRESHOLD:
        return Temperature.HOT
    if score >= WARM_THRESHOLD:
        return Temperature.WARM
    return Temperature.COLD


def classify_bucket(
    *,
    score: float,
    next_action: Optional[str],
    follow_up_due: bool,
    days_since_signal: Optional[float],
) -> Bucket:
    """The action recommendation. Checked in this order:

    1. A resolved deal (MARK_WON/MARK_LOST) is always IGNORE -- there's
       nothing left to do, no matter what the raw score says.
    2. A thread stale past `STALE_AFTER_DAYS` is IGNORE -- re-opening a
       cold thread is a deliberate human call, not a daily default.
    3. An explicit SEND_REPLY/ESCALATE_TO_HUMAN, or a follow-up whose
       recommended date has arrived, is CONTACT_TODAY regardless of score
       -- the recommendation already exists, this just surfaces it.
    4. A high score with no specific action yet is still CONTACT_TODAY
       (worth a proactive touch).
    5. A low score with nothing recommended is IGNORE.
    6. Everything else is MONITOR.
    """
    if next_action in _RESOLVED_ACTIONS:
        return Bucket.IGNORE

    if days_since_signal is not None and days_since_signal >= STALE_AFTER_DAYS:
        return Bucket.IGNORE

    if next_action in _CONTACT_ACTIONS or follow_up_due:
        return Bucket.CONTACT_TODAY

    if score >= HOT_THRESHOLD:
        return Bucket.CONTACT_TODAY

    if score < WARM_THRESHOLD and next_action in (None, "", "NO_ACTION"):
        return Bucket.IGNORE

    return Bucket.MONITOR


def build_reason(
    *,
    interest_level: str,
    urgency: str,
    sentiment: Optional[str],
    days_since_signal: Optional[float],
    next_action: Optional[str],
    follow_up_due: bool,
    bucket: Bucket,
) -> str:
    """A short, human-readable explanation for why a person landed where
    they did -- shown next to every row in the digest so the ranking isn't
    a black box.
    """
    recency = (
        "no recorded reply" if days_since_signal is None else f"last signal {_format_days(days_since_signal)}"
    )

    if bucket is Bucket.IGNORE:
        if next_action in _RESOLVED_ACTIONS:
            return f"Deal already resolved ({next_action.replace('_', ' ').title()})."
        if days_since_signal is not None and days_since_signal >= STALE_AFTER_DAYS:
            return f"Thread gone cold -- {recency}, no reason to reopen without a new signal."
        return f"Low interest ({interest_level.title()}) with no recommended action -- {recency}."

    if follow_up_due:
        return f"Scheduled follow-up is due -- {recency}."
    if next_action == "SEND_REPLY":
        return f"A reply is recommended -- {recency}."
    if next_action == "ESCALATE_TO_HUMAN":
        return f"Flagged for human review -- {recency}."

    sentiment_label = (sentiment or "neutral").title()
    return f"{interest_level.title()} interest, {urgency.title()} urgency, {sentiment_label} sentiment -- {recency}."


def pick_best_message(
    *,
    next_action: Optional[str],
    reply_draft: Optional[str],
    objections_text: Optional[str],
    name: str,
    days_since_signal: Optional[float],
    follow_up_due: bool,
    temperature: Temperature,
) -> str:
    """Chooses the best-first message for a human to review and send.

    Reuses Conversation Intelligence's own `recommendedReplyDraft` whenever
    the recommended action calls for one -- that draft was already produced
    with full thread context (see conversation/prompts.py), so re-deriving
    a message here from just the enum summary would be a strictly worse,
    context-free guess. This module only falls back to a generic template
    when no such draft exists (e.g. a stale thread, or a resolved/no-action
    case where Conversation Intelligence never generated one).
    """
    first_name = (name or "there").strip().split(" ")[0] or "there"

    if next_action in ("SEND_REPLY", "SCHEDULE_FOLLOW_UP") and reply_draft:
        return reply_draft

    if next_action == "ESCALATE_TO_HUMAN":
        note = f" Flagged concern: {objections_text}" if objections_text else ""
        return (
            "Escalate before sending anything -- Conversation Intelligence flagged this "
            f"reply for human review.{note}"
        )

    if follow_up_due:
        return f"Hi {first_name}, following up as planned -- did you get a chance to think it over?"

    if temperature is Temperature.HOT:
        return (
            f"Hi {first_name}, wanted to check back in given how positive our last exchange "
            "was -- happy to pick up right where we left off."
        )

    if days_since_signal is not None:
        return (
            f"Hi {first_name}, it's been {_format_days(days_since_signal)} since we last spoke -- "
            "checking if now's a better time to continue the conversation."
        )

    return f"Hi {first_name}, checking in -- happy to pick this back up whenever suits you."


def _format_days(days: float) -> str:
    whole = int(round(days))
    if whole <= 0:
        return "today"
    if whole == 1:
        return "1 day ago"
    return f"{whole} days ago"
