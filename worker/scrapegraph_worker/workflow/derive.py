"""Derives a company's current pipeline stage from records that already
exist (EnrichmentJob, ResearchJob, ICPScore, an outbound-draft Note, and
ConversationSignal via People) -- no new storage.

Stage logic, in order of precedence:

1. No EnrichmentJob at all -> IMPORTED (next action: run enrichment)
2. Most recent EnrichmentJob FAILED -> FAILED (next action: retry)
3. Enriched, no research run yet -> ENRICHED (next action: run research)
4. Enriched, most recent research run failed -> RESEARCH_FAILED
   (next action: retry research)
5. Researched, no ICPScore yet -> PENDING_ICP_SCORE (next action: run ICP
   Scoring -- see icp/engine.py)
6. Most recent ICP scoring attempt failed -> ICP_SCORING_FAILED
7. ICP-scored, no outreach draft yet -> PENDING_OUTREACH_DRAFT (next
   action: draft outreach messaging -- see outbound/engine.py)
8. Outreach drafted, nobody has replied yet -> OUTREACH_DRAFTED. This is
   the honest stopping point: sending itself is a deliberate human action
   (or, for email specifically, an opt-in automatic send -- see
   OutboundSettings.auto_send_email), not something advance() does on its
   own. `blocked_reason` explains why.
9. At least one Person at this company has a ConversationSignal ->
   RECOMMENDATIONS_ACTIVE. The existing reply-intelligence-trigger.ts ->
   /conversation/analyze -> conversation-signal-webhook.ts loop already
   drives this independently; this function only reports that it happened.

Note that step 9 is checked ahead of everything else it would otherwise
follow: a reply short-circuits the whole chain, because once someone has
actually replied, the pre-contact pipeline's remaining gaps stop mattering
for that company.
"""

from __future__ import annotations

from ..twenty_client import TwentyClient
from .models import WorkflowStage, WorkflowState

_RESEARCH_STATUSES = {"RESEARCHED", "RESEARCH_FAILED"}


