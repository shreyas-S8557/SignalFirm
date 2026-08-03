"""Data models for the Conversation Intelligence module.

Kept separate from `scrapegraph_worker.models` (scrape/sync domain) since
this is a distinct pipeline: reply text in, structured signal + recommendation
out. `ReplyAnalysisResult`'s enum fields are always produced by
`analyzer.normalize_result` -- never trusted verbatim from the LLM's JSON --
so anything downstream (including the Twenty push) can rely on them being one
of the declared values.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InterestLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class Urgency(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Sentiment(str, Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"


class NextAction(str, Enum):
    SEND_REPLY = "SEND_REPLY"
    SCHEDULE_FOLLOW_UP = "SCHEDULE_FOLLOW_UP"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
    MARK_WON = "MARK_WON"
    MARK_LOST = "MARK_LOST"
    NO_ACTION = "NO_ACTION"


class ReplyAnalysisRequest(BaseModel):
    """What reply-intelligence-trigger.ts POSTs to /conversation/analyze."""

    message_id: str = Field(alias="messageId")
    thread_id: Optional[str] = Field(default=None, alias="threadId")
    person_id: str = Field(alias="personId")
    subject: Optional[str] = None
    text: str
    received_at: Optional[str] = Field(default=None, alias="receivedAt")

    model_config = {"populate_by_name": True}


class ReplyAnalysisResult(BaseModel):
    """The normalized, enum-constrained output of one analysis run."""

    status: str = "COMPLETED"  # COMPLETED | FAILED -- mirrors ConversationSignalStatus
    interest_level: InterestLevel = InterestLevel.NONE
    urgency: Urgency = Urgency.LOW
    sentiment: Sentiment = Sentiment.NEUTRAL
    objections: list[str] = Field(default_factory=list)
    recommended_next_action: NextAction = NextAction.NO_ACTION
    recommended_reply_draft: Optional[str] = None
    recommended_follow_up_at: Optional[str] = None  # ISO-8601, computed deterministically
    confidence: float = 0.0
    model_used: Optional[str] = None
    error_message: Optional[str] = None

    def clamp_confidence(self) -> "ReplyAnalysisResult":
        self.confidence = min(1.0, max(0.0, self.confidence))
        return self
