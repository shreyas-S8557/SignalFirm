"""Tests for Phase 5 (Research Automation). No real LLM or network --
`FakeLLMClient` mirrors the one in test_conversation_analyzer.py.

The heaviest coverage here is on `agent.normalize_result`'s rejection
paths, because that function is the only thing standing between a model
that confidently invents a fact and that fact landing on a real company's
CRM record.
"""

from __future__ import annotations

import json

from scrapegraph_worker.config import LLMSettings
from scrapegraph_worker.enrichment.models import (
    BuyingSignalHit,
    EnrichmentResult,
    HiringSignal,
    TechStackHit,
)
from scrapegraph_worker.research import engine as research_engine
from scrapegraph_worker.research.agent import normalize_result, run_research
from scrapegraph_worker.research.models import ResearchGrounding, ResearchStatus
from scrapegraph_worker.research.prompts import build_user_prompt

_CONFIGURED_LLM = LLMSettings(base_url="https://example.com", model="test-model")


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

    # Context-manager surface so it can stand in for LLMClient in engine.py
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _enrichment(**overrides) -> EnrichmentResult:
    defaults = dict(
        company_id="company-1",
        summary="Acme builds accounting software for small firms.",
        tech_stack=[TechStackHit(name="HubSpot", category="Marketing", matched_on="script src")],
        hiring_signals=[HiringSignal(department="Engineering", mention_count=3, source_url="https://acme.com/careers")],
        buying_signals=[
            BuyingSignalHit(
                keyword="series a",
                excerpt="Acme raised a Series A led by Example Ventures",
                source_url="https://acme.com/news",
            )
        ],
        sources_checked=["https://acme.com/", "https://acme.com/careers"],
    )
    defaults.update(overrides)
    return EnrichmentResult(**defaults)


def _good_payload() -> dict:
    return {
        "summary": "Acme sells accounting software to small firms.",
        "pain_points": [
            {
                "hypothesis": "May be outgrowing their current reporting tooling",
                "derived_from": "careers page lists 3 open Engineering roles",
            }
        ],
        "sales_angles": [
            {
                "angle": "Ask how they're handling reporting load as the team grows",
                "addresses_pain_point": "outgrowing reporting tooling",
                "derived_from": "3 open Engineering roles plus recent Series A",
            }
        ],
        "buying_signals": [
            {
                "excerpt": "Acme raised a Series A led by Example Ventures",
                "source_url": "https://acme.com/news",
                "interpretation": "Fresh funding often precedes tooling purchases",
            }
        ],
    }


# ---------------------------------------------------------------------------
# prompts.py
# ---------------------------------------------------------------------------


def test_build_user_prompt_includes_available_sections():
    prompt = build_user_prompt(_enrichment(), company_name="Acme")
    assert "Acme" in prompt
    assert "HubSpot" in prompt
    assert "Engineering" in prompt
    assert "Series A" in prompt


def test_build_user_prompt_omits_absent_sections():
    sparse = _enrichment(summary=None, tech_stack=[], hiring_signals=[], buying_signals=[])
    prompt = build_user_prompt(sparse, company_name="Acme")
    assert "Detected technologies" not in prompt
    assert "Hiring signals" not in prompt
    assert "Buying-signal excerpts" not in prompt


# ---------------------------------------------------------------------------
# agent.py -- happy path
# ---------------------------------------------------------------------------


def test_run_research_happy_path():
    client = FakeLLMClient(response=json.dumps(_good_payload()))
    result = run_research(_enrichment(), client, company_id="company-1", company_name="Acme", model_name="test-model")

    assert result.status == ResearchStatus.RESEARCHED
    assert result.summary
    assert len(result.pain_point_hypotheses) == 1
    assert len(result.sales_angle_hypotheses) == 1
    assert len(result.interpreted_buying_signals) == 1
    assert result.model_used == "test-model"


def test_run_research_handles_markdown_fenced_json():
    client = FakeLLMClient(response=f"```json\n{json.dumps(_good_payload())}\n```")
    result = run_research(_enrichment(), client, company_id="company-1", company_name="Acme")
    assert result.status == ResearchStatus.RESEARCHED


def test_run_research_returns_failed_on_llm_error():
    client = FakeLLMClient(raise_error=RuntimeError("backend down"))
    result = run_research(_enrichment(), client, company_id="company-1", company_name="Acme")
    assert result.status == ResearchStatus.RESEARCH_FAILED
    assert "backend down" in (result.error_message or "")


def test_run_research_returns_failed_on_unparseable_json():
    client = FakeLLMClient(response="I'm afraid I can't do that.")
    result = run_research(_enrichment(), client, company_id="company-1", company_name="Acme")
    assert result.status == ResearchStatus.RESEARCH_FAILED


# ---------------------------------------------------------------------------
# agent.py -- the rejection paths that keep fabrications out of the CRM
# ---------------------------------------------------------------------------


def test_uncited_pain_points_are_dropped():
    payload = _good_payload()
    payload["pain_points"] = [
        {"hypothesis": "They are losing money", "derived_from": ""},
        {"hypothesis": "They need a CRM", "derived_from": "n/a"},
        {"hypothesis": "They may need better reporting", "derived_from": "3 open Engineering roles listed"},
    ]
    result = normalize_result(payload, _enrichment(), company_id="company-1")

    assert len(result.pain_point_hypotheses) == 1
    assert result.pain_point_hypotheses[0].derived_from == "3 open Engineering roles listed"


def test_uncited_sales_angles_are_dropped():
    payload = _good_payload()
    payload["sales_angles"] = [{"angle": "Just call them", "addresses_pain_point": "x", "derived_from": "-"}]
    result = normalize_result(payload, _enrichment(), company_id="company-1")
    assert result.sales_angle_hypotheses == []


