"""Tests for Phase 7 (Workflow Automation). No real network -- reuses
`FakeTwentyClient` and monkeypatches `enrichment.engine.website_crawler`
the same way `test_enrichment.py` does, since `workflow.engine.advance()`
calls straight into `enrichment.engine.enrich_company`.
"""

from __future__ import annotations

from scrapegraph_worker.config import LLMSettings
from scrapegraph_worker.enrichment import engine as enrichment_engine
from scrapegraph_worker.enrichment.models import CrawledPage
from scrapegraph_worker.workflow.derive import derive_workflow_state
from scrapegraph_worker.workflow.engine import advance, advance_all
from scrapegraph_worker.workflow.models import WorkflowStage

_LLM = LLMSettings(base_url="", model="")


def _reachable_pages():
    return [
        CrawledPage(
            url="https://acme.com/",
            status_code=200,
            html="<html><head><title>Acme</title></head></html>",
            text="Acme builds things.",
        )
    ]


# ---------------------------------------------------------------------------
# derive.py
# ---------------------------------------------------------------------------


def test_derive_state_imported_when_no_enrichment_job(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    state = derive_workflow_state(fake_client, company["id"])
    assert state.stage == WorkflowStage.IMPORTED
    assert state.next_action


def test_derive_state_failed_when_last_enrichment_failed(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs", {"status": "FAILED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"}
    )
    state = derive_workflow_state(fake_client, company["id"])
    assert state.stage == WorkflowStage.FAILED
    assert state.blocked


def test_derive_state_enriched_when_no_research_run_yet(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )
    state = derive_workflow_state(fake_client, company["id"])
    assert state.stage == WorkflowStage.ENRICHED
    assert not state.blocked
    assert state.next_action


def test_derive_state_pending_icp_score_after_research(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )
    fake_client.create_record(
        "researchJobs",
        {"status": "RESEARCHED", "company": {"id": company["id"]}, "createdAt": "2026-08-02T00:00:00Z"},
    )
    state = derive_workflow_state(fake_client, company["id"])
    assert state.stage == WorkflowStage.PENDING_ICP_SCORE
    assert not state.blocked
    assert "ICP Scoring" in state.next_action


def test_derive_state_pending_outreach_draft_after_icp_score(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )
    fake_client.create_record(
        "researchJobs",
        {"status": "RESEARCHED", "company": {"id": company["id"]}, "createdAt": "2026-08-02T00:00:00Z"},
    )
    fake_client.create_record(
        "icpScores",
        {"score": 72, "priority": "HIGH", "company": {"id": company["id"]}, "createdAt": "2026-08-03T00:00:00Z"},
    )
    state = derive_workflow_state(fake_client, company["id"])
    assert state.stage == WorkflowStage.PENDING_OUTREACH_DRAFT
    assert state.has_icp_score
    assert state.last_icp_priority == "HIGH"


def test_derive_state_outreach_drafted_and_blocked_pending_human_send(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )
    fake_client.create_record(
        "researchJobs",
        {"status": "RESEARCHED", "company": {"id": company["id"]}, "createdAt": "2026-08-02T00:00:00Z"},
    )
    fake_client.create_record(
        "icpScores",
        {"score": 72, "priority": "HIGH", "company": {"id": company["id"]}, "createdAt": "2026-08-03T00:00:00Z"},
    )
    note = fake_client.create_record("notes", {"title": "AI Outreach Draft - Acme", "body": "..."})
    fake_client.create_record("noteTargets", {"noteId": note["id"], "targetCompanyId": company["id"]})

    state = derive_workflow_state(fake_client, company["id"])
    assert state.stage == WorkflowStage.OUTREACH_DRAFTED
    assert state.blocked
    assert state.has_outreach_draft


def test_derive_state_research_failed(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )
    fake_client.create_record(
        "researchJobs",
        {"status": "RESEARCH_FAILED", "company": {"id": company["id"]}, "createdAt": "2026-08-02T00:00:00Z"},
    )
    state = derive_workflow_state(fake_client, company["id"])
    assert state.stage == WorkflowStage.RESEARCH_FAILED
    assert state.blocked


def test_derive_state_ignores_import_research_job_records(fake_client):
    """ResearchJob holds sync/import records too (status IMPORTED) -- those
    must not be mistaken for a research run having happened."""
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )
    fake_client.create_record(
        "researchJobs",
        {"status": "IMPORTED", "company": {"id": company["id"]}, "createdAt": "2026-08-02T00:00:00Z"},
    )
    state = derive_workflow_state(fake_client, company["id"])
    assert state.stage == WorkflowStage.ENRICHED
    assert not state.has_research


def test_derive_state_recommendations_active_when_someone_replied(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )
    fake_client.create_record(
        "people",
        {"company": {"id": company["id"]}, "lastConversationSignalAt": "2026-08-02T00:00:00Z"},
    )
    state = derive_workflow_state(fake_client, company["id"])
    assert state.stage == WorkflowStage.RECOMMENDATIONS_ACTIVE
    assert not state.blocked
    assert state.people_with_reply == 1
    assert state.latest_signal_at == "2026-08-02T00:00:00Z"


