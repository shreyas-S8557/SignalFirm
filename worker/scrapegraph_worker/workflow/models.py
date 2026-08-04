"""Data models for the Workflow Automation pipeline view."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WorkflowStage(str, Enum):
    """Ordered, but not every company passes through every value in order
    -- a company can sit at a BLOCKED_* stage indefinitely until the phase
    it's waiting on ships. `derive.py` is the only place that decides which
    value applies.
    """

    IMPORTED = "IMPORTED"  # synced from a scrape (Company exists), nothing else yet
    ENRICHING = "ENRICHING"  # an enrichment run is the next automatable action
    ENRICHED = "ENRICHED"  # enriched, and a research run is the next automatable action
    RESEARCHED = "RESEARCHED"  # Phase 5 research pass done -- pain points/angles available
    PENDING_ICP_SCORE = "PENDING_ICP_SCORE"  # researched, ICP Scoring is the next automatable action
    PENDING_OUTREACH_DRAFT = "PENDING_OUTREACH_DRAFT"  # ICP-scored, drafting outreach is the next automatable action
    OUTREACH_DRAFTED = "OUTREACH_DRAFTED"  # Phase 6 drafts exist (see outbound/); sending requires a human -- see
    # OutboundSettings.auto_send_email and outbound/send/linkedin_adapter.py's docstring for exactly why sending
    # itself isn't autonomous.
    AWAITING_REPLY = "AWAITING_REPLY"  # outreach has been sent (manually, or via the email adapter); no reply yet
    REPLY_RECEIVED = "REPLY_RECEIVED"  # at least one ConversationSignal exists for a Person at this company
    RECOMMENDATIONS_ACTIVE = "RECOMMENDATIONS_ACTIVE"  # eligible for the daily Recommendation Engine digest
    FAILED = "FAILED"  # most recent enrichment failed
    RESEARCH_FAILED = "RESEARCH_FAILED"  # enriched, but the most recent research run failed
    ICP_SCORING_FAILED = "ICP_SCORING_FAILED"  # researched, but the most recent ICP scoring run failed
    OUTREACH_DRAFT_FAILED = "OUTREACH_DRAFT_FAILED"  # ICP-scored, but the most recent outreach drafting run failed


# Stages with a real, callable next action. Every other stage is either a
# terminal/waiting state, or a state where the only next step requires a
# human decision (OUTREACH_DRAFTED: review and send) -- `engine.advance()`
# only ever acts on stages in this set.
ACTIONABLE_STAGES = {
    WorkflowStage.IMPORTED,
    WorkflowStage.ENRICHED,
    WorkflowStage.FAILED,
    WorkflowStage.RESEARCH_FAILED,
    WorkflowStage.PENDING_ICP_SCORE,
    WorkflowStage.ICP_SCORING_FAILED,
    WorkflowStage.PENDING_OUTREACH_DRAFT,
    WorkflowStage.OUTREACH_DRAFT_FAILED,
}


class WorkflowState(BaseModel):
    """What `derive_workflow_state` computes for one company -- an honest
    snapshot built from existing audit records, not a stored/mutable value.
    """

    company_id: str
    stage: WorkflowStage
    blocked: bool = False
    blocked_reason: Optional[str] = None

    has_enrichment: bool = False
    last_enrichment_status: Optional[str] = None
    last_enrichment_at: Optional[str] = None

    has_research: bool = False
    last_research_status: Optional[str] = None
    last_research_at: Optional[str] = None

    has_icp_score: bool = False
    last_icp_score: Optional[float] = None
    last_icp_priority: Optional[str] = None

    has_outreach_draft: bool = False
    last_outreach_status: Optional[str] = None

    person_count: int = 0
    people_with_reply: int = 0
    latest_signal_at: Optional[str] = None

    next_action: Optional[str] = None  # human-readable description of what `advance()` would do next


class WorkflowStepResult(BaseModel):
    """What one call to `engine.advance()` did."""

    company_id: str
    stage_before: WorkflowStage
    stage_after: WorkflowStage
    action_taken: str  # e.g. "ran_enrichment", "no_op_already_enriched", "blocked"
    detail: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
