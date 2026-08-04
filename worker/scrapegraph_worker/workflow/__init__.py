"""Phase 7: Workflow Automation.

Ties together the pipeline stages that already have real engines (Import,
Company Enrichment, Conversation Intelligence, Recommendations) into one
observable, per-company pipeline, and automates the concretely-automatable
hand-offs between them (today: Import -> Enrichment). It does **not**
fabricate stages for phases that don't have an engine yet (Research
Automation, ICP Scoring, AI Outbound Messaging) -- those show up as an
honest `BLOCKED` stage with a reason, not a fake pass-through.

Deliberate design choice: **no new Twenty custom object.** Every other
stage in this pipeline already writes an append-only audit record
(ResearchJob, EnrichmentJob, ConversationSignal) with a Company/Person
relation. Rather than adding a `WorkflowRun` record that could drift out of
sync with those, `derive.py` computes "what stage is this company at"
*on read*, directly from the records that already exist -- an
event-sourced view, not a second source of truth. See `derive.py`'s module
docstring for the exact stage logic.

  models.py   -- WorkflowStage enum, WorkflowState/WorkflowStepResult
  derive.py   -- derive_workflow_state(client, company_id) -> WorkflowState
  engine.py   -- advance(client, company_id, ...) -- executes the single
                 next automatable action, if any
"""
