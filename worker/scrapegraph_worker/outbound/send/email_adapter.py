"""The one channel this package can genuinely send on its own.

Sending an email your own business's SMTP account sends, to a prospect
whose address a human-reviewed sales pipeline already has, is a normal
thing for a sales tool to automate -- unlike LinkedIn (see
`linkedin_adapter.py`), there's no third-party ToS being circumvented
here. Still opt-in (`OutboundSettings.auto_send_email`, off by default)
and still dry-run-aware, same "safe by default" posture as the rest of
this service's automatic-execution flags (ENRICHMENT_SCHEDULE_ENABLED,
AUTO_ENRICH_ON_IMPORT, etc).
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from ...config import OutboundSettings
from .base import SendAdapter, SendOutcome, SendResult

logger = logging.getLogger(__name__)


class EmailSendAdapter(SendAdapter):
    channel = "EMAIL"

    def __init__(self, settings: OutboundSettings):
        self._settings = settings

    def send(self, *, recipient: str, subject: str | None, body: str) -> SendResult:
        if not recipient:
            return SendResult(outcome=SendOutcome.FAILED, error_message="No recipient email address on file.")

        if not self._settings.auto_send_email:
            return SendResult(
                outcome=SendOutcome.QUEUED_FOR_MANUAL_SEND,
                detail="OUTBOUND_AUTO_SEND_EMAIL is false -- draft is ready, send it yourself.",
            )

        if not self._settings.smtp_host:
            return SendResult(
                outcome=SendOutcome.QUEUED_FOR_MANUAL_SEND,
                detail="OUTBOUND_SMTP_HOST is not configured -- draft is ready, send it yourself.",
            )

        if self._settings.dry_run:
            logger.info("[outbound dry-run] would email %s: subject=%r", recipient, subject)
            return SendResult(outcome=SendOutcome.SKIPPED_DRY_RUN, detail=f"Dry run -- would have emailed {recipient}.")

        try:
            message = MIMEText(body, "plain", "utf-8")
            message["Subject"] = subject or "(no subject)"
            message["From"] = self._settings.smtp_from or self._settings.smtp_user
            message["To"] = recipient

            with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=15) as server:
                if self._settings.smtp_use_tls:
                    server.starttls()
                if self._settings.smtp_user and self._settings.smtp_password:
                    server.login(self._settings.smtp_user, self._settings.smtp_password)
                server.send_message(message)
            return SendResult(outcome=SendOutcome.SENT, detail=f"Emailed {recipient}.")
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("Failed to send outbound email to %s", recipient, exc_info=True)
            return SendResult(outcome=SendOutcome.FAILED, error_message=str(exc))
