"""Runs one research pass: enrichment data in, normalized ResearchResult
out. No Twenty I/O here -- `engine.py` handles reading the EnrichmentJob
and writing the ResearchJob, the same separation `conversation/analyzer.py`
keeps from `conversation/twenty_push.py`.

`normalize_result` is where the model's output stops being trusted. It:
  - drops any pain point / sales angle without a real `derived_from`
    (an uncited hypothesis is indistinguishable from a fabrication)
  - drops any interpreted buying signal whose `excerpt`/`source_url`
    doesn't match one actually present in the enrichment input, so the
    model can't quietly invent or reword a quote
  - caps list lengths regardless of what the prompt asked for
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional, Protocol

from ..enrichment.models import EnrichmentResult
from .models import (
    InterpretedBuyingSignal,
    PainPointHypothesis,
    ResearchResult,
    ResearchStatus,
    SalesAngleHypothesis,
)
from .prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

MAX_PAIN_POINTS = 5
MAX_SALES_ANGLES = 5
MAX_BUYING_SIGNALS = 10

# Below this, a `derived_from` is treated as absent -- catches models that
# satisfy the required key with "n/a", "-", "input", etc.
_MIN_DERIVED_FROM_CHARS = 8
_PLACEHOLDER_DERIVED_FROM = {"n/a", "na", "none", "unknown", "-", "input", "the input", "provided data"}


class SupportsCompleteJson(Protocol):
    """Structural type matching `conversation.llm_client.LLMClient` --
    declared so tests can pass a fake without importing httpx.
    """

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> str: ...


def run_research(
    enrichment: EnrichmentResult,
    client: SupportsCompleteJson,
    *,
    company_id: str,
    company_name: str,
    model_name: Optional[str] = None,
) -> ResearchResult:
    user_prompt = build_user_prompt(enrichment, company_name=company_name)

    try:
        raw = client.complete_json(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)
    except Exception as exc:  # noqa: BLE001 - "analysis unavailable", not a programming error
        logger.warning("Research LLM call failed for company %s: %s", company_id, exc)
        return ResearchResult(
            company_id=company_id,
            status=ResearchStatus.RESEARCH_FAILED,
            model_used=model_name,
            error_message=f"LLM call failed: {exc}",
        )

    try:
        payload = _parse_json_object(raw)
    except ValueError as exc:
        logger.warning("Research LLM returned unparseable JSON for company %s: %s", company_id, exc)
        return ResearchResult(
            company_id=company_id,
            status=ResearchStatus.RESEARCH_FAILED,
            model_used=model_name,
            error_message=f"Unparseable LLM response: {exc}",
        )

    return normalize_result(payload, enrichment, company_id=company_id, model_name=model_name)


def normalize_result(
    payload: dict[str, Any],
    enrichment: EnrichmentResult,
    *,
    company_id: str,
    model_name: Optional[str] = None,
) -> ResearchResult:
    summary = _clean_str(payload.get("summary"))

    pain_points: list[PainPointHypothesis] = []
    for item in _as_list(payload.get("pain_points"))[:MAX_PAIN_POINTS]:
        if not isinstance(item, dict):
            continue
        hypothesis = _clean_str(item.get("hypothesis"))
        derived_from = _clean_str(item.get("derived_from"))
        if not hypothesis or not _is_real_citation(derived_from):
            continue
        pain_points.append(PainPointHypothesis(hypothesis=hypothesis, derived_from=derived_from))

    sales_angles: list[SalesAngleHypothesis] = []
    for item in _as_list(payload.get("sales_angles"))[:MAX_SALES_ANGLES]:
        if not isinstance(item, dict):
            continue
        angle = _clean_str(item.get("angle"))
        derived_from = _clean_str(item.get("derived_from"))
        if not angle or not _is_real_citation(derived_from):
            continue
        sales_angles.append(
            SalesAngleHypothesis(
                angle=angle,
                addresses_pain_point=_clean_str(item.get("addresses_pain_point")) or "(unspecified)",
                derived_from=derived_from,
            )
        )

    # Buying signals are only kept when the excerpt genuinely came from the
    # enrichment input -- the model interprets quotes, it doesn't get to
    # supply them.
    known_excerpts = {(hit.excerpt.strip(), hit.source_url.strip()) for hit in enrichment.buying_signals}
    interpreted: list[InterpretedBuyingSignal] = []
    for item in _as_list(payload.get("buying_signals"))[:MAX_BUYING_SIGNALS]:
        if not isinstance(item, dict):
            continue
        excerpt = _clean_str(item.get("excerpt"))
        source_url = _clean_str(item.get("source_url"))
        interpretation = _clean_str(item.get("interpretation"))
        if not excerpt or not interpretation:
            continue
        if (excerpt, source_url) not in known_excerpts:
            logger.info("Dropping interpreted buying signal not present in enrichment input (company %s)", company_id)
            continue
        interpreted.append(
            InterpretedBuyingSignal(excerpt=excerpt, source_url=source_url, interpretation=interpretation)
        )

    return ResearchResult(
        company_id=company_id,
        status=ResearchStatus.RESEARCHED,
        summary=summary,
        pain_point_hypotheses=pain_points,
        sales_angle_hypotheses=sales_angles,
        interpreted_buying_signals=interpreted,
        model_used=model_name,
    )


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Strips markdown fences (some providers add them even in JSON mode --
    see llm_client.py's `supports_json_mode` note) and parses.
    """
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed).__name__}")
    return parsed


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_str(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _is_real_citation(derived_from: Optional[str]) -> bool:
    if not derived_from or len(derived_from) < _MIN_DERIVED_FROM_CHARS:
        return False
    return derived_from.strip().lower() not in _PLACEHOLDER_DERIVED_FROM