def derive_workflow_state(client: TwentyClient, company_id: str) -> WorkflowState:
    enrichment_jobs = client.find_records(
        "enrichmentJobs",
        filter_query=f"company.id[eq]:{company_id}",
        limit=1,
        depth=0,
        order_by="createdAt[DescNullsLast]",
    )
    research_jobs = client.find_records(
        "researchJobs",
        filter_query=f"company.id[eq]:{company_id}",
        limit=20,
        depth=0,
        order_by="createdAt[DescNullsLast]",
    )
    icp_scores = client.find_records(
        "icpScores",
        filter_query=f"company.id[eq]:{company_id}",
        limit=1,
        depth=0,
        order_by="createdAt[DescNullsLast]",
    )
    people = client.find_records("people", filter_query=f"company.id[eq]:{company_id}", limit=200, depth=0)

    last_enrichment = enrichment_jobs[0] if enrichment_jobs else None
    last_enrichment_status = last_enrichment.get("status") if last_enrichment else None

    # ResearchJob holds both import records (IMPORTED/SKIPPED/FAILED, written
    # by sync.py) and research records -- only the latter count here.
    research_runs = [r for r in research_jobs if r.get("status") in _RESEARCH_STATUSES]
    last_research = research_runs[0] if research_runs else None
    last_research_status = last_research.get("status") if last_research else None

    last_icp_score = icp_scores[0] if icp_scores else None

    # An outbound draft is recorded as a Note (see outbound/engine.py --
    # deliberately reuses the existing Note object rather than a new
    # custom Twenty object) tagged with a recognizable title prefix.
    outreach_notes = _find_outreach_notes(client, company_id)
    last_outreach_note = outreach_notes[0] if outreach_notes else None

    person_count = len(people)
    people_with_reply = sum(1 for p in people if p.get("lastConversationSignalAt"))
    latest_signal_at = max(
        (p["lastConversationSignalAt"] for p in people if p.get("lastConversationSignalAt")), default=None
    )

    def base(**overrides) -> WorkflowState:
        defaults = dict(
            company_id=company_id,
            has_enrichment=bool(last_enrichment),
            last_enrichment_status=last_enrichment_status,
            last_enrichment_at=last_enrichment.get("createdAt") if last_enrichment else None,
            has_research=bool(last_research),
            last_research_status=last_research_status,
            last_research_at=last_research.get("createdAt") if last_research else None,
            has_icp_score=bool(last_icp_score),
            last_icp_score=last_icp_score.get("score") if last_icp_score else None,
            last_icp_priority=last_icp_score.get("priority") if last_icp_score else None,
            has_outreach_draft=bool(last_outreach_note),
            last_outreach_status="DRAFTED" if last_outreach_note else None,
            person_count=person_count,
            people_with_reply=people_with_reply,
            latest_signal_at=latest_signal_at,
        )
        defaults.update(overrides)
        return WorkflowState(**defaults)

    if people_with_reply > 0 and last_enrichment:
        return base(
            stage=WorkflowStage.RECOMMENDATIONS_ACTIVE,
            next_action=None,  # already covered by the daily digest
        )

    if not last_enrichment:
        return base(
            stage=WorkflowStage.IMPORTED,
            next_action="Run Company Enrichment (POST /companies/{id}/enrich or advance()).",
        )

    if last_enrichment_status == "FAILED":
        return base(
            stage=WorkflowStage.FAILED,
            blocked=True,
            blocked_reason="Most recent EnrichmentJob failed -- see its errorMessage.",
            next_action="Re-run enrichment (advance() will retry automatically).",
        )

    if last_research is None:
        return base(
            stage=WorkflowStage.ENRICHED,
            next_action="Run the research pass (POST /companies/{id}/research or advance()).",
        )

    if last_research_status == "RESEARCH_FAILED":
        return base(
            stage=WorkflowStage.RESEARCH_FAILED,
            blocked=True,
            blocked_reason="Most recent research run failed -- see its errorMessage.",
            next_action="Re-run research (advance() will retry automatically).",
        )

    if last_icp_score is None:
        return base(
            stage=WorkflowStage.PENDING_ICP_SCORE,
            next_action="Run ICP Scoring (POST /companies/{id}/icp-score or advance()).",
        )

    if _icp_score_failed(last_icp_score):
        return base(
            stage=WorkflowStage.ICP_SCORING_FAILED,
            blocked=True,
            blocked_reason="Most recent ICP scoring run failed -- see its reasoning field.",
            next_action="Re-run ICP Scoring (advance() will retry automatically).",
        )

    if last_outreach_note is None:
        return base(
            stage=WorkflowStage.PENDING_OUTREACH_DRAFT,
            next_action="Draft outreach messaging (POST /companies/{id}/outreach/draft or advance()).",
        )

    return base(
        stage=WorkflowStage.OUTREACH_DRAFTED,
        blocked=True,
        blocked_reason=(
            "Outreach drafts exist (see the company's Notes) but haven't been sent. Sending is a "
            "deliberate human action for every channel except email, which can optionally auto-send "
            "when OUTBOUND_AUTO_SEND_EMAIL=true (see worker/README.md's AI Outbound Messaging section "
            "and outbound/send/linkedin_adapter.py for why LinkedIn is never automated)."
        ),
        next_action="Review the drafted messages and send them (or mark the lead contacted).",
    )


def _icp_score_failed(record: dict) -> bool:
    # A failed ICPScore write is represented by score/priority never being
    # written (see icp/engine.py::_write_icp_score, which only sends
    # non-None fields) -- so a record with no `priority` at all indicates
    # the run errored before it had a result to write.
    return not record.get("priority")


def _find_outreach_notes(client: TwentyClient, company_id: str) -> list[dict]:
    notes = client.find_records(
        "notes",
        filter_query="title[ilike]:%AI Outreach Draft%",
        limit=50,
        depth=1,
        order_by="createdAt[DescNullsLast]",
    )
    matched = []
    for note in notes:
        targets = note.get("noteTargets") or []
        if any(
            (
                t.get("targetCompanyId") == company_id
                or t.get("companyId") == company_id
                or (t.get("targetCompany") or {}).get("id") == company_id
                or (t.get("company") or {}).get("id") == company_id
            )
            for t in targets
        ):
            matched.append(note)
    if matched:
        return matched

    # Fallback for clients (including the in-memory test fake) that don't
    # resolve the noteTargets relation via depth=1 -- fall back to a direct
    # noteTargets lookup the way sync.py's own tests exercise.
    return _find_outreach_notes_via_note_targets(client, company_id)


def _find_outreach_notes_via_note_targets(client: TwentyClient, company_id: str) -> list[dict]:
    note_targets = client.find_records(
        "noteTargets", filter_query=f"targetCompanyId[eq]:{company_id}", limit=50, depth=0
    )
    note_ids = {t.get("noteId") for t in note_targets if t.get("noteId")}
    if not note_ids:
        return []
    notes = client.find_records("notes", limit=200, depth=0, order_by="createdAt[DescNullsLast]")
    return [n for n in notes if n.get("id") in note_ids and "AI Outreach Draft" in (n.get("title") or "")]
