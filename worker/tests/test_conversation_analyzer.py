"""Tests for the Conversation Intelligence analyzer. No real LLM or network
call -- `FakeLLMClient` is an in-memory stand-in exposing just the
`complete_json` surface `analyzer.py` calls, so parsing/normalization can be
verified offline (same approach as tests/conftest.py::FakeTwentyClient).
"""

from __future__ import annotations

import json

from scrapegraph_worker.conversation.analyzer import (
    _compute_follow_up_at,
    _parse_json_object,
    analyze_reply,
    normalize_result,
)
from scrapegraph_worker.conversation.llm_client import LLMError
from scrapegraph_worker.conversation.models import (
    InterestLevel,
    NextAction,
    ReplyAnalysisRequest,
    Sentiment,
    Urgency,
)


class FakeLLMClient:
    def __init__(self, response: str | None = None, raise_error: Exception | None = None):
        self._response = response
        self._raise_error = raise_error
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self._raise_error:
            raise self._raise_error
        assert self._response is not None
        return self._response


def _request(**overrides) -> ReplyAnalysisRequest:
    defaults = dict(
        messageId="msg-1",
        threadId="thread-1",
        personId="person-1",
        subject="Re: pricing",
        text="Thanks for the info, can we get on a call this week to talk numbers?",
        receivedAt="2026-08-01T10:00:00Z",
    )
    defaults.update(overrides)
    return ReplyAnalysisRequest.model_validate(defaults)


# -- happy path -----------------------------------------------------------


def test_analyze_reply_happy_path_maps_to_enums():
    response = json.dumps(
        {
            "interest_level": "high",
            "urgency": "medium",
            "sentiment": "positive",
            "objections": [],
            "recommended_next_action": "send_reply",
            "recommended_reply_draft": "Happy to set up a call -- how does Thursday look?",
            "confidence": 0.87,
        }
    )
    client = FakeLLMClient(response=response)
    result = analyze_reply(_request(), client, model_name="test-model/v1")

    assert result.status == "COMPLETED"
    assert result.interest_level is InterestLevel.HIGH
    assert result.urgency is Urgency.MEDIUM
    assert result.sentiment is Sentiment.POSITIVE
    assert result.recommended_next_action is NextAction.SEND_REPLY
    assert result.recommended_reply_draft is not None
    assert result.confidence == 0.87
    assert result.model_used == "test-model/v1"
    assert len(client.calls) == 1


# -- LLM call failure -------------------------------------------------------


def test_analyze_reply_llm_error_returns_failed_status_not_exception():
    client = FakeLLMClient(raise_error=LLMError("backend down"))
    result = analyze_reply(_request(), client, model_name="test-model")

    assert result.status == "FAILED"
    assert result.error_message == "backend down"
    # Fields still default to safe values so downstream code never needs a
    # None-check on the enum fields themselves.
    assert result.interest_level is InterestLevel.NONE


# -- malformed JSON handling -------------------------------------------------


def test_analyze_reply_non_json_output_returns_failed_status():
    client = FakeLLMClient(response="Sure! Here's my analysis: the prospect seems interested.")
    result = analyze_reply(_request(), client, model_name="test-model")

    assert result.status == "FAILED"
    assert "JSON" in result.error_message


def test_parse_json_object_strips_markdown_fences():
    fenced = '```json\n{"interest_level": "HIGH"}\n```'
    assert _parse_json_object(fenced) == {"interest_level": "HIGH"}


def test_parse_json_object_extracts_object_from_surrounding_chatter():
    noisy = 'Sure, here you go:\n{"interest_level": "LOW"}\nHope that helps!'
    assert _parse_json_object(noisy) == {"interest_level": "LOW"}


def test_parse_json_object_returns_none_for_unrecoverable_garbage():
    assert _parse_json_object("not json at all, no braces") is None


# -- enum coercion / drift tolerance -----------------------------------------


def test_normalize_result_tolerates_case_and_separator_drift():
    parsed = {
        "interest_level": "medium",
        "urgency": "High",  # mixed case
        "sentiment": "NEGATIVE",
        "recommended_next_action": "escalate to human",  # spaces instead of underscores
    }
    result = normalize_result(parsed, model_name="m")
    assert result.interest_level is InterestLevel.MEDIUM
    assert result.urgency is Urgency.HIGH
    assert result.sentiment is Sentiment.NEGATIVE
    assert result.recommended_next_action is NextAction.ESCALATE_TO_HUMAN


def test_normalize_result_falls_back_to_default_on_unknown_enum_value():
    parsed = {"interest_level": "SUPER_DUPER_HIGH", "urgency": "unknown"}
    result = normalize_result(parsed, model_name="m")
    assert result.interest_level is InterestLevel.NONE  # safe default, not a crash
    assert result.urgency is Urgency.LOW


def test_normalize_result_clamps_out_of_range_confidence():
    assert normalize_result({"confidence": 1.7}, model_name="m").confidence == 1.0
    assert normalize_result({"confidence": -0.3}, model_name="m").confidence == 0.0
    assert normalize_result({"confidence": "not a number"}, model_name="m").confidence == 0.0


def test_normalize_result_truncates_and_caps_objections():
    parsed = {
        "objections": ["ok"] * 20 + [None, 123, "  padded  "],  # noise mixed in
    }
    result = normalize_result(parsed, model_name="m")
    assert len(result.objections) == 8  # capped at _MAX_OBJECTIONS
    assert all(isinstance(o, str) for o in result.objections)


def test_normalize_result_drops_reply_draft_for_terminal_actions():
    for action in ("mark_won", "mark_lost", "no_action"):
        parsed = {
            "recommended_next_action": action,
            "recommended_reply_draft": "This should be discarded.",
        }
        result = normalize_result(parsed, model_name="m")
        assert result.recommended_reply_draft is None


def test_normalize_result_sets_follow_up_only_for_schedule_follow_up():
    parsed = {"recommended_next_action": "schedule_follow_up", "follow_up_in_days": 3}
    result = normalize_result(parsed, model_name="m")
    assert result.recommended_follow_up_at is not None

    parsed_no_followup = {"recommended_next_action": "send_reply", "follow_up_in_days": 3}
    result_no_followup = normalize_result(parsed_no_followup, model_name="m")
    assert result_no_followup.recommended_follow_up_at is None


def test_compute_follow_up_at_clamps_to_sane_window():
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # negative and absurdly large day counts both get clamped, not trusted
    assert _compute_follow_up_at(-5, now=now) == "2026-01-01T00:00:00+00:00"
    assert _compute_follow_up_at(9999, now=now) == "2026-01-31T00:00:00+00:00"
    # non-numeric input falls back to the conservative default (2 days)
    assert _compute_follow_up_at("soon", now=now) == "2026-01-03T00:00:00+00:00"
