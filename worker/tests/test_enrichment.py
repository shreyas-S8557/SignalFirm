"""Tests for Phase 4 (Company Enrichment). No real network call or LLM --
`website_crawler.crawl_company_site` is monkeypatched to return canned
`CrawledPage`s (same approach `test_conversation_analyzer.py` takes with
`FakeLLMClient`), so tech-stack detection, signal detection, and the
engine's orchestration/scoring logic can all be verified offline.
"""

from __future__ import annotations

import json

import pytest

from scrapegraph_worker.config import LLMSettings
from scrapegraph_worker.enrichment import engine, llm_synthesis, signals, tech_stack
from scrapegraph_worker.enrichment.models import AIMaturityLevel, CrawledPage, EnrichmentStatus
from scrapegraph_worker.enrichment.scheduling import find_companies_due_for_enrichment

# ---------------------------------------------------------------------------
# tech_stack.py
# ---------------------------------------------------------------------------


def test_detect_tech_stack_matches_known_signatures():
    page = CrawledPage(
        url="https://acme.com/",
        status_code=200,
        html=(
            "<html><head>"
            '<script src="https://js.hs-scripts.com/12345.js"></script>'
            '<script src="https://www.google-analytics.com/analytics.js"></script>'
            '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/foo.css">'
            "</head><body>wp-content/uploads/logo.png</body></html>"
        ),
    )

    hits = tech_stack.detect_tech_stack([page])
    names = {hit.name for hit in hits}

    assert "HubSpot" in names
    assert "Google Analytics" in names
    assert "Cloudflare" in names
    assert "WordPress" in names


def test_detect_tech_stack_deduplicates_across_pages():
    page1 = CrawledPage(url="https://acme.com/", status_code=200, html='<script src="js.hs-scripts.com"></script>')
    page2 = CrawledPage(url="https://acme.com/about", status_code=200, html='<script src="js.hs-scripts.com"></script>')

    hits = tech_stack.detect_tech_stack([page1, page2])

    assert len([h for h in hits if h.name == "HubSpot"]) == 1


def test_detect_tech_stack_skips_unreachable_pages():
    page = CrawledPage(url="https://acme.com/", fetch_error="timed out")
    assert tech_stack.detect_tech_stack([page]) == []


def test_detect_tech_stack_reads_meta_generator():
    page = CrawledPage(
        url="https://acme.com/",
        status_code=200,
        html='<html><head><meta name="generator" content="Framer"></head></html>',
    )
    hits = tech_stack.detect_tech_stack([page])
    assert any(h.name == "Framer" for h in hits)


# ---------------------------------------------------------------------------
# signals.py -- hiring / buying signals
# ---------------------------------------------------------------------------


def test_detect_hiring_signals_counts_department_keywords():
    page = CrawledPage(
        url="https://acme.com/careers",
        status_code=200,
        text="We're hiring! Open roles: Senior Engineer, Backend Engineer, and an Account Executive.",
    )

    hits = signals.detect_hiring_signals([page])
    by_dept = {h.department: h.mention_count for h in hits}

    assert by_dept.get("Engineering", 0) == 2
    assert by_dept.get("Sales", 0) == 1


def test_detect_hiring_signals_ignores_non_careers_pages():
    page = CrawledPage(url="https://acme.com/pricing", status_code=200, text="engineer engineer engineer")
    assert signals.detect_hiring_signals([page]) == []


def test_detect_buying_signals_returns_excerpt_and_source():
    page = CrawledPage(
        url="https://acme.com/news",
        status_code=200,
        text="Acme is thrilled to announce it raised a $12M Series A led by Example Ventures to fuel growth.",
    )

    hits = signals.detect_buying_signals([page])

    assert any(h.keyword == "series a" for h in hits)
    hit = next(h for h in hits if h.keyword == "series a")
    assert "Series A" in hit.excerpt
    assert hit.source_url == "https://acme.com/news"


def test_detect_buying_signals_no_match_returns_empty():
    page = CrawledPage(url="https://acme.com/", status_code=200, text="Welcome to our totally normal homepage.")
    assert signals.detect_buying_signals([page]) == []


# ---------------------------------------------------------------------------
# signals.py -- LinkedIn-derived + growth signals (from already-synced People)
# ---------------------------------------------------------------------------


def test_compute_linkedin_derived_signals_from_synced_people(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "people",
        {
            "jobTitle": "Chief Technology Officer",
            "company": {"id": company["id"]},
            "linkedinLink": {"primaryLinkUrl": "https://linkedin.com/in/a"},
        },
    )
    fake_client.create_record(
        "people",
        {
            "jobTitle": "Sales Manager",
            "company": {"id": company["id"]},
            "linkedinLink": {"primaryLinkUrl": "https://linkedin.com/in/b"},
        },
    )
    fake_client.create_record("people", {"jobTitle": "Software Engineer", "company": {"id": company["id"]}})

    result = signals.compute_linkedin_derived_signals(fake_client, company["id"])

    assert result.people_with_linkedin_url == 2
    assert result.seniority_mix.get("C-Level") == 1
    assert result.seniority_mix.get("Manager") == 1
    assert result.seniority_mix.get("Individual Contributor") == 1


