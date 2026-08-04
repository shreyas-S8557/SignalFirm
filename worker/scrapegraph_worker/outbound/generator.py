"""Orchestrates one outreach-drafting run: prompt -> LLM -> validated
OutboundMessageSet. Same "nothing the LLM emits reaches a caller without
being coerced into a known-safe shape first" rule as
conversation/analyzer.py -- a missing key, a channel enum the model
invented, a 900-character "connection note," or a truncated/malformed JSON
completion are all expected inputs to `normalize_result`, not exceptional
ones.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from ..conversation.llm_client import LLMClient, LLMError
from .models import CallScript, MessageChannel, MessageVariant, OutboundMessageSet, OutboundStatus, SequenceStep
from .prompts import SYSTEM_PROMPT, OutboundContext, build_user_prompt

logger = logging.getLogger(__name__)

_LINKEDIN_CONNECTION_NOTE_MAX = 300
_MAX_SEQUENCE_STEPS = 8
_MAX_QUESTIONS = 8
_MAX_OBJECTIONS = 8
_MAX_FIELD_LEN = 4000  # generous ceiling against a runaway completion, not a normal-case limit

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def generate_messages(
    ctx: OutboundContext,
    *,
    company_id: str,
    person_id: Optional[str],
    llm: LLMClient,
    model_name: str,
) -> OutboundMessageSet:
    try:
        raw_content = llm.complete_json(system_prompt=SYSTEM_PROMPT, user_prompt=build_user_prompt(ctx))
    except LLMError as exc:
        logger.warning("LLM call failed drafting outreach for company %s: %s", company_id, exc)
        return OutboundMessageSet(
            company_id=company_id,
            person_id=person_id,
            person_name=ctx.person_name or None,
            person_title=ctx.person_title or None,
            status=OutboundStatus.FAILED,
            model_used=model_name,
            error_message=str(exc),
        )

    parsed = _parse_json_object(raw_content)
    if parsed is None:
        logger.warning("Could not parse JSON from LLM output drafting outreach for company %s", company_id)
        return OutboundMessageSet(
            company_id=company_id,
            person_id=person_id,
            person_name=ctx.person_name or None,
            person_title=ctx.person_title or None,
            status=OutboundStatus.FAILED,
            model_used=model_name,
            error_message="LLM output was not valid JSON",
        )

    return normalize_result(parsed, company_id=company_id, person_id=person_id, ctx=ctx, model_name=model_name)


def normalize_result(
    data: dict[str, Any], *, company_id: str, person_id: Optional[str], ctx: OutboundContext, model_name: str
) -> OutboundMessageSet:
    result = OutboundMessageSet(
        company_id=company_id,
        person_id=person_id,
        person_name=ctx.person_name or None,
        person_title=ctx.person_title or None,
        status=OutboundStatus.DRAFTED,
        model_used=model_name,
    )

    result.linkedin_connection_note = _clip(_str(data.get("linkedin_connection_note")), _LINKEDIN_CONNECTION_NOTE_MAX)
    result.linkedin_message = _clip(_str(data.get("linkedin_message")), _MAX_FIELD_LEN)

    variant_a = _parse_variant(data.get("email_variant_a"), label="A")
    variant_b = _parse_variant(data.get("email_variant_b"), label="B")
    result.email_variants = [v for v in (variant_a, variant_b) if v is not None]

    result.meeting_request = _parse_variant(data.get("meeting_request"), label="meeting_request")
    result.call_script = _parse_call_script(data.get("call_script"))
    result.follow_up_sequence = _parse_sequence(data.get("follow_up_sequence"))

    confidence = data.get("confidence")
    result.confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.5
    result.clamp_confidence()

    # A drafting run that produced literally nothing usable is a failure,
    # not a "successful" empty draft -- same principle as
    # conversation/analyzer.py never trusting a technically-valid-but-empty
    # completion.
    if not any(
        [
            result.linkedin_connection_note,
            result.linkedin_message,
            result.email_variants,
            result.meeting_request,
            result.call_script and result.call_script.pitch,
            result.follow_up_sequence,
        ]
    ):
        result.status = OutboundStatus.FAILED
        result.error_message = "LLM completion parsed as JSON but contained no usable message content."

    return result


def _parse_variant(raw: Any, *, label: str) -> Optional[MessageVariant]:
    if not isinstance(raw, dict):
        return None
    body = _str(raw.get("body"))
    if not body:
        return None
    return MessageVariant(label=label, subject=_clip(_str(raw.get("subject")), 200), body=_clip(body, _MAX_FIELD_LEN))


def _parse_call_script(raw: Any) -> Optional[CallScript]:
    if not isinstance(raw, dict):
        return None
    return CallScript(
        opening=_clip(_str(raw.get("opening")), _MAX_FIELD_LEN),
        discovery_questions=_str_list(raw.get("discovery_questions"), _MAX_QUESTIONS),
        pitch=_clip(_str(raw.get("pitch")), _MAX_FIELD_LEN),
        objection_handling=_str_list(raw.get("objection_handling"), _MAX_OBJECTIONS),
        closing=_clip(_str(raw.get("closing")), _MAX_FIELD_LEN),
    )


def _parse_sequence(raw: Any) -> list[SequenceStep]:
    if not isinstance(raw, list):
        return []
    steps: list[SequenceStep] = []
    for i, item in enumerate(raw[:_MAX_SEQUENCE_STEPS]):
        if not isinstance(item, dict):
            continue
        try:
            channel = MessageChannel(str(item.get("channel", "")).upper())
        except ValueError:
            continue
        day_offset = item.get("day_offset")
        if not isinstance(day_offset, (int, float)):
            continue
        steps.append(
            SequenceStep(
                step_number=i + 1,
                day_offset=max(0, int(day_offset)),
                channel=channel,
                purpose=_clip(_str(item.get("purpose")), 200),
                body=_clip(_str(item.get("body")), _MAX_FIELD_LEN),
            )
        )
    return sorted(steps, key=lambda s: s.day_offset)


def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clip(value: str, max_len: int) -> Optional[str]:
    if not value:
        return None
    return value if len(value) <= max_len else value[: max_len - 1].rstrip() + "\u2026"


def _str_list(value: Any, max_items: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_str(v) for v in value[:max_items] if _str(v)]


def _parse_json_object(raw: str) -> Optional[dict[str, Any]]:
    """Best-effort JSON extraction -- same approach as
    conversation/analyzer.py::_parse_json_object.
    """
    candidate = _FENCE_RE.sub("", raw.strip())
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None
