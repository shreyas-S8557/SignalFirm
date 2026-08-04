"""Data models for AI Outbound Messaging (Phase 6)."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OutboundStatus(str, Enum):
    DRAFTED = "DRAFTED"
    FAILED = "FAILED"


class MessageChannel(str, Enum):
    LINKEDIN_CONNECTION = "LINKEDIN_CONNECTION"
    LINKEDIN_MESSAGE = "LINKEDIN_MESSAGE"
    EMAIL = "EMAIL"
    MEETING_REQUEST = "MEETING_REQUEST"
    CALL = "CALL"


class MessageVariant(BaseModel):
    """One A/B-testable message. `subject` is only meaningful for EMAIL /
    MEETING_REQUEST channels -- LinkedIn/call-script content leaves it None.
    """

    label: str = "A"
    subject: Optional[str] = None
    body: str = ""


class CallScript(BaseModel):
    opening: str = ""
    discovery_questions: list[str] = Field(default_factory=list)
    pitch: str = ""
    objection_handling: list[str] = Field(default_factory=list)
    closing: str = ""


class SequenceStep(BaseModel):
    """One step of the generated follow-up cadence. `day_offset` is
    relative to the sequence's start (day 0 = the first send), not to
    "today" -- `sequence.py` turns this into an absolute due date once a
    sequence is scheduled for a specific person.
    """

    step_number: int
    day_offset: int
    channel: MessageChannel
    purpose: str = ""
    body: str = ""


class OutboundMessageSet(BaseModel):
    """Everything one drafting run produced for one (company, person) pair.
    Never raises for LLM/parse failures -- see generator.py -- so callers
    always get a status to branch on, same convention as
    EnrichmentResult/ResearchResult.
    """

    company_id: str
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    person_title: Optional[str] = None
    person_email: Optional[str] = None

    status: OutboundStatus = OutboundStatus.FAILED
    model_used: Optional[str] = None
    confidence: float = 0.0
    error_message: Optional[str] = None

    linkedin_connection_note: Optional[str] = None  # <=300 chars, LinkedIn's own connection-note limit
    linkedin_message: Optional[str] = None
    email_variants: list[MessageVariant] = Field(default_factory=list)  # A/B cold-email drafts
    meeting_request: Optional[MessageVariant] = None
    call_script: Optional[CallScript] = None
    follow_up_sequence: list[SequenceStep] = Field(default_factory=list)

    note_id: Optional[str] = None  # the Note this draft was persisted as, once written

    def clamp_confidence(self) -> "OutboundMessageSet":
        self.confidence = min(1.0, max(0.0, self.confidence))
        return self
