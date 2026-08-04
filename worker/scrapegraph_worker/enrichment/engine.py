"""Orchestrates one company's enrichment run: crawl -> tech stack -> hiring/
buying/growth/LinkedIn-derived signals -> LLM (or heuristic) synthesis ->
one EnrichmentJob record written to Twenty, plus Company.lastEnrichedAt.

Mirrors sync.py's shape deliberately: a single entry point
(`enrich_company`, cf. `sync_lead`) that never lets one company's failure
raise past the caller uncaught for a batch run, and writes exactly one
audit record (EnrichmentJob, cf. ResearchJob) per attempt.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from ..config import DataProviderSettings, LLMSettings
from ..twenty_client import TwentyAPIError, TwentyClient
from . import signals, tech_stack, website_crawler
from .llm_synthesis import synthesize
from .models import EnrichmentResult, EnrichmentStatus, TechStackHit
from .providers.models import ProviderCompanyProfile
from .providers.registry import build_providers

logger = logging.getLogger(__name__)


class EnrichmentError(RuntimeError):
    pass


def enrich_company(
    client: TwentyClient,
    company_id: str,
    *,
    llm_settings: LLMSettings,
    data_provider_settings: Optional[DataProviderSettings] = None,
) -> EnrichmentResult:
    try:
        return _enrich_company_inner(
            client, company_id, llm_settings=llm_settings, data_provider_settings=data_provider_settings
        )
    except TwentyAPIError as exc:
        logger.exception("Twenty API error enriching company %s", company_id)
        return EnrichmentResult(company_id=company_id, status=EnrichmentStatus.FAILED, error_message=str(exc))
    except Exception as exc:  # noqa: BLE001 - a bad company should not kill a batch run
        logger.exception("Unexpected error enriching company %s", company_id)
        return EnrichmentResult(company_id=company_id, status=EnrichmentStatus.FAILED, error_message=str(exc))


def _enrich_company_inner(
    client: TwentyClient,
    company_id: str,
    *,
    llm_settings: LLMSettings,
    data_provider_settings: Optional[DataProviderSettings],
) -> EnrichmentResult:
    result = EnrichmentResult(company_id=company_id)

    domain = signals.resolve_company_domain(client, company_id)
    if not domain:
        result.status = EnrichmentStatus.FAILED
        result.error_message = "Company has no domain on file -- nothing to crawl."
        _write_enrichment_job(client, result)
        return result

    # Lazily loaded from the environment when not passed explicitly, same
    # pattern as outbound/engine.py's OutboundSettings -- keeps every
    # existing caller (workflow/engine.py, api.py, tests) working
    # unchanged, since most of them only know about LLMSettings.
    if data_provider_settings is None:
        from ..config import load_settings

        data_provider_settings = load_settings().data_providers

    provider_profile = _lookup_provider_data(domain, data_provider_settings)

    pages = website_crawler.crawl_company_site(domain)
    reachable = [p for p in pages if p.ok]
    result.sources_checked = [p.url for p in reachable]
    result.sources_failed = [p.url for p in pages if not p.ok]

    if not reachable and provider_profile is None:
        result.status = EnrichmentStatus.FAILED
        result.error_message = f"Could not reach any page on {domain} ({len(pages)} attempted), and no data provider matched it either."
        _write_enrichment_job(client, result)
        return result

    result.tech_stack = tech_stack.detect_tech_stack(pages) if reachable else []
    result.hiring_signals = signals.detect_hiring_signals(pages) if reachable else []
    result.buying_signals = signals.detect_buying_signals(pages) if reachable else []
    result.growth_indicators = signals.compute_growth_indicators(client, company_id, result.hiring_signals)
    result.linkedin_signals = signals.compute_linkedin_derived_signals(client, company_id)

    if reachable:
        synthesis = synthesize(pages, result.tech_stack, llm_settings=llm_settings)
        result.summary = synthesis.summary
        result.ai_maturity = synthesis.ai_maturity
        result.ai_maturity_reasoning = synthesis.reasoning
        synthesis_confidence = synthesis.confidence
    else:
        # Crawl failed entirely, but a paid provider still matched this
        # domain -- report a thinner, provider-only result rather than
        # failing outright (see the `not reachable and provider_profile is
        # None` guard above for the case where neither succeeded).
        synthesis_confidence = 0.0

    if provider_profile is not None:
        result.tech_stack = _merge_tech_stack(result.tech_stack, provider_profile)
        result.summary = _merge_summary(result.summary, provider_profile)
        result.provider = f"{result.provider}+{provider_profile.source}"

    result.status, result.confidence = _score_result(
        result, pages_attempted=len(pages), synthesis_confidence=synthesis_confidence, had_provider_match=provider_profile is not None
    )
    result.clamp_confidence()

    _write_enrichment_job(client, result)
    _update_company_last_enriched(client, company_id)

    return result


def _lookup_provider_data(domain: str, settings: DataProviderSettings) -> Optional[ProviderCompanyProfile]:
    """Tries configured providers in priority order, first match wins.
    Returns `None` immediately (no calls at all) when nothing is
    configured -- the common case, and the reason this function's cost is
    zero for every deployment that hasn't set an API key.
    """
    if not settings.any_configured:
        return None

    providers = build_providers(settings)
    for provider in providers:
        try:
            profile = provider.lookup_company(domain)
        except Exception:  # noqa: BLE001 - one provider's bug must not affect the others or the crawl
            logger.exception("Data provider %s raised unexpectedly for %s", provider.name, domain)
            continue
        if profile is not None:
            logger.info("Enrichment for %s supplemented by %s", domain, provider.name)
            return profile
    return None


def _merge_tech_stack(existing: list[TechStackHit], profile: ProviderCompanyProfile) -> list[TechStackHit]:
    known_names = {hit.name.lower() for hit in existing}
    merged = list(existing)
    for name in profile.technologies:
        if name and name.lower() not in known_names:
            merged.append(TechStackHit(name=name, category="unknown", matched_on=f"{profile.source} organization enrichment"))
            known_names.add(name.lower())
    return merged


def _merge_summary(summary: Optional[str], profile: ProviderCompanyProfile) -> str:
    lines = [summary] if summary else []
    facts = []
    if profile.employee_count is not None:
        facts.append(f"~{profile.employee_count} employees")
    if profile.industry:
        facts.append(f"industry: {profile.industry}")
    if profile.estimated_annual_revenue:
        facts.append(f"est. revenue: {profile.estimated_annual_revenue}")
    if profile.founded_year:
        facts.append(f"founded {profile.founded_year}")
    if facts:
        lines.append(f"[{profile.source} firmographic data] " + ", ".join(facts) + ".")
    if profile.short_description and profile.short_description != summary:
        lines.append(f"[{profile.source}] {profile.short_description}")
    return "\n\n".join(lines)


def _score_result(
    result: EnrichmentResult, *, pages_attempted: int, synthesis_confidence: float, had_provider_match: bool = False
) -> tuple[EnrichmentStatus, float]:
    """Deterministic status/confidence from what was actually gathered --
    never an LLM-emitted number taken at face value (same principle as
    ICPScore.score, see icp-score.object.ts). Confidence is a weighted
    blend of: page reachability, whether any tech was detected, and the
    synthesis step's own self-reported confidence, plus a small flat bonus
    when a paid data provider corroborated the result -- independent
    verification is worth something, but deliberately not much: this
    service still doesn't take a provider's word over what it directly
    observed on the company's own site.
    """
    reachability = len(result.sources_checked) / pages_attempted if pages_attempted else 0.0
    has_tech = 1.0 if result.tech_stack else 0.0
    has_summary = 1.0 if result.summary else 0.0

    confidence = (0.35 * reachability) + (0.15 * has_tech) + (0.2 * has_summary) + (0.3 * synthesis_confidence)
    if had_provider_match:
        confidence += 0.1

    if not result.sources_checked and not had_provider_match:
        status = EnrichmentStatus.FAILED
    elif not result.sources_checked and had_provider_match:
        # Crawl failed, but a paid provider still matched -- a real,
        # externally-sourced result, just thinner than a full crawl+LLM
        # pass would produce.
        status = EnrichmentStatus.PARTIAL
    elif reachability >= 0.5 and result.summary:
        status = EnrichmentStatus.SUCCEEDED
    else:
        status = EnrichmentStatus.PARTIAL

    return status, confidence


def _write_enrichment_job(client: TwentyClient, result: EnrichmentResult) -> str | None:
    fields = {
        "status": result.status.value,
        "provider": result.provider,
        "confidence": round(result.confidence, 3),
        "errorMessage": result.error_message,
        "summary": result.summary,
        "techStack": ", ".join(hit.name for hit in result.tech_stack) or None,
        "hiringSignals": _render_hiring_signals(result),
        "buyingSignals": _render_buying_signals(result),
        "growthIndicators": _render_growth_indicators(result),
        "aiMaturity": result.ai_maturity.value,
        "sourcesChecked": ", ".join(result.sources_checked) or None,
        "company": {"id": result.company_id},
    }
    fields = {k: v for k, v in fields.items() if v is not None}

    try:
        created = client.create_record("enrichmentJobs", fields)
        return created.get("id")
    except TwentyAPIError:
        # EnrichmentJob custom object may not be synced into this
        # workspace yet -- same tolerant handling sync.py uses for
        # ResearchJob, so a missing/not-yet-installed custom object never
        # takes down enrichment itself.
        logger.warning("Could not write EnrichmentJob (custom object may not be installed yet)")
        return None


def _update_company_last_enriched(client: TwentyClient, company_id: str) -> None:
    try:
        client.update_record("companies", company_id, {"lastEnrichedAt": datetime.now(timezone.utc).isoformat()})
    except TwentyAPIError:
        logger.warning("Could not update Company.lastEnrichedAt for %s", company_id)


def _render_hiring_signals(result: EnrichmentResult) -> str | None:
    if not result.hiring_signals:
        return None
    lines = [f"- {s.department}: {s.mention_count} mention(s) ({s.source_url})" for s in result.hiring_signals]
    if result.growth_indicators:
        lines.append(f"- Synced People at this company: {result.growth_indicators.synced_people_count}")
    return "\n".join(lines)


def _render_buying_signals(result: EnrichmentResult) -> str | None:
    if not result.buying_signals:
        return None
    lines = [f'- "{s.keyword}": "...{s.excerpt}..." ({s.source_url})' for s in result.buying_signals[:15]]
    return "\n".join(lines)


def _render_growth_indicators(result: EnrichmentResult) -> str | None:
    parts = []
    if result.growth_indicators:
        g = result.growth_indicators
        parts.append(f"Synced People (headcount proxy): {g.synced_people_count}")
        parts.append(f"Open-role keyword mentions: {g.open_role_mentions}")
        parts.extend(g.notes)
    if result.linkedin_signals:
        li = result.linkedin_signals
        if li.seniority_mix:
            mix = ", ".join(f"{k}: {v}" for k, v in li.seniority_mix.items())
            parts.append(f"Seniority mix (from synced People): {mix}")
        if li.top_job_titles:
            parts.append(f"Top job titles seen: {', '.join(li.top_job_titles)}")
    return "\n".join(parts) if parts else None
