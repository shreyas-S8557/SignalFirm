"""Data models for the Research Automation pipeline.

Note the naming throughout: `PainPointHypothesis` and `SalesAngleHypothesis`
are named for what they are rather than the shorter `PainPoint` /
`SalesAngle`, so the inferential status is visible at every call site and
can't quietly get lost between here and the CRM record.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ResearchStatus(str, Enum):
    RESEARCHED = "RESEARCHED"
    RESEARCH_FAILED = "RESEARCH_FAILED"


class PainPointHypothesis(BaseModel):
    """An INFERRED problem the company may have. Not an observation.

    `derived_from` is mandatory (not Optional) on purpose: an uncited
    hypothesis is indistinguishable from a fabrication, so
    `agent.normalize_result` drops any item the model returned without
    one rather than storing it.
    """

    hypothesis: str
    derived_from: str  # what in the enrichment data suggested this


class SalesAngleHypothesis(BaseModel):
    """An INFERRED conversation opener, tied to a pain-point hypothesis."""

    angle: str
    addresses_pain_point: str
    derived_from: str


class InterpretedBuyingSignal(BaseModel):
    """The LLM's reading of a buying signal Phase 4 already found by
    keyword match. `excerpt` is carried through verbatim from the
    enrichment data -- the LLM interprets it, it does not get to restate
    or embellish the underlying quote.
    """

    excerpt: str
    source_url: str
    interpretation: str


class ResearchGrounding(BaseModel):
    """What this run was actually based on -- written to the ResearchJob
    record so any claim can be traced back to its input.
    """

    enrichment_job_id: Optional[str] = None
    enrichment_status: Optional[str] = None
    source_urls: list[str] = Field(default_factory=list)
    had_summary: bool = False
    had_tech_stack: bool = False
    had_hiring_signals: bool = False
    had_buying_signals: bool = False

    @property
    def material_count(self) -> int:
        """How many distinct kinds of grounding material this run had.
        Drives `confidence` in engine.py -- more independent material,
        more trustworthy the synthesis.
        """
        return sum([self.had_summary, self.had_tech_stack, self.had_hiring_signals, self.had_buying_signals])


class ResearchResult(BaseModel):
    company_id: str
    status: ResearchStatus = ResearchStatus.RESEARCH_FAILED
    summary: Optional[str] = None
    pain_point_hypotheses: list[PainPointHypothesis] = Field(default_factory=list)
    sales_angle_hypotheses: list[SalesAngleHypothesis] = Field(default_factory=list)
    interpreted_buying_signals: list[InterpretedBuyingSignal] = Field(default_factory=list)
    grounding: ResearchGrounding = Field(default_factory=ResearchGrounding)
    confidence: float = 0.0
    model_used: Optional[str] = None
    error_message: Optional[str] = None

    def clamp_confidence(self) -> "ResearchResult":
        self.confidence = min(1.0, max(0.0, self.confidence))
        return self
