"""Executes the single next automatable action for a company, based on its
derived stage (see `derive.py`). Idempotent and safe to call repeatedly --
calling it on a company past the automatable part of the pipeline is a
documented no-op, not an error.

As of Phase 5 there are two automatable actions (enrichment and research),
so `advance()` walks one step at a time: call it twice on a freshly
imported company to get it enriched and then researched. `advance_all()`
runs the chain to completion for callers who want the whole pipeline in
one go (that's what AUTO_ENRICH_ON_IMPORT / AUTO_RESEARCH_AFTER_ENRICHMENT
drive during an import job).
"""

from __future__ import annotations

import logging

from ..config import LLMSettings
from ..enrichment.engine import enrich_company
from ..enrichment.models import EnrichmentStatus
from ..icp.engine import score_company
from ..icp.models import ICPScoreResult
from ..outbound.engine import draft_outreach_for_company
from ..outbound.models import OutboundStatus
from ..research.engine import research_company
from ..research.models import ResearchStatus
from ..twenty_client import TwentyClient
from .derive import derive_workflow_state
from .models import WorkflowStage, WorkflowState, WorkflowStepResult

logger = logging.getLogger(__name__)

# Guard against an unexpected cycle in advance_all -- with four automatable
# actions today (enrich, research, ICP score, draft outreach), six
# iterations is generous headroom.
_MAX_CHAIN_STEPS = 6


def advance(client: TwentyClient, company_id: str, *, llm_settings: LLMSettings) -> WorkflowStepResult:
    state_before = derive_workflow_state(client, company_id)

    # Enrichment: first attempt, or retry after a failure (enrich_company
    # is idempotent -- it writes a new EnrichmentJob record either way).
    if state_before.stage in (WorkflowStage.IMPORTED, WorkflowStage.FAILED):
        return _run_enrichment_step(client, company_id, llm_settings=llm_settings, state_before=state_before)

    if state_before.stage in (WorkflowStage.ENRICHED, WorkflowStage.RESEARCH_FAILED):
        return _run_research_step(client, company_id, llm_settings=llm_settings, state_before=state_before)

    if state_before.stage in (WorkflowStage.PENDING_ICP_SCORE, WorkflowStage.ICP_SCORING_FAILED):
        return _run_icp_scoring_step(client, company_id, state_before=state_before)

    if state_before.stage in (WorkflowStage.PENDING_OUTREACH_DRAFT, WorkflowStage.OUTREACH_DRAFT_FAILED):
        return _run_outreach_draft_step(client, company_id, llm_settings=llm_settings, state_before=state_before)

    # Every other stage (OUTREACH_DRAFTED -- needs a human to send;
    # RECOMMENDATIONS_ACTIVE) has no automatable next step -- report the
    # state honestly rather than silently doing nothing.
    return WorkflowStepResult(
        company_id=company_id,
        stage_before=state_before.stage,
        stage_after=state_before.stage,
        action_taken="no_op",
        detail=state_before.blocked_reason or "Nothing automatable to do at this stage.",
    )


def advance_all(client: TwentyClient, company_id: str, *, llm_settings: LLMSettings) -> list[WorkflowStepResult]:
    """Repeatedly `advance()` until the company reaches a stage with no
    automatable action left. Returns every step taken, in order, so a
    caller can report exactly what happened rather than just the end state.
    """
    steps: list[WorkflowStepResult] = []
    for _ in range(_MAX_CHAIN_STEPS):
        step = advance(client, company_id, llm_settings=llm_settings)
        steps.append(step)
        if step.action_taken == "no_op" or step.stage_after == step.stage_before:
            break
    return steps


def _run_icp_scoring_step(
    client: TwentyClient, company_id: str, *, state_before: WorkflowState
) -> WorkflowStepResult:
    result: ICPScoreResult = score_company(client, company_id)
    state_after = derive_workflow_state(client, company_id)

    if result.error_message:
        return WorkflowStepResult(
            company_id=company_id,
            stage_before=state_before.stage,
            stage_after=state_after.stage,
            action_taken="ran_icp_scoring",
            detail=result.error_message,
            errors=[result.error_message],
        )

    return WorkflowStepResult(
        company_id=company_id,
        stage_before=state_before.stage,
        stage_after=state_after.stage,
        action_taken="ran_icp_scoring",
        detail=f"ICP score {result.score:.1f}/100 ({result.priority.value}), confidence={result.confidence:.2f}.",
    )


def _run_outreach_draft_step(
    client: TwentyClient, company_id: str, *, llm_settings: LLMSettings, state_before: WorkflowState
) -> WorkflowStepResult:
    result = draft_outreach_for_company(client, company_id, llm_settings=llm_settings)
    state_after = derive_workflow_state(client, company_id)

    if result.status != OutboundStatus.DRAFTED:
        return WorkflowStepResult(
            company_id=company_id,
            stage_before=state_before.stage,
            stage_after=state_after.stage,
            action_taken="ran_outreach_draft",
            detail=result.error_message,
            errors=[result.error_message] if result.error_message else [],
        )

    return WorkflowStepResult(
        company_id=company_id,
        stage_before=state_before.stage,
        stage_after=state_after.stage,
        action_taken="ran_outreach_draft",
        detail=f"Drafted outreach for {result.person_name or 'the top contact'} -- review before sending.",
    )


def _run_enrichment_step(
    client: TwentyClient, company_id: str, *, llm_settings: LLMSettings, state_before: WorkflowState
) -> WorkflowStepResult:
    result = enrich_company(client, company_id, llm_settings=llm_settings)
    state_after = derive_workflow_state(client, company_id)

    if result.status == EnrichmentStatus.FAILED:
        return WorkflowStepResult(
            company_id=company_id,
            stage_before=state_before.stage,
            stage_after=state_after.stage,
            action_taken="ran_enrichment",
            detail=result.error_message,
            errors=[result.error_message] if result.error_message else [],
        )

    return WorkflowStepResult(
        company_id=company_id,
        stage_before=state_before.stage,
        stage_after=state_after.stage,
        action_taken="ran_enrichment",
        detail=f"Enrichment {result.status.value.lower()} (confidence={result.confidence:.2f}).",
    )


def _run_research_step(
    client: TwentyClient, company_id: str, *, llm_settings: LLMSettings, state_before: WorkflowState
) -> WorkflowStepResult:
    result = research_company(client, company_id, llm_settings=llm_settings)
    state_after = derive_workflow_state(client, company_id)

    if result.status == ResearchStatus.RESEARCH_FAILED:
        return WorkflowStepResult(
            company_id=company_id,
            stage_before=state_before.stage,
            stage_after=state_after.stage,
            action_taken="ran_research",
            detail=result.error_message,
            errors=[result.error_message] if result.error_message else [],
        )

    return WorkflowStepResult(
        company_id=company_id,
        stage_before=state_before.stage,
        stage_after=state_after.stage,
        action_taken="ran_research",
        detail=(
            f"Research complete (confidence={result.confidence:.2f}, "
            f"{len(result.pain_point_hypotheses)} pain-point hypotheses, "
            f"{len(result.sales_angle_hypotheses)} sales-angle hypotheses)."
        ),
    )
