"""Tests for enrichment/providers/. Uses httpx.MockTransport so no real
network call happens -- same offline-first approach as every other test
in this suite.
"""

from __future__ import annotations

import httpx
import pytest

from scrapegraph_worker.config import DataProviderSettings
from scrapegraph_worker.enrichment import engine as enrichment_engine
from scrapegraph_worker.enrichment.models import CrawledPage
from scrapegraph_worker.enrichment.providers.apollo import ApolloProvider
from scrapegraph_worker.enrichment.providers.people_data_labs import PeopleDataLabsProvider
from scrapegraph_worker.enrichment.providers.registry import build_providers


def _client_with_response(status_code: int, json_body: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body or {})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_apollo_provider_parses_organization():
    body = {
        "organization": {
            "estimated_num_employees": 120,
            "industry": "computer software",
            "annual_revenue": 5000000,
            "founded_year": 2015,
            "technology_names": ["Segment", "HubSpot"],
            "linkedin_url": "https://linkedin.com/company/acme",
            "short_description": "Acme builds things.",
        }
    }
    provider = ApolloProvider("fake-key", http_client=_client_with_response(200, body))
    profile = provider.lookup_company("acme.com")

    assert profile is not None
    assert profile.source == "apollo"
    assert profile.employee_count == 120
    assert profile.estimated_annual_revenue == "$5,000,000"
    assert "Segment" in profile.technologies


def test_apollo_provider_returns_none_on_404():
    provider = ApolloProvider("fake-key", http_client=_client_with_response(404))
    assert provider.lookup_company("nonexistent.example") is None


def test_apollo_provider_returns_none_on_error_status():
    provider = ApolloProvider("fake-key", http_client=_client_with_response(500))
    assert provider.lookup_company("acme.com") is None


def test_apollo_provider_never_raises_on_network_error():
    def handler(request: httpx.Request):
        raise httpx.ConnectError("boom", request=request)

    provider = ApolloProvider("fake-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider.lookup_company("acme.com") is None


def test_pdl_provider_parses_company():
    body = {
        "status": 200,
        "employee_count": 340,
        "industry": "internet",
        "inferred_revenue": "10M-50M",
        "founded": 2012,
        "tags": ["saas", "b2b"],
        "linkedin_url": "https://linkedin.com/company/acme",
        "summary": "Acme summary.",
    }
    provider = PeopleDataLabsProvider("fake-key", http_client=_client_with_response(200, body))
    profile = provider.lookup_company("acme.com")

    assert profile is not None
    assert profile.source == "people_data_labs"
    assert profile.employee_count == 340
    assert "saas" in profile.technologies


def test_pdl_provider_returns_none_on_404():
    provider = PeopleDataLabsProvider("fake-key", http_client=_client_with_response(404))
    assert provider.lookup_company("nonexistent.example") is None


def test_registry_respects_priority_order():
    settings = DataProviderSettings(
        apollo_api_key="a", people_data_labs_api_key="b", priority=("people_data_labs", "apollo")
    )
    providers = build_providers(settings)
    assert [p.name for p in providers] == ["people_data_labs", "apollo"]


def test_registry_skips_unconfigured_providers():
    settings = DataProviderSettings(apollo_api_key="", people_data_labs_api_key="b")
    providers = build_providers(settings)
    assert [p.name for p in providers] == ["people_data_labs"]


def test_registry_empty_when_nothing_configured():
    settings = DataProviderSettings(apollo_api_key="", people_data_labs_api_key="")
    assert build_providers(settings) == []
    assert not settings.any_configured


# ---------------------------------------------------------------------------
# engine.py merge behavior
# ---------------------------------------------------------------------------


class _FakeProvider:
    name = "apollo"

    def __init__(self, profile):
        self._profile = profile

    def lookup_company(self, domain):
        return self._profile


def _reachable_pages():
    return [
        CrawledPage(url="https://acme.com/", status_code=200, html="<html><head><title>Acme</title></head></html>", text="Acme builds things.")
    ]


def test_enrichment_merges_provider_tech_and_summary(fake_client, monkeypatch):
    from scrapegraph_worker.enrichment.providers.models import ProviderCompanyProfile

    company = fake_client.create_record("companies", {"name": "Acme", "domainName": {"primaryLinkUrl": "https://acme.com"}})

    profile = ProviderCompanyProfile(
        source="apollo", employee_count=50, industry="SaaS", technologies=["Segment"], short_description="An SDK company."
    )
    monkeypatch.setattr(enrichment_engine, "_lookup_provider_data", lambda domain, settings: profile)
    monkeypatch.setattr(enrichment_engine.website_crawler, "crawl_company_site", lambda domain, **kw: _reachable_pages())

    result = enrichment_engine.enrich_company(
        fake_client, company["id"], llm_settings=_unconfigured_llm(), data_provider_settings=DataProviderSettings()
    )

    assert any(hit.name == "Segment" for hit in result.tech_stack)
    assert "apollo" in result.provider
    assert "50 employees" in (result.summary or "")


def test_enrichment_provider_only_result_when_crawl_fails(fake_client, monkeypatch):
    from scrapegraph_worker.enrichment.providers.models import ProviderCompanyProfile
    from scrapegraph_worker.enrichment.models import EnrichmentStatus

    company = fake_client.create_record("companies", {"name": "Acme", "domainName": {"primaryLinkUrl": "https://acme.com"}})

    profile = ProviderCompanyProfile(source="apollo", employee_count=10)
    monkeypatch.setattr(enrichment_engine, "_lookup_provider_data", lambda domain, settings: profile)
    monkeypatch.setattr(
        enrichment_engine.website_crawler,
        "crawl_company_site",
        lambda domain, **kw: [CrawledPage(url="https://acme.com/", status_code=500, fetch_error="server error")],
    )

    result = enrichment_engine.enrich_company(
        fake_client, company["id"], llm_settings=_unconfigured_llm(), data_provider_settings=DataProviderSettings()
    )

    assert result.status == EnrichmentStatus.PARTIAL


def _unconfigured_llm():
    from scrapegraph_worker.config import LLMSettings

    return LLMSettings(base_url="", model="")
