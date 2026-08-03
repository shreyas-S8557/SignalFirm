"""Tests for the Recommendation Engine's scoring logic. Pure functions, no
network/IO -- see scorer.py's module docstring.
"""

from __future__ import annotations

from scrapegraph_worker.recommendations.models import Bucket, Temperature
from scrapegraph_worker.recommendations.scorer import (
    build_reason,
    classify_bucket,
    classify_temperature,
    pick_best_message,
    recency_weight,
    score_person,
)

# -- recency_weight ---------------------------------------------------------


def test_recency_weight_full_for_todays_signal():
    assert recency_weight(0) == 1.0
    assert recency_weight(2) == 1.0


def test_recency_weight_zero_for_no_signal():
    assert recency_weight(None) == 0.0


def test_recency_weight_zero_past_cutoff():
    assert recency_weight(21) == 0.0
    assert recency_weight(100) == 0.0


def test_recency_weight_decays_between_bounds():
    mid = recency_weight(11.5)  # halfway between 2 and 21
    assert 0.4 < mid < 0.6


# -- score_person -------------------------------------------------------


def test_score_person_high_interest_recent_positive_is_hot():
    score = score_person(
        interest_level="HIGH",
        urgency="HIGH",
        sentiment="POSITIVE",
        confidence=0.9,
        days_since_signal=0.5,
    )
    assert score >= 65.0


def test_score_person_none_interest_scores_low():
    score = score_person(
        interest_level="NONE",
        urgency="LOW",
        sentiment="NEUTRAL",
        confidence=0.5,
        days_since_signal=1.0,
    )
    assert score < 35.0


def test_score_person_stale_signal_decays_regardless_of_interest():
    fresh = score_person(
        interest_level="HIGH", urgency="HIGH", sentiment="POSITIVE", confidence=0.9, days_since_signal=0.5
    )
    stale = score_person(
        interest_level="HIGH", urgency="HIGH", sentiment="POSITIVE", confidence=0.9, days_since_signal=30.0
    )
    assert stale < fresh
    assert stale == 0.0


def test_score_person_low_confidence_dampens_but_does_not_zero():
    full_conf = score_person(
        interest_level="HIGH", urgency="MEDIUM", sentiment="NEUTRAL", confidence=1.0, days_since_signal=0
    )
    low_conf = score_person(
        interest_level="HIGH", urgency="MEDIUM", sentiment="NEUTRAL", confidence=0.1, days_since_signal=0
    )
    assert 0 < low_conf < full_conf


def test_score_person_icp_score_adds_bonus():
    without_icp = score_person(
        interest_level="MEDIUM", urgency="MEDIUM", sentiment="NEUTRAL", confidence=0.8, days_since_signal=1
    )
    with_icp = score_person(
        interest_level="MEDIUM",
        urgency="MEDIUM",
        sentiment="NEUTRAL",
        confidence=0.8,
        days_since_signal=1,
        icp_score=90.0,
    )
    assert with_icp > without_icp


def test_score_person_clamped_to_0_100():
    score = score_person(
        interest_level="HIGH",
        urgency="HIGH",
        sentiment="POSITIVE",
        confidence=1.0,
        days_since_signal=0,
        icp_score=100.0,
    )
    assert score <= 100.0


# -- classify_temperature -------------------------------------------------


def test_classify_temperature_thresholds():
    assert classify_temperature(65.0) is Temperature.HOT
    assert classify_temperature(64.9) is Temperature.WARM
    assert classify_temperature(35.0) is Temperature.WARM
    assert classify_temperature(34.9) is Temperature.COLD


# -- classify_bucket -------------------------------------------------------


def test_classify_bucket_resolved_deal_is_ignore_even_if_score_high():
    bucket = classify_bucket(score=90.0, next_action="MARK_WON", follow_up_due=False, days_since_signal=1)
    assert bucket is Bucket.IGNORE


def test_classify_bucket_stale_signal_is_ignore():
    bucket = classify_bucket(score=80.0, next_action=None, follow_up_due=False, days_since_signal=60.0)
    assert bucket is Bucket.IGNORE


def test_classify_bucket_send_reply_is_contact_today_even_at_low_score():
    bucket = classify_bucket(score=10.0, next_action="SEND_REPLY", follow_up_due=False, days_since_signal=1)
    assert bucket is Bucket.CONTACT_TODAY


def test_classify_bucket_follow_up_due_is_contact_today():
    bucket = classify_bucket(
        score=20.0, next_action="SCHEDULE_FOLLOW_UP", follow_up_due=True, days_since_signal=5
    )
    assert bucket is Bucket.CONTACT_TODAY


def test_classify_bucket_high_score_no_action_is_contact_today():
    bucket = classify_bucket(score=70.0, next_action="NO_ACTION", follow_up_due=False, days_since_signal=1)
    assert bucket is Bucket.CONTACT_TODAY


def test_classify_bucket_low_score_no_action_is_ignore():
    bucket = classify_bucket(score=10.0, next_action="NO_ACTION", follow_up_due=False, days_since_signal=5)
    assert bucket is Bucket.IGNORE


def test_classify_bucket_mid_score_is_monitor():
    bucket = classify_bucket(score=45.0, next_action=None, follow_up_due=False, days_since_signal=5)
    assert bucket is Bucket.MONITOR


# -- build_reason ------------------------------------------------------


def test_build_reason_mentions_resolution_for_ignore():
    reason = build_reason(
        interest_level="HIGH",
        urgency="LOW",
        sentiment="POSITIVE",
        days_since_signal=1,
        next_action="MARK_LOST",
        follow_up_due=False,
        bucket=Bucket.IGNORE,
    )
    assert "resolved" in reason.lower()


def test_build_reason_mentions_follow_up_due():
    reason = build_reason(
        interest_level="MEDIUM",
        urgency="MEDIUM",
        sentiment="NEUTRAL",
        days_since_signal=3,
        next_action="SCHEDULE_FOLLOW_UP",
        follow_up_due=True,
        bucket=Bucket.CONTACT_TODAY,
    )
    assert "follow-up" in reason.lower()


# -- pick_best_message ---------------------------------------------------


def test_pick_best_message_reuses_llm_draft_for_send_reply():
    message = pick_best_message(
        next_action="SEND_REPLY",
        reply_draft="Happy to set up a call -- how does Thursday look?",
        objections_text=None,
        name="Jordan Lee",
        days_since_signal=1,
        follow_up_due=False,
        temperature=Temperature.HOT,
    )
    assert message == "Happy to set up a call -- how does Thursday look?"


def test_pick_best_message_escalate_mentions_objections():
    message = pick_best_message(
        next_action="ESCALATE_TO_HUMAN",
        reply_draft=None,
        objections_text="- Wants legal to review the contract",
        name="Jordan Lee",
        days_since_signal=1,
        follow_up_due=False,
        temperature=Temperature.WARM,
    )
    assert "escalate" in message.lower()
    assert "legal" in message.lower()


def test_pick_best_message_falls_back_to_template_with_first_name():
    message = pick_best_message(
        next_action=None,
        reply_draft=None,
        objections_text=None,
        name="Jordan Lee",
        days_since_signal=10,
        follow_up_due=False,
        temperature=Temperature.COLD,
    )
    assert message.startswith("Hi Jordan,")
