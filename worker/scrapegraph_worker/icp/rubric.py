"""Deterministic ICP rubric scoring.

Every function here is pure -- plain scalars/collections in, a score out --
same "arithmetic on known-safe inputs, no network/IO, fully unit-testable"
shape as `recommendations/scorer.py`. `engine.py` is the only module that
does I/O (reading Company/EnrichmentJob/ResearchJob, writing ICPScore); this
module never touches TwentyClient or an LLM.
"""

from __future__ import annotations

import functools
import os
from typing import Any, Optional

import yaml

from .models import ICPCriterionResult, ICPPriority, ICPScoreResult

_DEFAULT_RUBRIC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "icp_rubric.yaml"
)


class RubricError(RuntimeError):
    pass


@functools.lru_cache(maxsize=8)
def load_rubric(path: Optional[str] = None) -> dict[str, Any]:
    """Loads and lightly validates the rubric YAML. Cached by path -- the
    rubric file doesn't change at runtime in a normal deployment, and
    re-parsing YAML on every scoring call would be wasted work in a batch
    sweep over hundreds of companies.
    """
    resolved = path or os.getenv("ICP_RUBRIC_PATH") or _DEFAULT_RUBRIC_PATH
    try:
        with open(resolved, "r", encoding="utf-8") as fh:
            rubric = yaml.safe_load(fh)
    except OSError as exc:
        raise RubricError(f"Could not read ICP rubric at {resolved}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RubricError(f"ICP rubric at {resolved} is not valid YAML: {exc}") from exc

    if not isinstance(rubric, dict) or "weights" not in rubric or "version" not in rubric:
        raise RubricError(f"ICP rubric at {resolved} is missing required top-level 'version'/'weights' keys.")

    total_weight = sum(float(w) for w in rubric["weights"].values())
    if abs(total_weight - 100.0) > 0.5:
        raise RubricError(
            f"ICP rubric weights sum to {total_weight}, not 100 -- see icp_rubric.yaml's header comment."
        )
    return rubric


def score_industry_fit(industry: Optional[str], cfg: dict[str, Any]) -> ICPCriterionResult:
    weight = float(cfg["weight"])
    text = (industry or "").strip().lower()

    if not text:
        return ICPCriterionResult(
            name="industry_fit", weight=weight, raw_fraction=0.0, points=0.0, detail="No industry on file."
        )

    disqualifiers = [d for d in cfg["disqualifying_industries"] if d.lower() in text]
    if disqualifiers:
        return ICPCriterionResult(
            name="industry_fit",
            weight=weight,
            raw_fraction=0.0,
            points=0.0,
            detail=f"Industry '{industry}' matches a disqualifying category ({', '.join(disqualifiers)}).",
        )

    hits = [t for t in cfg["target_industries"] if t.lower() in text]
    if hits:
        return ICPCriterionResult(
            name="industry_fit",
            weight=weight,
            raw_fraction=1.0,
            points=weight,
            detail=f"Industry '{industry}' matches target industry list ({', '.join(hits)}).",
        )

    return ICPCriterionResult(
        name="industry_fit",
        weight=weight,
        raw_fraction=0.3,
        points=weight * 0.3,
        detail=f"Industry '{industry}' is on file but doesn't match the target list -- partial credit only.",
    )


def score_company_size_fit(synced_people_count: int, cfg: dict[str, Any]) -> ICPCriterionResult:
    weight = float(cfg["weight"])
    n = max(0, synced_people_count)

    if n < cfg["too_small_below"]:
        fraction, detail = 0.2, f"Only {n} synced contact(s) -- likely too small to have a real buying process."
    elif n <= cfg["sweet_spot_max"]:
        fraction, detail = 1.0, f"{n} synced contacts -- within the {cfg['sweet_spot_min']}-{cfg['sweet_spot_max']} sweet spot."
    elif n > cfg["large_account_above"]:
        fraction = float(cfg["large_account_fraction"])
        detail = f"{n} synced contacts -- large account, partial credit (may need enterprise motion)."
    else:
        # Between sweet_spot_max and large_account_above: linearly taper
        # from full credit down to the large-account fraction.
        span = max(1, cfg["large_account_above"] - cfg["sweet_spot_max"])
        progress = (n - cfg["sweet_spot_max"]) / span
        fraction = 1.0 - progress * (1.0 - float(cfg["large_account_fraction"]))
        detail = f"{n} synced contacts -- above the sweet spot, tapering credit."

    return ICPCriterionResult(name="company_size_fit", weight=weight, raw_fraction=fraction, points=weight * fraction, detail=detail)


def _saturating_fraction(count: int, saturation_count: int) -> float:
    if saturation_count <= 0:
        return 0.0
    return max(0.0, min(1.0, count / saturation_count))


def score_buying_signal_strength(
    buying_signal_count: int, hiring_signal_count: int, cfg: dict[str, Any]
) -> ICPCriterionResult:
    weight = float(cfg["weight"])
    buying_fraction = _saturating_fraction(buying_signal_count, cfg["buying_signal_saturation_count"])
    hiring_fraction = _saturating_fraction(hiring_signal_count, cfg["hiring_signal_saturation_count"])
    fraction = buying_fraction * cfg["buying_signal_share"] + hiring_fraction * cfg["hiring_signal_share"]
    detail = f"{buying_signal_count} buying-signal hit(s), {hiring_signal_count} hiring-signal hit(s) from enrichment."
    return ICPCriterionResult(
        name="buying_signal_strength", weight=weight, raw_fraction=fraction, points=weight * fraction, detail=detail
    )


def score_tech_stack_fit(tech_stack_names: list[str], cfg: dict[str, Any]) -> ICPCriterionResult:
    weight = float(cfg["weight"])
    lowered = [t.lower() for t in tech_stack_names]

    if not lowered:
        return ICPCriterionResult(
            name="tech_stack_fit", weight=weight, raw_fraction=0.2, points=weight * 0.2, detail="No tech stack detected -- minimal partial credit."
        )

    competitor_hits = [c for c in cfg["competitor_tech"] if c.lower() in lowered]
    if competitor_hits:
        return ICPCriterionResult(
            name="tech_stack_fit",
            weight=weight,
            raw_fraction=0.1,
            points=weight * 0.1,
            detail=f"Runs a competing tool ({', '.join(competitor_hits)}) -- heavily discounted.",
        )

    complementary_hits = [c for c in cfg["complementary_tech"] if c.lower() in lowered]
    if complementary_hits:
        fraction = min(1.0, 0.5 + 0.15 * len(complementary_hits))
        return ICPCriterionResult(
            name="tech_stack_fit",
            weight=weight,
            raw_fraction=fraction,
            points=weight * fraction,
            detail=f"Runs complementary tooling ({', '.join(complementary_hits)}).",
        )

    return ICPCriterionResult(
        name="tech_stack_fit",
        weight=weight,
        raw_fraction=0.4,
        points=weight * 0.4,
        detail=f"Detected tech stack ({', '.join(tech_stack_names[:5])}) has no target/competitor match.",
    )


def score_ai_maturity_fit(ai_maturity: str, cfg: dict[str, Any]) -> ICPCriterionResult:
    weight = float(cfg["weight"])
    fraction = float(cfg["scores"].get(ai_maturity, cfg["scores"].get("UNKNOWN", 0.4)))
    detail = f"AI maturity signal: {ai_maturity}."
    return ICPCriterionResult(name="ai_maturity_fit", weight=weight, raw_fraction=fraction, points=weight * fraction, detail=detail)


def score_research_richness(
    pain_point_count: int, sales_angle_count: int, research_confidence: Optional[float], cfg: dict[str, Any]
) -> ICPCriterionResult:
    weight = float(cfg["weight"])

    if research_confidence is None:
        return ICPCriterionResult(
            name="research_richness",
            weight=weight,
            raw_fraction=0.0,
            points=0.0,
            detail="No research run yet -- this criterion contributes 0 until Research (Phase 5) has run.",
        )

    pain_fraction = _saturating_fraction(pain_point_count, cfg["pain_point_saturation_count"])
    angle_fraction = _saturating_fraction(sales_angle_count, cfg["sales_angle_saturation_count"])
    conf_fraction = max(0.0, min(1.0, research_confidence))
    fraction = (
        pain_fraction * cfg["pain_point_share"]
        + angle_fraction * cfg["sales_angle_share"]
        + conf_fraction * cfg["research_confidence_share"]
    )
    detail = (
        f"{pain_point_count} pain-point hypothesis(es), {sales_angle_count} sales-angle hypothesis(es), "
        f"research confidence {conf_fraction:.2f}."
    )
    return ICPCriterionResult(name="research_richness", weight=weight, raw_fraction=fraction, points=weight * fraction, detail=detail)


def compute_icp_score(
    *,
    company_id: str,
    industry: Optional[str],
    synced_people_count: int,
    buying_signal_count: int,
    hiring_signal_count: int,
    tech_stack_names: list[str],
    ai_maturity: str,
    pain_point_count: int,
    sales_angle_count: int,
    research_confidence: Optional[float],
    had_enrichment: bool,
    rubric: Optional[dict[str, Any]] = None,
) -> ICPScoreResult:
    """The one entry point `engine.py` calls. Returns a fully-populated,
    already-clamped `ICPScoreResult` -- never raises for bad/missing input
    (every criterion scorer above treats "no data for this criterion" as
    "0 points for this criterion," not an error).
    """
    rubric = rubric or load_rubric()
    weights = rubric["weights"]

    criteria = [
        score_industry_fit(industry, {"weight": weights["industry_fit"], **rubric["industry_fit"]}),
        score_company_size_fit(synced_people_count, {"weight": weights["company_size_fit"], **rubric["company_size_fit"]}),
        score_buying_signal_strength(
            buying_signal_count, hiring_signal_count, {"weight": weights["buying_signal_strength"], **rubric["buying_signal_strength"]}
        ),
        score_tech_stack_fit(tech_stack_names, {"weight": weights["tech_stack_fit"], **rubric["tech_stack_fit"]}),
        score_ai_maturity_fit(ai_maturity, {"weight": weights["ai_maturity_fit"], **rubric["ai_maturity_fit"]}),
        score_research_richness(
            pain_point_count, sales_angle_count, research_confidence, {"weight": weights["research_richness"], **rubric["research_richness"]}
        ),
    ]

    total = sum(c.points for c in criteria)

    thresholds = rubric["priority_thresholds"]
    if total >= thresholds["high"]:
        priority = ICPPriority.HIGH
    elif total >= thresholds["medium"]:
        priority = ICPPriority.MEDIUM
    else:
        priority = ICPPriority.LOW

    # Confidence in the *score itself* (not a criterion's raw_fraction) --
    # how much grounding material this run actually had, independent of
    # whether that material happened to score well or poorly. A confidently
    # LOW-fit company is still a useful, trustworthy result.
    confidence = 0.3 if had_enrichment else 0.0
    confidence += 0.3 if research_confidence is not None else 0.0
    confidence += 0.2 if tech_stack_names else 0.0
    confidence += 0.2 if (industry or "").strip() else 0.0

    reasoning = "\n".join(f"- {c.name} ({c.points:.1f}/{c.weight:.0f} pts): {c.detail}" for c in criteria)

    return ICPScoreResult(
        company_id=company_id,
        score=total,
        priority=priority,
        confidence=confidence,
        rubric_version=str(rubric["version"]),
        reasoning=reasoning,
        criteria=criteria,
    ).clamp()
