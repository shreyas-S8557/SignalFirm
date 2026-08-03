"""Builds the daily Recommendation Engine digest.

Scope: only People who have at least one ConversationSignal (i.e.
`Person.lastConversationSignalAt` is set) are considered. This engine
answers "of the people we've actually heard back from, who's worth a
morning's attention" -- prioritizing brand-new, never-contacted prospects
is a different question (ICP scoring, see the top-level README's "What's
NOT connected to anything yet") that this milestone deliberately doesn't
answer, the same way Conversation Intelligence deliberately never
auto-sends a reply.

No new LLM calls happen here -- everything is read from fields
Conversation Intelligence already wrote (see `conversation/analyzer.py` and
`conversation-signal-webhook.ts`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from ..twenty_client import TwentyClient
from .models import Bucket, DailyDigest, PersonRecommendation, Temperature
from .scorer import build_reason, classify_bucket, classify_temperature, pick_best_message, score_person

logger = logging.getLogger(__name__)

# A daily "who to contact this morning" digest is a bounded, human-sized
# list, not a full-table export. If your workspace has more than this many
# people with an active conversation signal, this is the first place to add
# pagination (Twenty's REST API supports a `startingAfter` cursor) rather
# than raising the limit indefinitely.
DEFAULT_PEOPLE_FETCH_LIMIT = 200


def build_daily_digest(
    client: TwentyClient,
    *,
    now: Optional[datetime] = None,
    people_fetch_limit: int = DEFAULT_PEOPLE_FETCH_LIMIT,
) -> DailyDigest:
    now = now or datetime.now(timezone.utc)

    raw_people = client.find_records("people", limit=people_fetch_limit, depth=1)
    engaged_people = [p for p in raw_people if p.get("id") and p.get("lastConversationSignalAt")]

    recommendations = [_build_recommendation(client, person, now=now) for person in engaged_people]
    ranked = sorted(recommendations, key=lambda r: r.buying_intent_score, reverse=True)

    return DailyDigest(
        generated_at=now,
        considered_count=len(recommendations),
        contact_today=[r for r in ranked if r.bucket is Bucket.CONTACT_TODAY],
        ignore=[r for r in ranked if r.bucket is Bucket.IGNORE],
        hot=[r for r in ranked if r.temperature is Temperature.HOT],
        cold=[r for r in ranked if r.temperature is Temperature.COLD],
        ranked_by_buying_intent=ranked,
        top_pick=ranked[0] if ranked else None,
    )


def _build_recommendation(client: TwentyClient, person: dict, *, now: datetime) -> PersonRecommendation:
    person_id = person["id"]
    signal = _latest_signal_for_person(client, person_id)

    interest_level = person.get("latestInterestLevel") or "NONE"
    urgency = person.get("latestUrgency") or "LOW"
    sentiment = signal.get("sentiment") if signal else None
    next_action = signal.get("recommendedNextAction") if signal else None
    confidence = signal.get("confidence") if signal else None
    objections = signal.get("objections") if signal else None
    reply_draft = signal.get("recommendedReplyDraft") if signal else None

    days_since_signal = _days_since(person.get("lastConversationSignalAt"), now)
    follow_up_due = _is_follow_up_due(signal, now)

    company = person.get("company") if isinstance(person.get("company"), dict) else {}
    icp_score = company.get("latestIcpScore")
    icp_priority = company.get("latestIcpPriority")

    score = score_person(
        interest_level=interest_level,
        urgency=urgency,
        sentiment=sentiment,
        confidence=confidence,
        days_since_signal=days_since_signal,
        icp_score=icp_score,
        icp_priority=icp_priority,
    )
    temperature = classify_temperature(score)
    bucket = classify_bucket(
        score=score,
        next_action=next_action,
        follow_up_due=follow_up_due,
        days_since_signal=days_since_signal,
    )
    name = _person_display_name(person)

    return PersonRecommendation(
        person_id=person_id,
        name=name,
        email=_person_email(person),
        company_name=company.get("name"),
        interest_level=interest_level,
        urgency=urgency,
        sentiment=sentiment,
        latest_next_action=next_action,
        latest_objections=objections,
        latest_confidence=confidence,
        last_signal_at=_parse_iso(person.get("lastConversationSignalAt")),
        days_since_signal=days_since_signal,
        icp_score=icp_score,
        icp_priority=icp_priority,
        buying_intent_score=score,
        temperature=temperature,
        bucket=bucket,
        reason=build_reason(
            interest_level=interest_level,
            urgency=urgency,
            sentiment=sentiment,
            days_since_signal=days_since_signal,
            next_action=next_action,
            follow_up_due=follow_up_due,
            bucket=bucket,
        ),
        best_message=pick_best_message(
            next_action=next_action,
            reply_draft=reply_draft,
            objections_text=objections,
            name=name,
            days_since_signal=days_since_signal,
            follow_up_due=follow_up_due,
            temperature=temperature,
        ),
    )


def _latest_signal_for_person(client: TwentyClient, person_id: str) -> Optional[dict]:
    try:
        matches = client.find_records(
            "conversationSignals",
            filter_query=f"person.id[eq]:{person_id}",
            limit=1,
            depth=0,
            order_by="createdAt[DescNullsLast]",
        )
    except Exception:  # noqa: BLE001
        # Best-effort: a missing/misbehaving conversationSignals endpoint
        # (e.g. twenty-app not yet synced) shouldn't take down the whole
        # digest -- that person just falls back to Person's own
        # denormalized latestInterestLevel/latestUrgency with no
        # per-signal detail (sentiment, objections, draft, next action).
        logger.warning("Failed to fetch latest ConversationSignal for person %s", person_id, exc_info=True)
        return None
    return matches[0] if matches else None


def _person_display_name(person: dict) -> str:
    name = person.get("name") or {}
    first = name.get("firstName") or ""
    last = name.get("lastName") or ""
    full = f"{first} {last}".strip()
    return full or person.get("id", "Unknown")


def _person_email(person: dict) -> Optional[str]:
    return (person.get("emails") or {}).get("primaryEmail")


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _days_since(value: Optional[str], now: datetime) -> Optional[float]:
    ts = _parse_iso(value)
    if ts is None:
        return None
    return (now - ts).total_seconds() / 86400.0


def _is_follow_up_due(signal: Optional[dict], now: datetime) -> bool:
    if not signal:
        return False
    follow_up_at = _parse_iso(signal.get("recommendedFollowUpAt"))
    if follow_up_at is None:
        return False
    return follow_up_at <= now
