from __future__ import annotations

from scrapegraph_worker.icp.models import ICPPriority
from scrapegraph_worker.icp.rubric import compute_icp_score, load_rubric


def test_rubric_loads_and_weights_sum_to_100():
    rubric = load_rubric()
    assert abs(sum(rubric["weights"].values()) - 100.0) < 0.5


def test_strong_fit_scores_high_priority():
    result = compute_icp_score(
        company_id="c1",
        industry="B2B SaaS",
        synced_people_count=40,
        buying_signal_count=6,
        hiring_signal_count=4,
        tech_stack_names=["HubSpot", "Segment"],
        ai_maturity="ADOPTING",
        pain_point_count=4,
        sales_angle_count=3,
        research_confidence=0.8,
        had_enrichment=True,
    )
    assert result.score >= 70
    assert result.priority is ICPPriority.HIGH
    assert result.rubric_version
    assert "industry_fit" in result.reasoning


def test_disqualified_industry_scores_low_on_that_criterion():
    result = compute_icp_score(
        company_id="c2",
        industry="Local Government",
        synced_people_count=10,
        buying_signal_count=0,
        hiring_signal_count=0,
        tech_stack_names=[],
        ai_maturity="UNKNOWN",
        pain_point_count=0,
        sales_angle_count=0,
        research_confidence=None,
        had_enrichment=False,
    )
    industry_criterion = next(c for c in result.criteria if c.name == "industry_fit")
    assert industry_criterion.points == 0.0
    assert result.priority is ICPPriority.LOW


def test_no_data_never_raises_and_stays_in_bounds():
    result = compute_icp_score(
        company_id="c3",
        industry=None,
        synced_people_count=0,
        buying_signal_count=0,
        hiring_signal_count=0,
        tech_stack_names=[],
        ai_maturity="UNKNOWN",
        pain_point_count=0,
        sales_angle_count=0,
        research_confidence=None,
        had_enrichment=False,
    )
    assert 0.0 <= result.score <= 100.0
    assert 0.0 <= result.confidence <= 1.0
    assert result.confidence < 0.3  # almost nothing to ground the score in


def test_competitor_tech_discounts_tech_stack_fit():
    rubric = load_rubric()
    rubric = dict(rubric)
    rubric["tech_stack_fit"] = dict(rubric["tech_stack_fit"])
    rubric["tech_stack_fit"]["competitor_tech"] = ["acme crm"]

    result = compute_icp_score(
        company_id="c4",
        industry="Software",
        synced_people_count=20,
        buying_signal_count=1,
        hiring_signal_count=0,
        tech_stack_names=["Acme CRM"],
        ai_maturity="EXPLORING",
        pain_point_count=0,
        sales_angle_count=0,
        research_confidence=None,
        had_enrichment=True,
        rubric=rubric,
    )
    tech_criterion = next(c for c in result.criteria if c.name == "tech_stack_fit")
    assert tech_criterion.raw_fraction <= 0.1
