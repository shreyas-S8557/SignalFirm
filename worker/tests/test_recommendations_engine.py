"""Tests for recommendations/engine.py. Uses the shared `FakeTwentyClient`
(tests/conftest.py) -- no real Twenty instance or network access, same
approach as tests/test_sync.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scrapegraph_worker.recommendations.engine import build_daily_digest
from scrapegraph_worker.recommendations.models import Bucket, Temperature

NOW = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _add_person(fake_client, *, person_id: str, first_name: str, last_name: str, **fields) -> None:
    fake_client.people[person_id] = {
        "id": person_id,
        "name": {"firstName": first_name, "lastName": last_name},
        "emails": {"primaryEmail": f"{first_name.lower()}@example.com"},
        **fields,
    }


def _add_signal(fake_client, *, signal_id: str, person_id: str, created_at: datetime, **fields) -> None:
    fake_client.conversation_signals[signal_id] = {
        "id": signal_id,
        "person": {"id": person_id},
        "createdAt": _iso(created_at),
        **fields,
    }


def test_ignores_people_with_no_conversation_signal(fake_client):
    _add_person(fake_client, person_id="p1", first_name="Sam", last_name="Nobody")
    # No lastConversationSignalAt set -- never engaged, out of scope per
    # engine.py's module docstring.
    digest = build_daily_digest(fake_client, now=NOW)
    assert digest.considered_count == 0
    assert digest.ranked_by_buying_intent == []


def test_hot_lead_lands_in_contact_today_and_hot(fake_client):
    _add_person(
        fake_client,
        person_id="p1",
        first_name="Jordan",
        last_name="Lee",
        latestInterestLevel="HIGH",
        latestUrgency="HIGH",
        lastConversationSignalAt=_iso(NOW - timedelta(hours=6)),
    )
    _add_signal(
        fake_client,
        signal_id="s1",
        person_id="p1",
        created_at=NOW - timedelta(hours=6),
        sentiment="POSITIVE",
        recommendedNextAction="SEND_REPLY",
        recommendedReplyDraft="Happy to set up a call -- how does Thursday look?",
        confidence=0.9,
    )

    digest = build_daily_digest(fake_client, now=NOW)

    assert digest.considered_count == 1
    [rec] = digest.ranked_by_buying_intent
    assert rec.name == "Jordan Lee"
    assert rec.bucket is Bucket.CONTACT_TODAY
    assert rec.temperature is Temperature.HOT
    assert rec.best_message == "Happy to set up a call -- how does Thursday look?"
    assert digest.top_pick.person_id == "p1"
    assert rec in digest.contact_today
    assert rec in digest.hot


def test_resolved_deal_is_ignored_even_with_high_historical_interest(fake_client):
    _add_person(
        fake_client,
        person_id="p1",
        first_name="Alex",
        last_name="Won",
        latestInterestLevel="HIGH",
        latestUrgency="HIGH",
        lastConversationSignalAt=_iso(NOW - timedelta(days=1)),
    )
    _add_signal(
        fake_client,
        signal_id="s1",
        person_id="p1",
        created_at=NOW - timedelta(days=1),
        sentiment="POSITIVE",
        recommendedNextAction="MARK_WON",
        confidence=0.95,
    )

    digest = build_daily_digest(fake_client, now=NOW)
    [rec] = digest.ranked_by_buying_intent
    assert rec.bucket is Bucket.IGNORE
    assert rec not in digest.contact_today


def test_stale_cold_lead_is_ignored_and_cold(fake_client):
    _add_person(
        fake_client,
        person_id="p1",
        first_name="Casey",
        last_name="Stale",
        latestInterestLevel="LOW",
        latestUrgency="LOW",
        lastConversationSignalAt=_iso(NOW - timedelta(days=90)),
    )
    _add_signal(
        fake_client,
        signal_id="s1",
        person_id="p1",
        created_at=NOW - timedelta(days=90),
        sentiment="NEUTRAL",
        recommendedNextAction="NO_ACTION",
        confidence=0.5,
    )

    digest = build_daily_digest(fake_client, now=NOW)
    [rec] = digest.ranked_by_buying_intent
    assert rec.bucket is Bucket.IGNORE
    assert rec.temperature is Temperature.COLD
    assert rec in digest.cold
    assert rec in digest.ignore


def test_uses_latest_signal_when_person_has_multiple(fake_client):
    _add_person(
        fake_client,
        person_id="p1",
        first_name="Riley",
        last_name="Multi",
        latestInterestLevel="HIGH",
        latestUrgency="MEDIUM",
        lastConversationSignalAt=_iso(NOW - timedelta(hours=1)),
    )
    _add_signal(
        fake_client,
        signal_id="s-old",
        person_id="p1",
        created_at=NOW - timedelta(days=10),
        sentiment="NEGATIVE",
        recommendedNextAction="NO_ACTION",
        recommendedReplyDraft="stale draft",
        confidence=0.5,
    )
    _add_signal(
        fake_client,
        signal_id="s-new",
        person_id="p1",
        created_at=NOW - timedelta(hours=1),
        sentiment="POSITIVE",
        recommendedNextAction="SEND_REPLY",
        recommendedReplyDraft="fresh draft",
        confidence=0.8,
    )

    digest = build_daily_digest(fake_client, now=NOW)
    [rec] = digest.ranked_by_buying_intent
    assert rec.sentiment == "POSITIVE"
    assert rec.best_message == "fresh draft"


def test_ranking_orders_highest_score_first(fake_client):
    _add_person(
        fake_client,
        person_id="p-hot",
        first_name="Hot",
        last_name="Lead",
        latestInterestLevel="HIGH",
        latestUrgency="HIGH",
        lastConversationSignalAt=_iso(NOW - timedelta(hours=2)),
    )
    _add_signal(
        fake_client,
        signal_id="s-hot",
        person_id="p-hot",
        created_at=NOW - timedelta(hours=2),
        sentiment="POSITIVE",
        recommendedNextAction="SEND_REPLY",
        confidence=0.9,
    )
    _add_person(
        fake_client,
        person_id="p-cold",
        first_name="Cold",
        last_name="Lead",
        latestInterestLevel="LOW",
        latestUrgency="LOW",
        lastConversationSignalAt=_iso(NOW - timedelta(days=5)),
    )
    _add_signal(
        fake_client,
        signal_id="s-cold",
        person_id="p-cold",
        created_at=NOW - timedelta(days=5),
        sentiment="NEUTRAL",
        recommendedNextAction="NO_ACTION",
        confidence=0.5,
    )

    digest = build_daily_digest(fake_client, now=NOW)
    assert [r.person_id for r in digest.ranked_by_buying_intent] == ["p-hot", "p-cold"]
    assert digest.top_pick.person_id == "p-hot"


def test_icp_score_flows_through_from_company_relation(fake_client):
    _add_person(
        fake_client,
        person_id="p1",
        first_name="Morgan",
        last_name="Fit",
        latestInterestLevel="MEDIUM",
        latestUrgency="MEDIUM",
        lastConversationSignalAt=_iso(NOW - timedelta(hours=3)),
        company={"name": "Acme Co", "latestIcpScore": 88.0, "latestIcpPriority": "HIGH"},
    )
    _add_signal(
        fake_client,
        signal_id="s1",
        person_id="p1",
        created_at=NOW - timedelta(hours=3),
        sentiment="NEUTRAL",
        recommendedNextAction="NO_ACTION",
        confidence=0.7,
    )

    digest = build_daily_digest(fake_client, now=NOW)
    [rec] = digest.ranked_by_buying_intent
    assert rec.company_name == "Acme Co"
    assert rec.icp_score == 88.0
    assert rec.icp_priority == "HIGH"
