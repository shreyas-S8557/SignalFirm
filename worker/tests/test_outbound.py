"""Tests for Phase 6 (AI Outbound Messaging). No real LLM/network -- reuses
the same FakeLLMClient shape as test_conversation_analyzer.py, and
FakeTwentyClient for the drafting-engine integration test.
"""

from __future__ import annotations

import json

from scrapegraph_worker.config import LLMSettings
from scrapegraph_worker.outbound.engine import draft_outreach_for_company
from scrapegraph_worker.outbound.generator import generate_messages, normalize_result
from scrapegraph_worker.outbound.models import MessageChannel, OutboundStatus
from scrapegraph_worker.outbound.prompts import OutboundContext


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


_GOOD_COMPLETION = json.dumps(
    {
        "linkedin_connection_note": "Hi Jamie -- noticed Acme is scaling fast, would love to connect.",
        "linkedin_message": "Thanks for connecting! Saw Acme is hiring across engineering -- curious how you're handling onboarding at that pace.",
        "email_variant_a": {"subject": "Quick question about Acme's growth", "body": "Hi Jamie,\n\nBody A.\n\nBest,\nRep"},
        "email_variant_b": {"subject": "A different angle for Acme", "body": "Hi Jamie,\n\nBody B, different hook.\n\nBest,\nRep"},
        "meeting_request": {"subject": "15 min this week?", "body": "Would Tuesday or Wednesday afternoon work for a quick call?"},
        "call_script": {
            "opening": "Hi Jamie, got a quick minute?",
            "discovery_questions": ["What's the biggest bottleneck in your current process?"],
            "pitch": "We help teams like Acme move faster.",
            "objection_handling": ["Objection: too busy | Response: totally understand, 10 minutes max."],
            "closing": "Can we grab 15 minutes Thursday?",
        },
        "follow_up_sequence": [
            {"day_offset": 0, "channel": "LINKEDIN_CONNECTION", "purpose": "connect", "body": "Hi Jamie..."},
            {"day_offset": 3, "channel": "EMAIL", "purpose": "intro", "body": "Following up..."},
            {"day_offset": 8, "channel": "CALL", "purpose": "call attempt", "body": "Call script summary..."},
        ],
        "confidence": 0.72,
    }
)

_CTX = OutboundContext(
    company_name="Acme",
    person_name="Jamie Lee",
    person_title="VP Engineering",
    industry="SaaS",
    pain_points=["Hiring is outpacing onboarding capacity"],
    sales_angles=["Faster onboarding via automation"],
)


def test_generate_messages_happy_path():
    llm = FakeLLMClient(response=_GOOD_COMPLETION)
    result = generate_messages(_CTX, company_id="c1", person_id="p1", llm=llm, model_name="test-model")

    assert result.status == OutboundStatus.DRAFTED
    assert result.linkedin_connection_note
    assert len(result.linkedin_connection_note) <= 300
    assert len(result.email_variants) == 2
    assert result.email_variants[0].label == "A"
    assert result.meeting_request is not None
    assert result.call_script is not None
    assert result.call_script.discovery_questions
    assert len(result.follow_up_sequence) == 3
    assert result.follow_up_sequence[0].channel == MessageChannel.LINKEDIN_CONNECTION
    assert 0.0 <= result.confidence <= 1.0


def test_generate_messages_llm_error_returns_failed():
    llm = FakeLLMClient(raise_error=RuntimeError("boom"))
    from scrapegraph_worker.conversation.llm_client import LLMError

    llm._raise_error = LLMError("provider down")
    result = generate_messages(_CTX, company_id="c1", person_id="p1", llm=llm, model_name="test-model")

    assert result.status == OutboundStatus.FAILED
    assert result.error_message


def test_generate_messages_malformed_json_returns_failed():
    llm = FakeLLMClient(response="not json at all")
    result = generate_messages(_CTX, company_id="c1", person_id=None, llm=llm, model_name="test-model")
    assert result.status == OutboundStatus.FAILED


def test_normalize_result_drops_unknown_channel_in_sequence():
    data = {
        "linkedin_connection_note": "hi",
        "follow_up_sequence": [
            {"day_offset": 0, "channel": "CARRIER_PIGEON", "purpose": "x", "body": "y"},
            {"day_offset": 1, "channel": "EMAIL", "purpose": "x", "body": "y"},
        ],
        "confidence": 0.5,
    }
    result = normalize_result(data, company_id="c1", person_id=None, ctx=_CTX, model_name="m")
    assert len(result.follow_up_sequence) == 1
    assert result.follow_up_sequence[0].channel == MessageChannel.EMAIL


def test_normalize_result_empty_content_is_failed():
    result = normalize_result({"confidence": 0.9}, company_id="c1", person_id=None, ctx=_CTX, model_name="m")
    assert result.status == OutboundStatus.FAILED


def test_connection_note_over_300_chars_is_clipped():
    data = {"linkedin_connection_note": "x" * 500, "confidence": 0.5}
    result = normalize_result(data, company_id="c1", person_id=None, ctx=_CTX, model_name="m")
    assert len(result.linkedin_connection_note) <= 300


# ---------------------------------------------------------------------------
# engine.py -- draft_outreach_for_company
# ---------------------------------------------------------------------------


def test_draft_outreach_requires_llm_configured(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    result = draft_outreach_for_company(fake_client, company["id"], llm_settings=LLMSettings(base_url="", model=""))
    assert result.status == OutboundStatus.FAILED
    assert "not configured" in result.error_message


def test_draft_outreach_writes_note_and_targets(fake_client, monkeypatch):
    company = fake_client.create_record("companies", {"name": "Acme", "industry": "SaaS"})
    person = fake_client.create_record(
        "people",
        {"company": {"id": company["id"]}, "jobTitle": "VP Engineering", "name": {"firstName": "Jamie", "lastName": "Lee"}},
    )

    import scrapegraph_worker.outbound.engine as engine_module

    class _FakeLLMContext:
        def __enter__(self_inner):
            return FakeLLMClient(response=_GOOD_COMPLETION)

        def __exit__(self_inner, *exc):
            return False

    monkeypatch.setattr(engine_module, "LLMClient", lambda settings: _FakeLLMContext())

    settings = LLMSettings(base_url="http://fake", model="test-model")
    result = draft_outreach_for_company(fake_client, company["id"], llm_settings=settings)

    assert result.status == OutboundStatus.DRAFTED
    assert result.person_id == person["id"]
    assert result.note_id is not None
    assert len(fake_client.notes) == 1
    assert any(t.get("targetCompanyId") == company["id"] for t in fake_client.note_targets)
    assert any(t.get("targetPersonId") == person["id"] for t in fake_client.note_targets)
