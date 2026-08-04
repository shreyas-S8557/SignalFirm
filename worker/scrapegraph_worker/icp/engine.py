"""Orchestrates one company's ICP scoring run: read its latest EnrichmentJob
+ ResearchJob + synced People count -> apply the rubric (see rubric.py) ->
write one ICPScore record (append-only, mirrors ResearchJob/EnrichmentJob)
plus the denormalized Company.latestIcpScore/latestIcpPriority fields.

Unlike research/engine.py, an enrichment run is NOT a hard precondition --
a company with no enrichment yet still gets scored (industry_fit and
company_size_fit can still contribute), just with lower `confidence` and
zero credit on the enrichment-dependent criteria. This is deliberate: ICP
fit is meant to be checkable the moment a company is imported, not gated
behind two other phases completing first, even though scoring right after
Research (when all the grounding is available) gives the most complete
picture.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..enrichment.models import AIMaturityLevel
from ..twenty_client import TwentyAPIError, TwentyClient
from .models import ICPScoreResult
from .rubric import RubricError, compute_icp_score, load_rubric

logger = logging.getLogger(__name__)


def score_company(client: TwentyClient, company_id: str, *, rubric_path: Optional[str] = None) -> ICPScoreResult:
    try:
        return _score_company_inner(client, company_id, rubric_path=rubric_path)
    except RubricError as exc:
        logger.error("ICP rubric error scoring company %s: %s", company_id, exc)
        return ICPScoreResult(company_id=company_id, error_message=str(exc))
    except TwentyAPIError as exc:
        logger.exception("Twenty API error scoring company %s", company_id)
        return ICPScoreResult(company_id=company_id, error_message=str(exc))
    except Exception as exc:  # noqa: BLE001 - a bad company must not kill a batch run
        logger.exception("Unexpected error scoring company %s", company_id)
        return ICPScoreResult(company_id=company_id, error_message=str(exc))


def _score_company_inner(client: TwentyClient, company_id: str, *, rubric_path: Optional[str]) -> ICPScoreResult:
    rubric = load_rubric(rubric_path)

    company = client.get_record("companies", company_id, depth=0)
    if company is None:
        return ICPScoreResult(company_id=company_id, error_message="Company not found.")

    enrichment = _latest_usable_enrichment(client, company_id)
    research = _latest_usable_research(client, company_id)
    people = client.find_records("people", filter_query=f"company.id[eq]:{company_id}", limit=500, depth=0)

    tech_stack_raw = (enrichment.get("techStack") or "") if enrichment else ""
    tech_stack_names = [t.strip() for t in tech_stack_raw.split(",") if t.strip()]
    buying_signal_count = _count_rendered_lines(enrichment.get("buyingSignals") if enrichment else None)
    hiring_signal_count = _count_rendered_lines(enrichment.get("hiringSignals") if enrichment else None)

    try:
        ai_maturity = AIMaturityLevel(enrichment.get("aiMaturity")) if enrichment and enrichment.get("aiMaturity") else AIMaturityLevel.UNKNOWN
    except ValueError:
        ai_maturity = AIMaturityLevel.UNKNOWN

    pain_point_count = _count_hypothesis_lines(research.get("painPoints") if research else None)
    sales_angle_count = _count_hypothesis_lines(research.get("salesAngles") if research else None)
    research_confidence = research.get("researchConfidence") if research else None

    result = compute_icp_score(
        company_id=company_id,
        industry=company.get("industry"),
        synced_people_count=len(people),
        buying_signal_count=buying_signal_count,
        hiring_signal_count=hiring_signal_count,
        tech_stack_names=tech_stack_names,
        ai_maturity=ai_maturity.value,
        pain_point_count=pain_point_count,
        sales_angle_count=sales_angle_count,
        research_confidence=research_confidence,
        had_enrichment=enrichment is not None,
        rubric=rubric,
    )

    _write_icp_score(client, result)
    return result


def _latest_usable_enrichment(client: TwentyClient, company_id: str) -> Optional[dict]:
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


def _latest_usable_research(client: TwentyClient, company_id: str) -> Optional[dict]:
    records = client.find_records(
        "researchJobs",
        filter_query=f"company.id[eq]:{company_id}",
        limit=20,
        depth=0,
        order_by="createdAt[DescNullsLast]",
    )
    for record in records:
        if record.get("status") == "RESEARCHED":
            return record
    return None


def _count_rendered_lines(rendered: Optional[str]) -> int:
    """Counts "- ..." lines in enrichment/engine.py's rendered markdown
    strings (buyingSignals, hiringSignals) without needing to fully
    re-parse them the way research/engine.py's rehydration does -- ICP
    scoring only needs a count, not the structured hits.
    """
    if not rendered:
        return 0
    return sum(1 for line in rendered.splitlines() if line.strip().startswith("-"))


def _count_hypothesis_lines(rendered: Optional[str]) -> int:
    """Same idea as `_count_rendered_lines`, but for research/engine.py's
    pain-point/sales-angle rendering, which prefixes the block with an
    explanatory non-hypothesis line that must not be counted.
    """
    if not rendered:
        return 0
    return sum(1 for line in rendered.splitlines() if line.strip().startswith("- "))


def _write_icp_score(client: TwentyClient, result: ICPScoreResult) -> Optional[str]:
    fields = {
        "score": result.score,
        "priority": result.priority.value,
        "reasoning": result.reasoning or None,
        "confidence": result.confidence,
        "rubricVersion": result.rubric_version,
        "company": {"id": result.company_id},
    }
    fields = {k: v for k, v in fields.items() if v is not None}

    record_id: Optional[str] = None
    try:
        created = client.create_record("icpScores", fields)
        record_id = created.get("id")
    except TwentyAPIError:
        logger.warning("Could not write ICPScore (custom object may not be installed yet)")

    # Denormalized "current value" on Company itself (see
    # company-latest-icp-score.field.ts) -- best-effort, same tolerant
    # handling as the record write above.
    try:
        client.update_record(
            "companies",
            result.company_id,
            {"latestIcpScore": result.score, "latestIcpPriority": result.priority.value},
        )
    except TwentyAPIError:
        logger.warning("Could not update Company.latestIcpScore/latestIcpPriority for %s", result.company_id)

    return record_id
