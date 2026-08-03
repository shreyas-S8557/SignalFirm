"""Pushes a completed (or failed) ReplyAnalysisResult back into Twenty.

Mirrors `progress.py::push_progress_to_twenty` deliberately: same
best-effort-POST-with-shared-secret shape, just pointed at
conversation-signal-webhook.ts instead of job-progress-webhook.ts. Kept as
its own function (not folded into progress.py) because it's a different
domain object with a different payload shape, not because the mechanics
differ.
"""

from __future__ import annotations

import json
import logging

import httpx

from ..config import TwentySettings
from .models import ReplyAnalysisRequest, ReplyAnalysisResult

logger = logging.getLogger(__name__)


def push_conversation_signal_to_twenty(
    settings: TwentySettings,
    request: ReplyAnalysisRequest,
    result: ReplyAnalysisResult,
) -> bool:
    """Best-effort POST of the analysis result to Twenty's
    conversation-signal-webhook.ts route. Returns True on a 2xx response,
    False otherwise (including when the URL isn't configured) -- callers
    decide how to surface that in the API response, this function never
    raises for a downstream failure.
    """
    if not settings.conversation_signal_webhook_url:
        return False

    excerpt = request.text.strip()[:280]

    try:
        response = httpx.post(
            settings.conversation_signal_webhook_url,
            timeout=10,
            headers={
                "Authorization": f"Bearer {settings.webhook_shared_secret}",
                "Content-Type": "application/json",
            },
            content=json.dumps(
                {
                    "personId": request.person_id,
                    "messageId": request.message_id,
                    "status": result.status,
                    "interestLevel": result.interest_level.value,
                    "urgency": result.urgency.value,
                    "sentiment": result.sentiment.value,
                    "objections": _objections_to_text(result.objections),
                    "recommendedNextAction": result.recommended_next_action.value,
                    "recommendedReplyDraft": result.recommended_reply_draft,
                    "recommendedFollowUpAt": result.recommended_follow_up_at,
                    "confidence": result.confidence,
                    "rawExcerpt": excerpt,
                    "modelUsed": result.model_used,
                    "errorMessage": result.error_message,
                }
            ),
        )
    except httpx.HTTPError:
        logger.warning(
            "Failed to push conversation signal for message %s to Twenty webhook",
            request.message_id,
            exc_info=True,
        )
        return False

    if response.status_code >= 400:
        logger.warning(
            "Twenty rejected conversation signal for message %s: %s %s",
            request.message_id,
            response.status_code,
            response.text[:300],
        )
        return False
    return True


def _objections_to_text(objections: list[str]) -> str:
    """ConversationSignal.objections is a RICH_TEXT field -- render as a
    simple markdown bullet list rather than a raw JSON array.
    """
    if not objections:
        return ""
    return "\n".join(f"- {item}" for item in objections)
