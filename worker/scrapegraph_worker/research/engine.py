"""Orchestrates one company's research run: read its latest EnrichmentJob
-> run the agent -> write one ResearchJob record (append-only).

Mirrors `enrichment/engine.py`'s shape deliberately: one entry point that
never lets a single company's failure raise past the caller in a batch
run, and exactly one audit record per attempt.

Two hard preconditions, both of which fail loudly rather than degrading
into a lower-quality guess:

1. **No enrichment, no research.** Research without grounding material is
   just the model free-associating from a company name, which is exactly
   the failure mode this module exists to avoid. A company with no
   successful EnrichmentJob returns RESEARCH_FAILED with a clear reason
   (and `workflow/engine.py` knows to run enrichment first).
2. **No LLM configured, no research.** Unlike enrichment -- which has a
   genuine heuristic fallback (title/meta-description) -- there is no
   non-LLM way to produce pain-point hypotheses that would be worth
   anything. Rather than write a keyword-template "pain point" that looks
   like analysis but isn't, this returns RESEARCH_FAILED and says the LLM
   isn't configured.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..config import LLMSettings
from ..enrichment.models import (
    AIMaturityLevel,
    BuyingSignalHit,
    EnrichmentResult,
    GrowthIndicators,
    HiringSignal,
    TechStackHit,
)
from ..twenty_client import TwentyAPIError, TwentyClient
from .agent import run_research
from .models import ResearchGrounding, ResearchResult, ResearchStatus

logger = logging.getLogger(__name__)


def research_company(
    client: TwentyClient,
    company_id: str,
    *,
    llm_settings: LLMSettings,
    source_run_id: Optional[str] = None,
) -> ResearchResult:
    try:
        return _research_company_inner(
            client, company_id, llm_settings=llm_settings, source_run_id=source_run_id
        )
    except TwentyAPIError as exc:
        logger.exception("Twenty API error researching company %s", company_id)
        return ResearchResult(
            company_id=company_id, status=ResearchStatus.RESEARCH_FAILED, error_message=str(exc)
        )
    except Exception as exc:  # noqa: BLE001 - a bad company must not kill a batch run
        logger.exception("Unexpected error researching company %s", company_id)
        return ResearchResult(
            company_id=company_id, status=ResearchStatus.RESEARCH_FAILED, error_message=str(exc)
        )


def _research_company_inner(
    client: TwentyClient,
    company_id: str,
    *,
    llm_settings: LLMSettings,
    source_run_id: Optional[str],
) -> ResearchResult:
    if not llm_settings.is_configured:
        result = ResearchResult(
            company_id=company_id,
            status=ResearchStatus.RESEARCH_FAILED,
            error_message=(
                "LLM_BASE_URL / LLM_MODEL are not configured -- research produces inferences, and "
                "there is no meaningful non-LLM fallback for that (see research/engine.py)."
            ),
        )
        _write_research_job(client, result, source_run_id=source_run_id)
        return result

    company = client.get_record("companies", company_id, depth=0)
    if company is None:
        return ResearchResult(
            company_id=company_id,
            status=ResearchStatus.RESEARCH_FAILED,
            error_message="Company not found.",
        )

    enrichment_record = _latest_usable_enrichment(client, company_id)
    if enrichment_record is None:
        result = ResearchResult(
            company_id=company_id,
            status=ResearchStatus.RESEARCH_FAILED,
            error_message=(
                "No successful EnrichmentJob for this company -- run enrichment first. "
                "Research is deliberately never run without grounding material."
            ),
        )
        _write_research_job(client, result, source_run_id=source_run_id)
        return result

    enrichment = _rehydrate_enrichment(enrichment_record, company_id=company_id)
    grounding = _build_grounding(enrichment_record, enrichment)

    # Imported here rather than at module scope so this module stays
    # importable (and testable) without httpx, same as
    # enrichment/llm_synthesis.py does.
    from ..conversation.llm_client import LLMClient

    with LLMClient(llm_settings) as llm:
        result = run_research(
            enrichment,
            llm,
            company_id=company_id,
            company_name=company.get("name") or "",
            model_name=llm_settings.model,
        )

    result.grounding = grounding
    result.confidence = _score_confidence(result, grounding)
    result.clamp_confidence()

    _write_research_job(client, result, source_run_id=source_run_id)
    return result


def _latest_usable_enrichment(client: TwentyClient, company_id: str) -> Optional[dict]:
    """Most recent EnrichmentJob that actually produced something. A
    FAILED enrichment carries no grounding material, so it's skipped
    rather than researched against.
    """
    records = client.find_records(
        "enrichmentJobs",
        filter_query=f"company.id[eq]:{company_id}",
        limit=10,
        depth=0,
        order_by="createdAt[DescNullsLast]",
    )
    for record in records:
        if record.get("status") in {"SUCCEEDED", "PARTIAL"}:
            return record
    return None


def _rehydrate_enrichment(record: dict, *, company_id: str) -> EnrichmentResult:
    """Turns a flat EnrichmentJob CRM record back into the structured
    EnrichmentResult the prompt builder expects.

    Necessarily lossy: `techStack` was flattened to a comma-separated
    string and the signal fields to rendered markdown when
    `enrichment/engine.py` wrote them, so category/count/source detail
    doesn't survive the round trip. Buying signals are the exception --
    they're re-parsed back into structured hits including source URLs,
    because `agent.normalize_result` needs the exact excerpt/URL pairs to
    validate the model's interpretations against.
    """
    tech_stack = [
        TechStackHit(name=name.strip(), category="unknown", matched_on="(from EnrichmentJob record)")
        for name in (record.get("techStack") or "").split(",")
        if name.strip()
    ]

    buying_signals = _parse_rendered_buying_signals(record.get("buyingSignals") or "")

    hiring_signals: list[HiringSignal] = []
    for line in (record.get("hiringSignals") or "").splitlines():
        line = line.strip().lstrip("- ").strip()
        if not line or ":" not in line:
            continue
        department, _, rest = line.partition(":")
        count = 0
        for token in rest.split():
            if token.isdigit():
                count = int(token)
                break
        source_url = rest.split("(")[-1].rstrip(")").strip() if "(" in rest else ""
        if count:
            hiring_signals.append(
                HiringSignal(department=department.strip(), mention_count=count, source_url=source_url)
            )

    try:
        ai_maturity = AIMaturityLevel(record.get("aiMaturity") or "UNKNOWN")
    except ValueError:
        ai_maturity = AIMaturityLevel.UNKNOWN

    return EnrichmentResult(
        company_id=company_id,
        summary=record.get("summary"),
        tech_stack=tech_stack,
        hiring_signals=hiring_signals,
        buying_signals=buying_signals,
        growth_indicators=GrowthIndicators(open_role_mentions=sum(s.mention_count for s in hiring_signals)),
        ai_maturity=ai_maturity,
        sources_checked=[url.strip() for url in (record.get("sourcesChecked") or "").split(",") if url.strip()],
    )


def _parse_rendered_buying_signals(rendered: str) -> list[BuyingSignalHit]:
    """Inverse of `enrichment/engine.py::_render_buying_signals`, whose
    line format is:  - "keyword": "...excerpt..." (source_url)
    """
    hits: list[BuyingSignalHit] = []
    for line in rendered.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        try:
            keyword = line.split('"')[1]
            excerpt = line.split('": "')[1].rsplit('" (', 1)[0]
            source_url = line.rsplit("(", 1)[1].rstrip(")")
        except (IndexError, ValueError):
            continue
        hits.append(
            BuyingSignalHit(
                keyword=keyword,
                excerpt=excerpt.strip().strip("."),
                source_url=source_url.strip(),
            )
        )
    return hits


def _build_grounding(record: dict, enrichment: EnrichmentResult) -> ResearchGrounding:
    return ResearchGrounding(
        enrichment_job_id=record.get("id"),
        enrichment_status=record.get("status"),
        source_urls=enrichment.sources_checked,
        had_summary=bool(enrichment.summary),
        had_tech_stack=bool(enrichment.tech_stack),
        had_hiring_signals=bool(enrichment.hiring_signals),
        had_buying_signals=bool(enrichment.buying_signals),
    )


def _score_confidence(result: ResearchResult, grounding: ResearchGrounding) -> float:
    """Deterministic, from how much grounding the run had and how much of
    the model's output survived normalization -- never the model's own
    self-reported confidence (which this prompt doesn't even ask for).

    A run whose hypotheses were mostly dropped for missing citations is
    *less* trustworthy, and this reflects that rather than hiding it.
    """
    if result.status != ResearchStatus.RESEARCHED:
        return 0.0

    material = grounding.material_count / 4.0  # 0-1 across summary/tech/hiring/buying
    has_summary = 1.0 if result.summary else 0.0
    has_cited_hypotheses = 1.0 if result.pain_point_hypotheses else 0.0
    has_signal_reading = 1.0 if result.interpreted_buying_signals else 0.0

    return (0.45 * material) + (0.25 * has_summary) + (0.2 * has_cited_hypotheses) + (0.1 * has_signal_reading)


def _write_research_job(
    client: TwentyClient, result: ResearchResult, *, source_run_id: Optional[str]
) -> Optional[str]:
    fields = {
        "status": result.status.value,
        "source": "research-agent",
        "sourceRunId": source_run_id,
        "researchSummary": result.summary,
        "painPoints": _render_pain_points(result),
        "salesAngles": _render_sales_angles(result),
        "researchBuyingSignals": _render_buying_signals(result),
        "researchConfidence": round(result.confidence, 3),
        "grounding": _render_grounding(result),
        "modelUsed": result.model_used,
        "errorMessage": result.error_message,
        "company": {"id": result.company_id},
    }
    fields = {k: v for k, v in fields.items() if v is not None}

    try:
        created = client.create_record("researchJobs", fields)
        return created.get("id")
    except TwentyAPIError:
        # Same tolerant handling sync.py and enrichment/engine.py use --
        # a not-yet-installed custom object must not take down the run.
        logger.warning("Could not write ResearchJob (custom object may not be installed yet)")
        return None


def _render_pain_points(result: ResearchResult) -> Optional[str]:
    if not result.pain_point_hypotheses:
        return None
    lines = ["HYPOTHESES -- inferred, not confirmed. Validate before asserting any of this to the prospect."]
    lines += [f"- {p.hypothesis}\n  (derived from: {p.derived_from})" for p in result.pain_point_hypotheses]
    return "\n".join(lines)


def _render_sales_angles(result: ResearchResult) -> Optional[str]:
    if not result.sales_angle_hypotheses:
        return None
    lines = ["HYPOTHESES -- talking points for a human to adapt, not messages to send as-is."]
    lines += [
        f"- {a.angle}\n  (addresses: {a.addresses_pain_point} | derived from: {a.derived_from})"
        for a in result.sales_angle_hypotheses
    ]
    return "\n".join(lines)


def _render_buying_signals(result: ResearchResult) -> Optional[str]:
    if not result.interpreted_buying_signals:
        return None
    return "\n".join(
        f'- "{s.excerpt}" ({s.source_url})\n  reading: {s.interpretation}'
        for s in result.interpreted_buying_signals
    )


def _render_grounding(result: ResearchResult) -> Optional[str]:
    grounding = result.grounding
    if not grounding.enrichment_job_id and not grounding.source_urls:
        return None
    return json.dumps(
        {
            "enrichmentJobId": grounding.enrichment_job_id,
            "enrichmentStatus": grounding.enrichment_status,
            "sourceUrls": grounding.source_urls[:20],
            "materialsUsed": {
                "summary": grounding.had_summary,
                "techStack": grounding.had_tech_stack,
                "hiringSignals": grounding.had_hiring_signals,
                "buyingSignals": grounding.had_buying_signals,
            },
        }
    )