# ---------------------------------------------------------------------------
# engine.py -- advance()
# ---------------------------------------------------------------------------


def test_advance_runs_enrichment_when_imported(fake_client, monkeypatch):
    company = fake_client.create_record(
        "companies", {"name": "Acme", "domainName": {"primaryLinkUrl": "https://acme.com"}}
    )
    monkeypatch.setattr(
        enrichment_engine.website_crawler, "crawl_company_site", lambda domain, **kw: _reachable_pages()
    )

    result = advance(fake_client, company["id"], llm_settings=_LLM)

    assert result.stage_before == WorkflowStage.IMPORTED
    assert result.action_taken == "ran_enrichment"
    assert result.stage_after == WorkflowStage.ENRICHED
    assert len(fake_client.enrichment_jobs) == 1


def test_advance_runs_research_when_enriched(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )

    # _LLM is deliberately unconfigured, so research fails cleanly with a
    # stated reason rather than being skipped -- which is itself the
    # behavior worth asserting.
    result = advance(fake_client, company["id"], llm_settings=_LLM)

    assert result.stage_before == WorkflowStage.ENRICHED
    assert result.action_taken == "ran_research"
    assert result.errors
    # No new EnrichmentJob -- advance() moved on to the research step.
    assert len(fake_client.enrichment_jobs) == 1


def test_advance_runs_icp_scoring_when_pending(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme", "industry": "SaaS"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )
    fake_client.create_record(
        "researchJobs",
        {"status": "RESEARCHED", "company": {"id": company["id"]}, "createdAt": "2026-08-02T00:00:00Z"},
    )

    result = advance(fake_client, company["id"], llm_settings=_LLM)

    assert result.stage_before == WorkflowStage.PENDING_ICP_SCORE
    assert result.action_taken == "ran_icp_scoring"
    assert result.stage_after == WorkflowStage.PENDING_OUTREACH_DRAFT
    assert len(fake_client.icp_scores) == 1


def test_advance_is_no_op_when_outreach_drafted(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )
    fake_client.create_record(
        "researchJobs",
        {"status": "RESEARCHED", "company": {"id": company["id"]}, "createdAt": "2026-08-02T00:00:00Z"},
    )
    fake_client.create_record(
        "icpScores",
        {"score": 72, "priority": "HIGH", "company": {"id": company["id"]}, "createdAt": "2026-08-03T00:00:00Z"},
    )
    note = fake_client.create_record("notes", {"title": "AI Outreach Draft - Acme", "body": "..."})
    fake_client.create_record("noteTargets", {"noteId": note["id"], "targetCompanyId": company["id"]})

    result = advance(fake_client, company["id"], llm_settings=_LLM)

    assert result.action_taken == "no_op"
    assert result.stage_before == WorkflowStage.OUTREACH_DRAFTED
    assert len(fake_client.enrichment_jobs) == 1


def test_advance_is_no_op_when_recommendations_active(fake_client):
    company = fake_client.create_record("companies", {"name": "Acme"})
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "SUCCEEDED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )
    fake_client.create_record(
        "people", {"company": {"id": company["id"]}, "lastConversationSignalAt": "2026-08-02T00:00:00Z"}
    )

    result = advance(fake_client, company["id"], llm_settings=_LLM)

    assert result.action_taken == "no_op"
    assert result.stage_before == WorkflowStage.RECOMMENDATIONS_ACTIVE


def test_advance_retries_enrichment_after_failure(fake_client, monkeypatch):
    company = fake_client.create_record(
        "companies", {"name": "Acme", "domainName": {"primaryLinkUrl": "https://acme.com"}}
    )
    fake_client.create_record(
        "enrichmentJobs",
        {"status": "FAILED", "company": {"id": company["id"]}, "createdAt": "2026-08-01T00:00:00Z"},
    )
    monkeypatch.setattr(
        enrichment_engine.website_crawler, "crawl_company_site", lambda domain, **kw: _reachable_pages()
    )

    result = advance(fake_client, company["id"], llm_settings=_LLM)

    assert result.stage_before == WorkflowStage.FAILED
    assert result.action_taken == "ran_enrichment"
    # Retry wrote a second EnrichmentJob rather than mutating the first.
    assert len(fake_client.enrichment_jobs) == 2


def test_advance_all_chains_enrichment_then_research(fake_client, monkeypatch):
    """A freshly imported company should walk enrichment -> research in one
    call, and stop once nothing automatable is left."""
    company = fake_client.create_record(
        "companies", {"name": "Acme", "domainName": {"primaryLinkUrl": "https://acme.com"}}
    )
    monkeypatch.setattr(
        enrichment_engine.website_crawler, "crawl_company_site", lambda domain, **kw: _reachable_pages()
    )

    steps = advance_all(fake_client, company["id"], llm_settings=_LLM)

    actions = [s.action_taken for s in steps]
    assert actions[0] == "ran_enrichment"
    assert "ran_research" in actions
    # Chain terminates rather than looping.
    assert len(steps) <= 6