def test_compute_growth_indicators_reports_notes_when_empty(fake_client):
    company = fake_client.create_record("companies", {"name": "Empty Co"})
    growth = signals.compute_growth_indicators(fake_client, company["id"], hiring_signals=[])
    assert growth.synced_people_count == 0
    assert growth.open_role_mentions == 0
    assert len(growth.notes) == 2  # no people synced + no hiring mentions


def test_resolve_company_domain_strips_scheme():
    class _Client:
        def get_record(self, object_name_plural, record_id, *, depth=0):
            return {"domainName": {"primaryLinkUrl": "https://www.acme.com/about"}}

    assert signals.resolve_company_domain(_Client(), "company-1") == "www.acme.com"


def test_resolve_company_domain_none_when_no_domain(fake_client):
    company = fake_client.create_record("companies", {"name": "No Domain Co"})
    assert signals.resolve_company_domain(fake_client, company["id"]) is None


# ---------------------------------------------------------------------------
# llm_synthesis.py
# ---------------------------------------------------------------------------


def test_synthesize_heuristic_fallback_uses_title_and_meta_description():
    page = CrawledPage(
        url="https://acme.com/",
        status_code=200,
        html=(
            "<html><head><title>Acme Corp</title>"
            '<meta name="description" content="We build widgets for enterprises.">'
            "</head></html>"
        ),
        text="Acme Corp We build widgets for enterprises.",
    )

    result = llm_synthesis.synthesize([page], [], llm_settings=LLMSettings(base_url="", model=""))

    assert result.summary == "Acme Corp. We build widgets for enterprises."
    assert result.ai_maturity == AIMaturityLevel.NONE_OBSERVED
    assert result.confidence < 0.5  # heuristic path never claims high confidence


def test_synthesize_heuristic_detects_ai_keywords():
    page = CrawledPage(
        url="https://acme.com/",
        status_code=200,
        html="<html><head><title>Acme AI</title></head></html>",
        text="Acme uses artificial intelligence and machine learning throughout our generative ai platform.",
    )

    result = llm_synthesis.synthesize([page], [], llm_settings=LLMSettings(base_url="", model=""))

    assert result.ai_maturity in (AIMaturityLevel.EXPLORING, AIMaturityLevel.ADOPTING)


def test_synthesize_uses_llm_when_configured(monkeypatch):
    class FakeLLMClient:
        def __init__(self, settings):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def complete_json(self, *, system_prompt, user_prompt):
            return json.dumps(
                {
                    "summary": "Acme sells widgets to enterprises.",
                    "ai_maturity": "ADOPTING",
                    "ai_maturity_reasoning": "Careers page lists two ML engineer roles.",
                    "confidence": 0.8,
                }
            )

    monkeypatch.setattr("scrapegraph_worker.conversation.llm_client.LLMClient", FakeLLMClient)

    page = CrawledPage(url="https://acme.com/", status_code=200, text="Acme sells widgets.")
    settings = LLMSettings(base_url="https://example.com", model="test-model")

    result = llm_synthesis.synthesize([page], [], llm_settings=settings)

    assert result.summary == "Acme sells widgets to enterprises."
    assert result.ai_maturity == AIMaturityLevel.ADOPTING
    assert result.confidence == 0.8


def test_synthesize_falls_back_when_llm_errors(monkeypatch):
    class FailingLLMClient:
        def __init__(self, settings):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def complete_json(self, *, system_prompt, user_prompt):
            raise RuntimeError("backend unreachable")

    monkeypatch.setattr("scrapegraph_worker.conversation.llm_client.LLMClient", FailingLLMClient)

    page = CrawledPage(
        url="https://acme.com/",
        status_code=200,
        html="<html><head><title>Acme</title></head></html>",
        text="Acme",
    )
    settings = LLMSettings(base_url="https://example.com", model="test-model")

    result = llm_synthesis.synthesize([page], [], llm_settings=settings)

    # Falls back to the heuristic path rather than raising.
    assert result.summary == "Acme"


# ---------------------------------------------------------------------------
# engine.py -- end-to-end orchestration against FakeTwentyClient
# ---------------------------------------------------------------------------


def _homepage_and_careers_pages():
    return [
        CrawledPage(
            url="https://acme.com/",
            status_code=200,
            html='<html><head><title>Acme</title><script src="js.hs-scripts.com"></script></head></html>',
            text="Acme builds tools for accountants.",
        ),
        CrawledPage(
            url="https://acme.com/careers",
            status_code=200,
            html="<html></html>",
            text="We're hiring! Open roles: Software Engineer, Software Engineer.",
        ),
    ]


