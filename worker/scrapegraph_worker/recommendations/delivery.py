"""Delivers a rendered digest somewhere a human will actually see it every
morning.

Same philosophy as `conversation/twenty_push.py`: every transport is
independently optional, and missing config means "don't send this way," not
"crash." No transport is required for the engine itself to work -- the
digest is always computable and always available via the API
(`GET /recommendations/daily-digest`) regardless of what's configured here.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

import httpx

from ..config import DigestSettings

logger = logging.getLogger(__name__)


def deliver_digest(settings: DigestSettings, *, markdown: str) -> dict[str, bool]:
    """Attempts every configured transport and reports which succeeded.
    Falls back to writing a local file only if *neither* email nor Slack is
    configured, so a fresh deploy with no DIGEST_* env vars set still
    produces a visible artifact instead of a silent no-op.
    """
    results = {"email": False, "slack": False, "file": False}

    if settings.smtp_host and settings.email_to:
        results["email"] = _send_email(settings, markdown)

    if settings.slack_webhook_url:
        results["slack"] = _send_slack(settings, markdown)

    if not results["email"] and not results["slack"]:
        results["file"] = _write_file(settings, markdown)

    return results


def _send_email(settings: DigestSettings, markdown: str) -> bool:
    try:
        message = MIMEText(markdown, "plain", "utf-8")
        message["Subject"] = "Morning Recommendations"
        message["From"] = settings.smtp_from or settings.email_to
        message["To"] = settings.email_to

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
        return True
    except (smtplib.SMTPException, OSError):
        logger.warning("Failed to email the daily digest", exc_info=True)
        return False


def _send_slack(settings: DigestSettings, markdown: str) -> bool:
    try:
        response = httpx.post(settings.slack_webhook_url, json={"text": markdown}, timeout=10)
    except httpx.HTTPError:
        logger.warning("Failed to post the daily digest to Slack", exc_info=True)
        return False
    return response.status_code < 300


def _write_file(settings: DigestSettings, markdown: str) -> bool:
    try:
        Path(settings.fallback_file_path).write_text(markdown, encoding="utf-8")
        return True
    except OSError:
        logger.warning("Failed to write the fallback digest file", exc_info=True)
        return False
