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

from ..config import LLMSettings
from ..twenty_client import TwentyAPIError, TwentyClient
from . import signals, tech_stack, website_crawler
from .llm_synthesis import synthesize
from .models import EnrichmentResult, EnrichmentStatus

logger = logging.getLogger(__name__)


class EnrichmentError(RuntimeError):
    pass


def enrich_company(client: TwentyClient, company_id: str, *, llm_settings: LLMSettings) -> EnrichmentResult:
    try:
        return _enrich_company_inner(client, company_id, llm_settings=llm_settings)
    except TwentyAPIError as exc:
        logger.exception("Twenty API error enriching company %s", company_id)
        return EnrichmentResult(company_id=company_id, status=EnrichmentStatus.FAILED, error_message=str(exc))
    except Exception as exc:  # noqa: BLE001 - a bad company should not kill a batch run
        logger.exception("Unexpected error enriching company %s", company_id)
        return EnrichmentResult(company_id=company_id, status=EnrichmentStatus.FAILED, error_message=str(exc))


def _enrich_company_inner(client: TwentyClient, company_id: str, *, llm_settings: LLMSettings) -> EnrichmentResult:
    result = EnrichmentResult(company_id=company_id)

    domain = signals.resolve_company_domain(client, company_id)
    if not domain:
        result.status = EnrichmentStatus.FAILED
        result.error_message = "Company has no domain on file -- nothing to crawl."
        _write_enrichment_job(client, result)
        return result

    pages = website_crawler.crawl_company_site(domain)
    reachable = [p for p in pages if p.ok]
    result.sources_checked = [p.url for p in reachable]
    result.sources_failed = [p.url for p in pages if not p.ok]

    if not reachable:
        result.status = EnrichmentStatus.FAILED
        result.error_message = f"Could not reach any page on {domain} ({len(pages)} attempted)."
        _write_enrichment_job(client, result)
        return result

    result.tech_stack = tech_stack.detect_tech_stack(pages)
    result.hiring_signals = signals.detect_hiring_signals(pages)
    result.buying_signals = signals.detect_buying_signals(pages)
    result.growth_indicators = signals.compute_growth_indicators(client, company_id, result.hiring_signals)
    result.linkedin_signals = signals.compute_linkedin_derived_signals(client, company_id)

    synthesis = synthesize(pages, result.tech_stack, llm_settings=llm_settings)
    result.summary = synthesis.summary
    result.ai_maturity = synthesis.ai_maturity
    result.ai_maturity_reasoning = synthesis.reasoning

    result.status, result.confidence = _score_result(result, pages_attempted=len(pages), synthesis_confidence=synthesis.confidence)
    result.clamp_confidence()

    _write_enrichment_job(client, result)
    _update_company_last_enriched(client, company_id)

    return result


def _score_result(result: EnrichmentResult, *, pages_attempted: int, synthesis_confidence: float) -> tuple[EnrichmentStatus, float]:
    """Deterministic status/confidence from what was actually gathered --
    never an LLM-emitted number taken at face value (same principle as
    ICPScore.score, see icp-score.object.ts). Confidence is a weighted
    blend of: page reachability, whether any tech was detected, and the
    synthesis step's own self-reported confidence.
    """
    reachability = len(result.sources_checked) / pages_attempted if pages_attempted else 0.0
    has_tech = 1.0 if result.tech_stack else 0.0
    has_summary = 1.0 if result.summary else 0.0

    confidence = (0.35 * reachability) + (0.15 * has_tech) + (0.2 * has_summary) + (0.3 * synthesis_confidence)

    if not result.sources_checked:
        status = EnrichmentStatus.FAILED
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
