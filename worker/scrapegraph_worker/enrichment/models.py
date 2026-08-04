"""Data models for the Company Enrichment pipeline.

Kept separate from `scrapegraph_worker.models` (scrape/sync domain) for the
same reason `conversation/models.py` is separate: this is its own
input-in/structured-output-out pipeline, not an extension of the CSV-row
sync flow.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EnrichmentStatus(str, Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class AIMaturityLevel(str, Enum):
    UNKNOWN = "UNKNOWN"
    NONE_OBSERVED = "NONE_OBSERVED"
    EXPLORING = "EXPLORING"
    ADOPTING = "ADOPTING"
    ADVANCED = "ADVANCED"


class CrawledPage(BaseModel):
    """One fetched page. `text` is visible-text-only (scripts/styles
    stripped), used for keyword scanning and LLM synthesis; `html` is kept
    for tech-stack signature matching, which needs script src attributes
    and meta tags that plain text extraction throws away.
    """

    url: str
    status_code: Optional[int] = None
    html: str = ""
    text: str = ""
    fetch_error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.fetch_error is None and self.status_code is not None and self.status_code < 400


class BuyingSignalHit(BaseModel):
    """One keyword match, always tied to the exact excerpt and page it came
    from -- never a synthesized claim. `sync.py`'s "never fabricate" norm
    applies here too: a buying signal is a quote, not an inference.
    """

    keyword: str
    excerpt: str
    source_url: str


class HiringSignal(BaseModel):
    department: str
    mention_count: int
    source_url: str


class GrowthIndicators(BaseModel):
    """Headcount proxy is deliberately NOT a claim about the company's real
    headcount -- it's the count of People records this workspace has
    already synced (via the scrape pipeline) whose Company matches this
    one. Useful as a relative signal across companies in this workspace,
    not as an absolute fact to state to a prospect.
    """

    synced_people_count: int = 0
    open_role_mentions: int = 0
    notes: list[str] = Field(default_factory=list)


class LinkedInDerivedSignals(BaseModel):
    """Derived entirely from People records already synced into this
    workspace (each of which came from a public search result the scrape
    pipeline collected, per its own ToS-compliant collection method) --
    never from directly fetching linkedin.com. See signals.py for the full
    reasoning.
    """

    people_with_linkedin_url: int = 0
    seniority_mix: dict[str, int] = Field(default_factory=dict)  # e.g. {"C-Level": 2, "Manager": 5}
    top_job_titles: list[str] = Field(default_factory=list)


class TechStackHit(BaseModel):
    name: str
    category: str
    matched_on: str  # what signature matched, e.g. "script src contains 'js.hs-scripts.com'"


class EnrichmentResult(BaseModel):
    """Everything one enrichment run produced, before it's turned into an
    EnrichmentJob record. `engine.py` computes `status` and `confidence`
    from how much of this actually got filled in -- neither is ever set by
    a sub-module directly, so the aggregation logic lives in exactly one
    place.
    """

    company_id: str
    status: EnrichmentStatus = EnrichmentStatus.PENDING
    provider: str = "site-crawl"
    confidence: float = 0.0
    error_message: Optional[str] = None

    summary: Optional[str] = None
    tech_stack: list[TechStackHit] = Field(default_factory=list)
    hiring_signals: list[HiringSignal] = Field(default_factory=list)
    buying_signals: list[BuyingSignalHit] = Field(default_factory=list)
    growth_indicators: Optional[GrowthIndicators] = None
    linkedin_signals: Optional[LinkedInDerivedSignals] = None
    ai_maturity: AIMaturityLevel = AIMaturityLevel.UNKNOWN
    ai_maturity_reasoning: Optional[str] = None

    sources_checked: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)

    def clamp_confidence(self) -> "EnrichmentResult":
        self.confidence = min(1.0, max(0.0, self.confidence))
        return self