def test_enrich_company_happy_path_writes_enrichment_job_and_updates_company(fake_client, monkeypatch):
    company = fake_client.create_record(
        "companies", {"name": "Acme", "domainName": {"primaryLinkUrl": "https://acme.com"}}
    )
    monkeypatch.setattr(engine.website_crawler, "crawl_company_site", lambda domain, **kw: _homepage_and_careers_pages())

    result = engine.enrich_company(fake_client, company["id"], llm_settings=LLMSettings(base_url="", model=""))

    assert result.status in (EnrichmentStatus.SUCCEEDED, EnrichmentStatus.PARTIAL)
    assert result.summary
    assert "HubSpot" in [h.name for h in result.tech_stack]
    assert len(fake_client.enrichment_jobs) == 1
    job = next(iter(fake_client.enrichment_jobs.values()))
    assert job["status"] == result.status.value
    assert job["company"] == {"id": company["id"]}
    assert fake_client.companies[company["id"]].get("lastEnrichedAt")


def test_enrich_company_without_domain_fails_gracefully(fake_client):
    company = fake_client.create_record("companies", {"name": "No Domain Co"})

    result = engine.enrich_company(fake_client, company["id"], llm_settings=LLMSettings(base_url="", model=""))

    assert result.status == EnrichmentStatus.FAILED
    assert "domain" in (result.error_message or "").lower()
    assert len(fake_client.enrichment_jobs) == 1
    # No site to crawl -- Company.lastEnrichedAt must NOT be silently set.
    assert not fake_client.companies[company["id"]].get("lastEnrichedAt")


def test_enrich_company_all_pages_unreachable_fails_gracefully(fake_client, monkeypatch):
    company = fake_client.create_record(
        "companies", {"name": "Down Co", "domainName": {"primaryLinkUrl": "https://down.example"}}
    )
    unreachable = [CrawledPage(url="https://down.example/", fetch_error="connection refused")]
    monkeypatch.setattr(engine.website_crawler, "crawl_company_site", lambda domain, **kw: unreachable)

    result = engine.enrich_company(fake_client, company["id"], llm_settings=LLMSettings(base_url="", model=""))

    assert result.status == EnrichmentStatus.FAILED
    assert result.sources_checked == []


def test_enrich_company_never_raises_on_unexpected_error(fake_client, monkeypatch):
    company = fake_client.create_record(
        "companies", {"name": "Acme", "domainName": {"primaryLinkUrl": "https://acme.com"}}
    )

    def _boom(domain, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(engine.website_crawler, "crawl_company_site", _boom)

    result = engine.enrich_company(fake_client, company["id"], llm_settings=LLMSettings(base_url="", model=""))

    assert result.status == EnrichmentStatus.FAILED
    assert "boom" in (result.error_message or "")


def test_enrich_company_tolerates_missing_enrichment_job_object(fake_client, monkeypatch):
    """If the EnrichmentJob custom object isn't installed in this workspace
    yet, create_record raises TwentyAPIError -- enrichment should still
    complete rather than blow up (mirrors sync.py's ResearchJob handling).
    """
    from scrapegraph_worker.twenty_client import TwentyAPIError

    company = fake_client.create_record(
        "companies", {"name": "Acme", "domainName": {"primaryLinkUrl": "https://acme.com"}}
    )
    monkeypatch.setattr(engine.website_crawler, "crawl_company_site", lambda domain, **kw: _homepage_and_careers_pages())

    original_create_record = fake_client.create_record

    def _raise_for_enrichment_jobs(object_name_plural, fields):
        if object_name_plural == "enrichmentJobs":
            raise TwentyAPIError(404, "custom object not found")
        return original_create_record(object_name_plural, fields)

    monkeypatch.setattr(fake_client, "create_record", _raise_for_enrichment_jobs)

    result = engine.enrich_company(fake_client, company["id"], llm_settings=LLMSettings(base_url="", model=""))

    # Still computed successfully -- just couldn't persist the audit record.
    assert result.status in (EnrichmentStatus.SUCCEEDED, EnrichmentStatus.PARTIAL)
    assert len(fake_client.enrichment_jobs) == 0


# ---------------------------------------------------------------------------
# scheduling.py
# ---------------------------------------------------------------------------


def test_find_companies_due_for_enrichment_includes_never_enriched(fake_client):
    never_enriched = fake_client.create_record("companies", {"name": "Never Enriched"})
    recently_enriched = fake_client.create_record(
        "companies", {"name": "Recently Enriched", "lastEnrichedAt": "2099-01-01T00:00:00+00:00"}
    )

    due = find_companies_due_for_enrichment(fake_client, stale_after_days=30, max_results=50)

    assert never_enriched["id"] in due
    assert recently_enriched["id"] not in due


def test_find_companies_due_for_enrichment_includes_stale():
    class _Client:
        def find_records(self, object_name_plural, *, limit=25, depth=0, order_by=None, **kw):
            return [
                {"id": "stale-1", "lastEnrichedAt": "2020-01-01T00:00:00+00:00"},
                {"id": "fresh-1", "lastEnrichedAt": "2099-01-01T00:00:00+00:00"},
            ]

    due = find_companies_due_for_enrichment(_Client(), stale_after_days=30, max_results=50)

    assert due == ["stale-1"]


def test_find_companies_due_for_enrichment_respects_max_results():
    class _Client:
        def find_records(self, object_name_plural, *, limit=25, depth=0, order_by=None, **kw):
            return [{"id": f"co-{i}"} for i in range(10)]

    due = find_companies_due_for_enrichment(_Client(), stale_after_days=30, max_results=3)

    assert len(due) == 3
