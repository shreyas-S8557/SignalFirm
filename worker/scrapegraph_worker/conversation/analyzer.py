"""Orchestrates one reply analysis: prompt -> LLM -> validated result.

The one rule this module enforces throughout: nothing the LLM emits reaches
a caller (and eventually a ConversationSignal record in Twenty) without
being coerced into a known-safe shape first. Free-text drift in an enum
field, a missing key, a confidence value of 1.7, an unterminated JSON
object from a truncated completion -- all of these are expected inputs to
`normalize_result`, not exceptional ones.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .llm_client import LLMClient, LLMError
from .models import (
    InterestLevel,
    NextAction,
    ReplyAnalysisRequest,
    ReplyAnalysisResult,
    Sentiment,
    Urgency,
)
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

_MAX_OBJECTIONS = 8
_MAX_OBJECTION_LEN = 200
_MAX_DRAFT_LEN = 2000

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def analyze_reply(request: ReplyAnalysisRequest, client: LLMClient, *, model_name: str) -> ReplyAnalysisResult:
    """Runs the full pipeline for one reply. Never raises for LLM/parse
    failures -- those become a `status="FAILED"` result with `error_message`
    set, so the API layer can still push *something* back to Twenty (a
    ConversationSignal with status FAILED) rather than losing the event
    silently.
    """
    try:
        raw_content = client.complete_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(request),
        )
    except LLMError as exc:
        logger.warning("LLM call failed for message %s: %s", request.message_id, exc)
        return ReplyAnalysisResult(status="FAILED", model_used=model_name, error_message=str(exc))

    parsed = _parse_json_object(raw_content)
    if parsed is None:
        logger.warning("Could not parse JSON from LLM output for message %s", request.message_id)
        return ReplyAnalysisResult(
            status="FAILED",
            model_used=model_name,
            error_message="LLM output was not valid JSON",
        )

    return normalize_result(parsed, model_name=model_name)


def _parse_json_object(raw: str) -> Optional[dict[str, Any]]:
    """Best-effort JSON extraction. Handles the two most common ways a small
    local/free-tier model fails to follow "JSON only" instructions:
    markdown code fences, and leading/trailing chatter around the object.
    """
    candidate = _FENCE_RE.sub("", raw.strip())

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Fall back to the first {...} span, in case the model added a preamble
    # or trailing remark despite instructions not to.
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None


def normalize_result(parsed: dict[str, Any], *, model_name: str) -> ReplyAnalysisResult:
    interest_level = _coerce_enum(parsed.get("interest_level"), InterestLevel, InterestLevel.NONE)
    urgency = _coerce_enum(parsed.get("urgency"), Urgency, Urgency.LOW)
    sentiment = _coerce_enum(parsed.get("sentiment"), Sentiment, Sentiment.NEUTRAL)
    next_action = _coerce_enum(parsed.get("recommended_next_action"), NextAction, NextAction.NO_ACTION)

    objections = _coerce_objections(parsed.get("objections"))

    draft = parsed.get("recommended_reply_draft")
    draft = draft.strip()[:_MAX_DRAFT_LEN] if isinstance(draft, str) and draft.strip() else None
    if next_action in (NextAction.MARK_WON, NextAction.MARK_LOST, NextAction.NO_ACTION):
        # A draft reply makes no sense for these actions regardless of what
        # the model produced -- deterministic override, not a model choice.
        draft = None

    follow_up_at = None
    if next_action is NextAction.SCHEDULE_FOLLOW_UP:
        follow_up_at = _compute_follow_up_at(parsed.get("follow_up_in_days"))

    confidence = _coerce_confidence(parsed.get("confidence"))

    return ReplyAnalysisResult(
        status="COMPLETED",
        interest_level=interest_level,
        urgency=urgency,
        sentiment=sentiment,
        objections=objections,
        recommended_next_action=next_action,
        recommended_reply_draft=draft,
        recommended_follow_up_at=follow_up_at,
        confidence=confidence,
        model_used=model_name,
    )


def _coerce_enum(value: Any, enum_cls: type, default: Any) -> Any:
    if isinstance(value, str):
        normalized = value.strip().upper().replace(" ", "_").replace("-", "_")
        try:
            return enum_cls(normalized)
        except ValueError:
            pass
    return default


def _coerce_objections(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text:
            cleaned.append(text[:_MAX_OBJECTION_LEN])
        if len(cleaned) >= _MAX_OBJECTIONS:
            break
    return cleaned


def _coerce_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN check without importing math for one use
        return 0.0
    return min(1.0, max(0.0, number))


def _compute_follow_up_at(days_value: Any, *, now: Optional[datetime] = None) -> Optional[str]:
    """Turns the model's `follow_up_in_days` into an absolute ISO-8601
    timestamp computed by us, not the model -- an LLM has no reliable notion
    of "now", so it never gets to emit a timestamp directly.
    """
    try:
        days = int(days_value)
    except (TypeError, ValueError):
        days = 2  # conservative default when the model omits/garbles this
    days = min(max(days, 0), 30)  # clamp to a sane sales-follow-up window
    base = now or datetime.now(timezone.utc)
    return (base + timedelta(days=days)).isoformat()
