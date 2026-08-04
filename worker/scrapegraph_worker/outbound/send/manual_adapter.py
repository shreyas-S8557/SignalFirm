"""For channels that were never going to be sendable by code at all --
right now just CALL. A phone call has no "send" step; this exists purely
so `router.py` has a uniform adapter for every `MessageChannel` value
rather than a special case.
"""

from __future__ import annotations

from .base import SendAdapter, SendOutcome, SendResult


class ManualOnlyAdapter(SendAdapter):
    channel = "MANUAL"

    def send(self, *, recipient: str, subject: str | None, body: str) -> SendResult:
        return SendResult(
            outcome=SendOutcome.QUEUED_FOR_MANUAL_SEND,
            detail="This channel has no send step to automate -- the script is ready for a human to use.",
        )
