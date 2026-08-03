"""Tests for recommendations/render.py."""

from __future__ import annotations

from datetime import datetime, timezone

from scrapegraph_worker.recommendations.models import Bucket, DailyDigest, PersonRecommendation, Temperature
from scrapegraph_worker.recommendations.render import render_markdown

NOW = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)


def _rec(**overrides) -> PersonRecommendation:
    defaults = dict(
        person_id="p1",
        name="Jordan Lee",
        email="jordan@example.com",
        company_name="Acme Co",
        interest_level="HIGH",
        urgency="HIGH",
        sentiment="POSITIVE",
        latest_next_action="SEND_REPLY",
        buying_intent_score=82.0,
        temperature=Temperature.HOT,
        bucket=Bucket.CONTACT_TODAY,
        reason="A reply is recommended -- today.",
        best_message="Happy to set up a call -- how does Thursday look?",
    )
    defaults.update(overrides)
    return PersonRecommendation(**defaults)


def test_render_includes_date_and_counts():
    digest = DailyDigest(generated_at=NOW, considered_count=1, ranked_by_buying_intent=[_rec()])
    md = render_markdown(digest)
    assert "2026-08-03" in md
    assert "1 contact(s)" in md


def test_render_shows_top_pick_and_contact_today_message():
    rec = _rec()
    digest = DailyDigest(
        generated_at=NOW,
        considered_count=1,
        ranked_by_buying_intent=[rec],
        contact_today=[rec],
        hot=[rec],
        top_pick=rec,
    )
    md = render_markdown(digest)
    assert "Top pick" in md
    assert "Jordan Lee" in md
    assert "Suggested message: Happy to set up a call" in md


def test_render_empty_sections_say_none_today():
    digest = DailyDigest(generated_at=NOW, considered_count=0)
    md = render_markdown(digest)
    assert md.count("_None today._") >= 4
