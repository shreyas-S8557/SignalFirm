"""Data models for the Recommendation Engine.

Kept separate from `conversation/models.py` for the same reason that module
is separate from `scrapegraph_worker.models`: distinct pipeline, distinct
contract. `PersonRecommendation` is always produced by `scorer.py` /
`engine.py` -- never partially hand-built -- so every field here can be
trusted to already be within its documented range (e.g.
`buying_intent_score` is always 0-100) by the time it reaches `render.py`
or an API response.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Bucket(str, Enum):
    """An action recommendation -- distinct from `Temperature` (intent
    strength). A resolved deal is IGNORE no matter how hot its last signal
    was; see `scorer.classify_bucket` for the full decision.
    """

    CONTACT_TODAY = "CONTACT_TODAY"
    MONITOR = "MONITOR"
    IGNORE = "IGNORE"


class Temperature(str, Enum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


class PersonRecommendation(BaseModel):
    """One person's row in the daily digest."""

    person_id: str
    name: str
    email: Optional[str] = None
    company_name: Optional[str] = None

    # Carried straight from Person.latestInterestLevel / .latestUrgency
    # (denormalized by conversation-signal-webhook.ts) and from that
    # person's most recent ConversationSignal record.
    interest_level: str  # HIGH | MEDIUM | LOW | NONE
    urgency: str  # HIGH | MEDIUM | LOW
    sentiment: Optional[str] = None
    latest_next_action: Optional[str] = None
    latest_objections: Optional[str] = None
    latest_confidence: Optional[float] = None

    last_signal_at: Optional[datetime] = None
    days_since_signal: Optional[float] = None

    # Optional bonus input -- null until a later milestone starts writing
    # Company.latestIcpScore/latestIcpPriority (see package docstring).
    icp_score: Optional[float] = None
    icp_priority: Optional[str] = None

    buying_intent_score: float
    temperature: Temperature
    bucket: Bucket
    reason: str
    best_message: str


class DailyDigest(BaseModel):
    """The full morning digest. `ranked_by_buying_intent` is every
    considered person sorted highest-score-first; the other lists are
    filtered views of the same data for the specific questions this engine
    answers (who to contact, who to ignore, hot, cold).
    """

    generated_at: datetime
    considered_count: int
    contact_today: list[PersonRecommendation] = Field(default_factory=list)
    ignore: list[PersonRecommendation] = Field(default_factory=list)
    hot: list[PersonRecommendation] = Field(default_factory=list)
    cold: list[PersonRecommendation] = Field(default_factory=list)
    ranked_by_buying_intent: list[PersonRecommendation] = Field(default_factory=list)
    top_pick: Optional[PersonRecommendation] = None