def test_invented_buying_signal_excerpt_is_dropped():
    """The model must not be able to supply its own quote -- only
    interpret excerpts that were genuinely in the enrichment input.
    """
    payload = _good_payload()
    payload["buying_signals"] = [
        {
            "excerpt": "Acme announced a $50M Series C and 200 new hires",  # never in the input
            "source_url": "https://acme.com/news",
            "interpretation": "Major expansion underway",
        }
    ]
    result = normalize_result(payload, _enrichment(), company_id="company-1")
    assert result.interpreted_buying_signals == []


def test_reworded_buying_signal_excerpt_is_dropped():
    payload = _good_payload()
    payload["buying_signals"][0]["excerpt"] = "Acme raised a Series A (led by Example Ventures)"
    result = normalize_result(payload, _enrichment(), company_id="company-1")
    assert result.interpreted_buying_signals == []


def test_list_lengths_are_capped_regardless_of_model_output():
    payload = _good_payload()
    payload["pain_points"] = [
        {"hypothesis": f"Hypothesis {i}", "derived_from": f"grounded in observation number {i}"} for i in range(20)
    ]
    result = normalize_result(payload, _enrichment(), company_id="company-1")
    assert len(result.pain_point_hypotheses) <= 5


def test_non_dict_items_are_skipped():
    payload = _good_payload()
    payload["pain_points"] = ["just a string", None, 42]
    result = normalize_result(payload, _enrichment(), company_id="company-1")
    assert result.pain_point_hypotheses == []


# ---------------------------------------------------------------------------
# engine.py -- confidence scoring
# ---------------------------------------------------------------------------


def test_confidence_is_higher_with_more_grounding_material():
    rich = ResearchGrounding(had_summary=True, had_tech_stack=True, had_hiring_signals=True, had_buying_signals=True)
    thin = ResearchGrounding(had_summary=True)

    payload = _good_payload()
    result_rich = normalize_result(payload, _enrichment(), company_id="c1")
    result_thin = normalize_result(payload, _enrichment(), company_id="c1")

    assert research_engine._score_confidence(result_rich, rich) > research_engine._score_confidence(result_thin, thin)


def test_confidence_is_zero_for_failed_research():
    result = normalize_result(_good_payload(), _enrichment(), company_id="c1")
    result.status = ResearchStatus.RESEARCH_FAILED
    grounding = ResearchGrounding(had_summary=True, had_tech_stack=True)
    assert research_engine._score_confidence(result, grounding) == 0.0


# ---------------------------------------------------------------------------
# engine.py -- preconditions and Twenty round trip
# ---------------------------------------------------------------------------


def test_research_fails_without_llm_configured(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "summary": "x", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )

    result = research_engine.research_company(
        fake_client, company["id"], llm_settings=LLMSettings(base_url="", model="")
    )

    assert result.status == ResearchStatus.RESEARCH_FAILED
    assert "not configured" in (result.error_message or "").lower()
    # Still writes an audit record so the failure is visible in the CRM.
    assert len(fake_client.research_jobs) == 1


def test_research_fails_without_enrichment_grounding(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})

    result = research_engine.research_company(fake_client, company["id"], llm_settings=_CONFIGURED_LLM)

    assert result.status == ResearchStatus.RESEARCH_FAILED
    assert "enrichment" in (result.error_message or "").lower()


def test_research_ignores_failed_enrichment_records(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "FAILED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )

    result = research_engine.research_company(fake_client, company["id"], llm_settings=_CONFIGURED_LLM)

    assert result.status == ResearchStatus.RESEARCH_FAILED
    assert "enrichment" in (result.error_message or "").lower()


def test_research_writes_research_job_record(fake_client, monkeypatch):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {
            "status": "SUCCEEDED",
            "summary": "Acme builds accounting software.",
            "techStack": "HubSpot, WordPress",
            "buyingSignals": '- "series a": "...Acme raised a Series A led by Example Ventures..." (https://acme.com/news)',
            "sourcesChecked": "https://acme.com/",
            "company": {"id": company["id"]},
            "createdAt": "2026-08-01T00:00:00Z",
        },
    )

    monkeypatch.setattr(
        "scrapegraph_worker.conversation.llm_client.LLMClient",
        lambda settings: FakeLLMClient(response=json.dumps(_good_payload())),
    )

    result = research_engine.research_company(fake_client, company["id"], llm_settings=_CONFIGURED_LLM)

    assert result.status == ResearchStatus.RESEARCHED
    assert result.grounding.enrichment_job_id is not None
    assert len(fake_client.research_jobs) == 1

    written = next(iter(fake_client.research_jobs.values()))
    assert written["status"] == "RESEARCHED"
    assert written["source"] == "research-agent"
    # Hypothesis framing must survive into what's actually stored in the CRM.
    assert "HYPOTHESES" in written["painPoints"]
    assert "HYPOTHESES" in written["salesAngles"]


def test_rendered_buying_signals_round_trip(fake_client):
    """enrichment/engine.py renders buying signals to a string; research
    has to parse them back well enough that agent.py can validate the
    model's interpretations against real excerpts.
    """
    rendered = '- "series a": "...Acme raised a Series A led by Example Ventures..." (https://acme.com/news)'
    hits = research_engine._parse_rendered_buying_signals(rendered)

    assert len(hits) == 1
    assert hits[0].keyword == "series a"
    assert "Series A" in hits[0].excerpt
    assert hits[0].source_url == "https://acme.com/news"
