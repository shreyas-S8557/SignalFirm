"""Deliberately does NOT send LinkedIn connection requests or messages.

This is not an unfinished stub -- it's the correct behavior. Automating
LinkedIn connection requests / DMs through browser automation or an
unofficial API:

1. Violates LinkedIn's Terms of Service (automated/scripted activity on
   the platform is explicitly prohibited), and real accounts get
   restricted or permanently banned for it, including accounts that
   otherwise look like normal sales activity.
2. LinkedIn's official Messaging/Marketing APIs are partner-gated (Talent
   Solutions, Marketing Developer Platform, etc.) and are not something a
   self-hosted worker like this one can obtain general access to; there is
   no compliant "just call an API" path here the way there is for SMTP
   email.

So this adapter's `send()` always reports `QUEUED_FOR_MANUAL_SEND`: the
message was already drafted (see engine.py) and is sitting on the
Company/Person's Notes, ready for a human to paste into LinkedIn
themselves. If your organization has a compliant LinkedIn automation tool
(e.g. an official partner integration) you're licensed to use, swap this
adapter out for one that calls it -- this module intentionally does not
attempt that.
"""

from __future__ import annotations

from .base import SendAdapter, SendOutcome, SendResult


class LinkedInSendAdapter(SendAdapter):
    channel = "LINKEDIN"

    def send(self, *, recipient: str, subject: str | None, body: str) -> SendResult:
        return SendResult(
            outcome=SendOutcome.QUEUED_FOR_MANUAL_SEND,
            detail=(
                "LinkedIn sending is never automated by this service (ToS + no compliant API path -- "
                "see this module's docstring). The draft is ready on the contact's Notes for you to send "
                "manually."
            ),
        )
