from __future__ import annotations

import abc
from enum import Enum

from pydantic import BaseModel


class SendOutcome(str, Enum):
    SENT = "SENT"  # actually delivered by this adapter
    QUEUED_FOR_MANUAL_SEND = "QUEUED_FOR_MANUAL_SEND"  # adapter cannot send itself; a human must act
    FAILED = "FAILED"
    SKIPPED_DRY_RUN = "SKIPPED_DRY_RUN"


class SendResult(BaseModel):
    outcome: SendOutcome
    detail: str = ""
    error_message: str | None = None


class SendAdapter(abc.ABC):
    """One implementation per channel. `send()` must never raise -- like
    every other engine in this codebase, a delivery failure becomes a
    FAILED SendResult, not an exception that could take down a batch
    sweep (see outbound_scheduler_main.py, which calls this across many
    people in one run).
    """

    channel: str

    @abc.abstractmethod
    def send(self, *, recipient: str, subject: str | None, body: str) -> SendResult:
        raise NotImplementedError
