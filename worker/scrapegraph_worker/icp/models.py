"""Data models for ICP Scoring."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ICPPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ICPCriterionResult(BaseModel):
    """One rubric line item's contribution -- surfaced in `reasoning` so a
    score of, say, 42 is never a black box.
    """

    name: str
    weight: float
    raw_fraction: float  # 0-1, how much of this criterion's weight was earned
    points: float  # weight * raw_fraction
    detail: str


class ICPScoreResult(BaseModel):
    company_id: str
    score: float = 0.0  # 0-100
    priority: ICPPriority = ICPPriority.LOW
    confidence: float = 0.0  # 0-1, how much grounding data was available to score against
    rubric_version: str = "unscored"
    reasoning: str = ""
    criteria: list[ICPCriterionResult] = Field(default_factory=list)
    error_message: Optional[str] = None

    def clamp(self) -> "ICPScoreResult":
        self.score = round(max(0.0, min(100.0, self.score)), 1)
        self.confidence = round(max(0.0, min(1.0, self.confidence)), 3)
        return self
