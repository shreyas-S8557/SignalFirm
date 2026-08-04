"""FastAPI service: the front door for triggering scrape/sync jobs and
monitoring their progress. Run with:

    uvicorn scrapegraph_worker.api:app --reload

Actual scraping happens in a separate RQ worker process
(`python -m scrapegraph_worker.worker_main`) -- this process only enqueues
jobs and reads their recorded progress, so it stays responsive even while a
scrape is running.
"""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .config import load_settings
from .conversation.analyzer import analyze_reply
from .conversation.llm_client import LLMClient
from .conversation.models import ReplyAnalysisRequest
from .conversation.twenty_push import push_conversation_signal_to_twenty
from .enrichment.engine import enrich_company
from .enrichment.models import EnrichmentResult
from .icp.engine import score_company
from .icp.models import ICPScoreResult
from .jobs import enqueue_enrichment_job, enqueue_import_job
from .models import JobRecord, JobStage
from .observability import RateLimitMiddleware, RequestIdMiddleware, configure_logging, metrics_endpoint
from .outbound.engine import draft_outreach_for_company
from .outbound.models import OutboundMessageSet
from .progress import JobStore
from .recommendations.delivery import deliver_digest
from .recommendations.engine import build_daily_digest
from .recommendations.models import DailyDigest
from .recommendations.render import render_markdown
from .research.engine import research_company
from .research.models import ResearchResult
from .twenty_client import TwentyAPIError, TwentyClient
from .workflow.derive import derive_workflow_state
from .workflow.engine import advance as advance_workflow
from .workflow.engine import advance_all as advance_workflow_all
from .workflow.models import WorkflowState, WorkflowStepResult

configure_logging()

app = FastAPI(title="Scrapegraph Worker", version="0.1.0")
_settings = load_settings()
_store = JobStore(_settings.job_store_url.replace("sqlite:///", ""))

# The Phase 9 frontend (frontend/) is a separate origin (Vite dev server /
# static host) talking to this API directly from the browser, unlike every
# other caller in this repo (Twenty logic-functions, the RQ worker), which
# are server-to-server. Wide open by default the same way the rest of this
# service trusts its deployment network -- tighten via a settings field if
# this is ever exposed beyond an internal network.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Order matters: middleware runs outside-in on the request, inside-out on
# the response -- adding RequestIdMiddleware last means it's the outermost
# wrapper, so the request id it stamps covers (and its timing captures) the
# rate limiter's own work too.
app.add_middleware(
    RateLimitMiddleware,
    max_requests=_settings.rate_limit_max_requests,
    window_seconds=_settings.rate_limit_window_seconds,
)
app.add_middleware(RequestIdMiddleware)


def _require_worker_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key")) -> None:
    """Optional dependency (see config.py::WorkerSettings.worker_api_key).
    No-ops entirely when WORKER_API_KEY is unset, so this never breaks the
    Phase 9 standalone frontend's existing unauthenticated calls unless a
    deployer has explicitly opted in. Uses a constant-time comparison
    (`hmac.compare_digest`) rather than `!=` so response timing can't be
    used to brute-force the key one byte at a time.
    """
    if not _settings.worker_api_key:
        return
    if not x_api_key or not hmac.compare_digest(x_api_key, _settings.worker_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Api-Key")


class CreateJobRequest(BaseModel):
    repo_path: str
    target: int = 100
    phases: Optional[str] = None


class CreateJobResponse(BaseModel):
    job_id: str


@app.get("/health")
def health() -> dict:
    """Liveness only -- returns 200 the moment the process is up, with no
    dependency checks. A load balancer / orchestrator should use this to
    decide whether to restart the container, not whether to route traffic
    to it (that's `/health/ready`, below).
    """
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict:
    """Readiness -- actually exercises the two things this service can't
    function without: Twenty's REST API and the local job store. Returns
    503 (not just a JSON `false`) on failure, so a standard orchestrator
    health-check config (expects a non-2xx to mean "not ready") works
    without special-casing this endpoint.
    """
    checks: dict[str, Any] = {}

    try:
        with TwentyClient(_settings.twenty) as client:
            client.find_records("companies", limit=1, depth=0)
        checks["twenty"] = "ok"
    except TwentyAPIError as exc:
        checks["twenty"] = f"error: {exc}"
    except Exception as exc:  # noqa: BLE001 - readiness must report, not crash
        checks["twenty"] = f"error: {exc}"

    try:
        _store.get("__readiness_probe__")
        checks["job_store"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["job_store"] = f"error: {exc}"

    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", "checks": checks}


@app.get("/metrics")
def metrics():
    return metrics_endpoint()


@app.post("/jobs", response_model=CreateJobResponse)
def create_job(request: CreateJobRequest) -> CreateJobResponse:
    job_id = enqueue_import_job(repo_path=request.repo_path, target=request.target, phases=request.phases)
    return CreateJobResponse(job_id=job_id)


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = _store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {**job.model_dump(), "progress_pct": job.progress_pct}


@app.get("/jobs")
def list_jobs(stage: Optional[JobStage] = None, limit: int = 50) -> list[dict]:
    jobs = _store.list(stage=stage, limit=limit)
    return [{**j.model_dump(), "progress_pct": j.progress_pct} for j in jobs]


@app.post("/jobs/{job_id}/retry", response_model=CreateJobResponse)
def retry_job(job_id: str) -> CreateJobResponse:
    job = _store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.stage != JobStage.FAILED:
        raise HTTPException(status_code=400, detail=f"Job is in stage {job.stage}, not FAILED")
    new_job_id = enqueue_import_job(
        repo_path=job.params.get("repo_path", ""),
        target=job.params.get("target", 100),
        phases=job.params.get("phases"),
    )
    return CreateJobResponse(job_id=new_job_id)


# ---------------------------------------------------------------------------
# Phase 4 -- Company Enrichment
#
# Two ways to trigger a run, same split as the scrape/sync flow above:
# a synchronous single-company endpoint (mirrors /conversation/analyze --
# useful for an "Enrich now" button in the frontend that wants an immediate
# result) and an async batch endpoint reusing the same JobRecord/JobStore
# infra as /jobs (useful for "enrich every company synced in the last
# week" style runs). See enrichment/engine.py for the actual pipeline.
# ---------------------------------------------------------------------------


class EnrichCompanyResponse(BaseModel):
    company_id: str
    status: str
    provider: str
    confidence: float
    summary: Optional[str] = None
    tech_stack: list[str] = []
    ai_maturity: str
    ai_maturity_reasoning: Optional[str] = None
    hiring_signal_count: int
    buying_signal_count: int
    sources_checked: list[str] = []
    sources_failed: list[str] = []
    error_message: Optional[str] = None

    @classmethod
    def from_result(cls, result: EnrichmentResult) -> "EnrichCompanyResponse":
        return cls(
            company_id=result.company_id,
            status=result.status.value,
            provider=result.provider,
            confidence=result.confidence,
            summary=result.summary,
            tech_stack=[hit.name for hit in result.tech_stack],
            ai_maturity=result.ai_maturity.value,
            ai_maturity_reasoning=result.ai_maturity_reasoning,
            hiring_signal_count=len(result.hiring_signals),
            buying_signal_count=len(result.buying_signals),
            sources_checked=result.sources_checked,
            sources_failed=result.sources_failed,
            error_message=result.error_message,
        )


@app.post("/companies/{company_id}/enrich", response_model=EnrichCompanyResponse, dependencies=[Depends(_require_worker_api_key)])
def enrich_company_now(company_id: str) -> EnrichCompanyResponse:
    """Runs enrichment for one company synchronously and returns the
    result immediately (also written to Twenty as an EnrichmentJob record,
    same as the async path below). Site crawling + LLM synthesis for one
    company is a few seconds, not the minutes a scrape/import job takes --
    synchronous is the right shape here, unlike the CSV-import flow.
    """
    with TwentyClient(_settings.twenty) as client:
        result = enrich_company(client, company_id, llm_settings=_settings.llm)
    return EnrichCompanyResponse.from_result(result)


class EnrichBatchRequest(BaseModel):
    company_ids: list[str]


class EnrichBatchResponse(BaseModel):
    job_id: str
    company_count: int


@app.post("/enrichment/jobs", response_model=EnrichBatchResponse)
def create_enrichment_batch(request: EnrichBatchRequest) -> EnrichBatchResponse:
    """Enqueues an async batch run over `company_ids`. Poll the same
    `GET /jobs/{job_id}` used for scrape/sync jobs -- `stage` will show
    ENRICHING while it runs.
    """
    if not request.company_ids:
        raise HTTPException(status_code=400, detail="company_ids must not be empty")
    job_id = enqueue_enrichment_job(company_ids=request.company_ids)
    return EnrichBatchResponse(job_id=job_id, company_count=len(request.company_ids))


@app.get("/companies/{company_id}/enrichment-jobs", dependencies=[Depends(_require_worker_api_key)])
def get_company_enrichment_jobs(company_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Every EnrichmentJob for a company, newest first -- same shape as the
    Research tab's `GET /companies/{id}/research-jobs`.
    """
    with TwentyClient(_settings.twenty) as client:
        return client.find_records(
            "enrichmentJobs",
            filter_query=f"company.id[eq]:{company_id}",
            limit=limit,
            depth=0,
            order_by="createdAt[DescNullsLast]",
        )


# ---------------------------------------------------------------------------
# Phase 5 -- Research Automation
#
# Runs the LLM research pass over a company's existing enrichment data.
# Requires both a successful EnrichmentJob (grounding) and a configured
# LLM -- neither is faked or worked around, see research/engine.py.
# ---------------------------------------------------------------------------


class ResearchCompanyResponse(BaseModel):
    company_id: str
    status: str
    summary: Optional[str] = None
    pain_point_hypotheses: list[dict[str, str]] = []
    sales_angle_hypotheses: list[dict[str, str]] = []
    interpreted_buying_signals: list[dict[str, str]] = []
    confidence: float
    model_used: Optional[str] = None
    grounded_on_enrichment_job_id: Optional[str] = None
    error_message: Optional[str] = None

    @classmethod
    def from_result(cls, result: ResearchResult) -> "ResearchCompanyResponse":
        return cls(
            company_id=result.company_id,
            status=result.status.value,
            summary=result.summary,
            pain_point_hypotheses=[p.model_dump() for p in result.pain_point_hypotheses],
            sales_angle_hypotheses=[a.model_dump() for a in result.sales_angle_hypotheses],
            interpreted_buying_signals=[s.model_dump() for s in result.interpreted_buying_signals],
            confidence=result.confidence,
            model_used=result.model_used,
            grounded_on_enrichment_job_id=result.grounding.enrichment_job_id,
            error_message=result.error_message,
        )


@app.post(
    "/companies/{company_id}/research",
    response_model=ResearchCompanyResponse,
    dependencies=[Depends(_require_worker_api_key)],
)
def research_company_now(company_id: str) -> ResearchCompanyResponse:
    """Runs the research pass for one company synchronously. Returns
    RESEARCH_FAILED (not an HTTP error) when the company has no successful
    enrichment to ground on, or when no LLM is configured -- both are
    expected states with a stated reason, not server faults.
    """
    with TwentyClient(_settings.twenty) as client:
        result = research_company(client, company_id, llm_settings=_settings.llm)
    return ResearchCompanyResponse.from_result(result)


# ---------------------------------------------------------------------------
# Phase 7 -- Workflow Automation
#
# GET is read-only (derives the company's current pipeline stage from
# existing records -- see workflow/derive.py, no side effects). POST
# executes the single next automatable action, if any -- ICP Scoring and
# outreach drafting (see icp/engine.py, outbound/engine.py) are both
# automatable now; only OUTREACH_DRAFTED reports BLOCKED, since sending is
# a deliberate human step for every channel except opt-in email.
# ---------------------------------------------------------------------------


@app.get("/companies/{company_id}/workflow", response_model=WorkflowState, dependencies=[Depends(_require_worker_api_key)])
def get_company_workflow(company_id: str) -> WorkflowState:
    with TwentyClient(_settings.twenty) as client:
        return derive_workflow_state(client, company_id)


@app.post("/companies/{company_id}/workflow/advance", response_model=WorkflowStepResult, dependencies=[Depends(_require_worker_api_key)])
def advance_company_workflow(company_id: str) -> WorkflowStepResult:
    """Executes exactly one step. With two automatable actions now
    (enrichment, then research), a freshly imported company needs two
    calls -- or one call to `/advance-all` below.
    """
    with TwentyClient(_settings.twenty) as client:
        return advance_workflow(client, company_id, llm_settings=_settings.llm)


@app.post(
    "/companies/{company_id}/workflow/advance-all",
    response_model=list[WorkflowStepResult],
    dependencies=[Depends(_require_worker_api_key)],
)
def advance_company_workflow_all(company_id: str) -> list[WorkflowStepResult]:
    """Runs the automatable chain to completion (import -> enrichment ->
    research) and returns every step taken, in order, so the caller sees
    exactly what happened rather than just the end state.
    """
    with TwentyClient(_settings.twenty) as client:
        return advance_workflow_all(client, company_id, llm_settings=_settings.llm)


class ICPScoreResponse(BaseModel):
    company_id: str
    score: float
    priority: str
    confidence: float
    rubric_version: str
    reasoning: str
    error_message: Optional[str] = None

    @classmethod
    def from_result(cls, result: ICPScoreResult) -> "ICPScoreResponse":
        return cls(
            company_id=result.company_id,
            score=result.score,
            priority=result.priority.value,
            confidence=result.confidence,
            rubric_version=result.rubric_version,
            reasoning=result.reasoning,
            error_message=result.error_message,
        )


@app.post("/companies/{company_id}/icp-score", response_model=ICPScoreResponse, dependencies=[Depends(_require_worker_api_key)])
def score_company_icp(company_id: str) -> ICPScoreResponse:
    """Runs ICP Scoring for one company against the rubric in
    data/icp_rubric.yaml. Deterministic and network-light (no LLM call) --
    see icp/rubric.py's module docstring for why an ICP fit score is
    computed, not asked of a model.
    """
    with TwentyClient(_settings.twenty) as client:
        result = score_company(client, company_id)
    return ICPScoreResponse.from_result(result)


class OutreachDraftResponse(BaseModel):
    company_id: str
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    status: str
    confidence: float
    linkedin_connection_note: Optional[str] = None
    linkedin_message: Optional[str] = None
    email_variants: list[dict]
    meeting_request: Optional[dict] = None
    call_script: Optional[dict] = None
    follow_up_sequence: list[dict]
    note_id: Optional[str] = None
    error_message: Optional[str] = None

    @classmethod
    def from_result(cls, result: OutboundMessageSet) -> "OutreachDraftResponse":
        return cls(
            company_id=result.company_id,
            person_id=result.person_id,
            person_name=result.person_name,
            status=result.status.value,
            confidence=result.confidence,
            linkedin_connection_note=result.linkedin_connection_note,
            linkedin_message=result.linkedin_message,
            email_variants=[v.model_dump() for v in result.email_variants],
            meeting_request=result.meeting_request.model_dump() if result.meeting_request else None,
            call_script=result.call_script.model_dump() if result.call_script else None,
            follow_up_sequence=[s.model_dump(mode="json") for s in result.follow_up_sequence],
            note_id=result.note_id,
            error_message=result.error_message,
        )


@app.post(
    "/companies/{company_id}/outreach/draft",
    response_model=OutreachDraftResponse,
    dependencies=[Depends(_require_worker_api_key)],
)
def draft_company_outreach(company_id: str) -> OutreachDraftResponse:
    """Phase 6 -- drafts LinkedIn/email/call-script/follow-up-sequence
    outreach for the company's top contact and saves it as a Note (visible
    in Twenty's own Company/Person timeline). Never sends anything -- see
    outbound/send/linkedin_adapter.py and OutboundSettings.auto_send_email
    for exactly what is and isn't automated beyond drafting.
    """
    with TwentyClient(_settings.twenty) as client:
        result = draft_outreach_for_company(client, company_id, llm_settings=_settings.llm)
    return OutreachDraftResponse.from_result(result)


class ConversationAnalyzeResponse(BaseModel):
    status: str
    interest_level: str
    urgency: str
    sentiment: str
    objections: list[str]
    recommended_next_action: str
    recommended_reply_draft: Optional[str] = None
    recommended_follow_up_at: Optional[str] = None
    confidence: float
    pushed_to_twenty: bool
    error_message: Optional[str] = None


@app.post("/conversation/analyze", response_model=ConversationAnalyzeResponse)
def analyze_conversation_reply(
    request: ReplyAnalysisRequest,
    authorization: Optional[str] = Header(default=None),
) -> ConversationAnalyzeResponse:
    """Called by reply-intelligence-trigger.ts whenever a genuine inbound
    reply is detected. This is the new direction of the shared-secret
    handshake (Twenty -> worker) -- job-progress-webhook.ts is worker ->
    Twenty, this is the reverse, but the same secret and Bearer-header
    convention is reused on both sides (see application.config.ts).
    """
    expected = f"Bearer {_settings.twenty.webhook_shared_secret}"
    if not _settings.twenty.webhook_shared_secret or authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not _settings.llm.is_configured:
        raise HTTPException(
            status_code=503,
            detail="LLM_BASE_URL / LLM_MODEL are not configured -- Conversation Intelligence is disabled",
        )

    with LLMClient(_settings.llm) as client:
        result = analyze_reply(request, client, model_name=_settings.llm.model)

    pushed = push_conversation_signal_to_twenty(_settings.twenty, request, result)

    return ConversationAnalyzeResponse(
        status=result.status,
        interest_level=result.interest_level.value,
        urgency=result.urgency.value,
        sentiment=result.sentiment.value,
        objections=result.objections,
        recommended_next_action=result.recommended_next_action.value,
        recommended_reply_draft=result.recommended_reply_draft,
        recommended_follow_up_at=result.recommended_follow_up_at,
        confidence=result.confidence,
        pushed_to_twenty=pushed,
        error_message=result.error_message,
    )


@app.get("/recommendations/daily-digest", response_model=DailyDigest, dependencies=[Depends(_require_worker_api_key)])
def get_daily_digest() -> DailyDigest:
    """On-demand version of what `recommendations_scheduler_main.py` runs
    every morning -- same engine, same scoring, just computed synchronously
    on request rather than on a schedule. Useful for testing scoring
    changes, or for driving the digest from a scheduler you already run
    instead of this repo's own (see `POST .../send` below).
    """
    with TwentyClient(_settings.twenty) as client:
        return build_daily_digest(client)


@app.get("/recommendations/daily-digest.md", response_class=PlainTextResponse)
def get_daily_digest_markdown() -> str:
    """Same digest as above, pre-rendered as Markdown -- what actually gets
    emailed/Slacked every morning (see `recommendations/render.py`).
    """
    with TwentyClient(_settings.twenty) as client:
        digest = build_daily_digest(client)
    return render_markdown(digest)


class SendDailyDigestResponse(BaseModel):
    considered_count: int
    delivered: dict[str, bool]


@app.post("/recommendations/daily-digest/send", response_model=SendDailyDigestResponse)
def send_daily_digest() -> SendDailyDigestResponse:
    """Manually triggers today's digest through the same delivery transports
    (email/Slack/local-file fallback -- see `recommendations/delivery.py`)
    the scheduler uses. Handy for testing `DIGEST_*` env vars without
    waiting for the scheduled hour, or for triggering delivery from an
    external cron instead of running `recommendations_scheduler_main.py`.
    """
    with TwentyClient(_settings.twenty) as client:
        digest = build_daily_digest(client)
    markdown = render_markdown(digest)
    results = deliver_digest(_settings.digest, markdown=markdown)
    return SendDailyDigestResponse(considered_count=digest.considered_count, delivered=results)


# ---------------------------------------------------------------------------
# Phase 9 -- Frontend read endpoints
#
# Everything above this line existed before Phase 9. These three routes are
# thin, read-only passthroughs onto TwentyClient.find_records -- no new
# business logic, no new writes -- added because the frontend's Conversation
# panel, Research tab, and AI Insights panel each need a list Twenty's REST
# API already exposes but that nothing in this service queried yet.
# Pass-through dicts (not a typed response_model) deliberately: these mirror
# Twenty's own field names 1:1 (camelCase, as declared in twenty-app/), so
# the frontend types in frontend/src/api/types.ts are the source of truth
# for the shape, not a second Pydantic model that would just have to be kept
# in sync with the object definitions by hand.
# ---------------------------------------------------------------------------


@app.get("/people/{person_id}/conversation-signals", dependencies=[Depends(_require_worker_api_key)])
def get_person_conversation_signals(person_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Every ConversationSignal for a person, newest first -- the reply-by-
    reply history behind the Conversation panel. `Person.latestInterestLevel`
    etc. (used by the Recommendation Engine) is just the head of this list.
    """
    with TwentyClient(_settings.twenty) as client:
        return client.find_records(
            "conversationSignals",
            filter_query=f"person.id[eq]:{person_id}",
            limit=limit,
            depth=0,
            order_by="createdAt[DescNullsLast]",
        )


@app.get("/companies/{company_id}/research-jobs", dependencies=[Depends(_require_worker_api_key)])
def get_company_research_jobs(company_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Every ResearchJob for a company, newest first -- the Research tab's
    timeline of import/research attempts.
    """
    with TwentyClient(_settings.twenty) as client:
        return client.find_records(
            "researchJobs",
            filter_query=f"company.id[eq]:{company_id}",
            limit=limit,
            depth=0,
            order_by="createdAt[DescNullsLast]",
        )


class CompanyInsights(BaseModel):
    """Everything the AI Insights panel needs about one company, gathered
    from three reads (company + latest ICPScore + that company's People)
    into one response so the panel doesn't have to sequence its own calls.
    ICP fields are null until a company has actually gone through ICP
    Scoring (see `icp/engine.py` -- POST /companies/{id}/icp-score, or
    Workflow Automation's advance()) -- this endpoint never fabricates a
    score, it reports the scaffold as it is.
    """

    company_id: str
    company_name: Optional[str] = None
    latest_icp_score: Optional[float] = None
    latest_icp_priority: Optional[str] = None
    last_enriched_at: Optional[str] = None
    icp_reasoning: Optional[str] = None
    icp_rubric_version: Optional[str] = None
    research_job_count: int = 0
    last_research_at: Optional[str] = None
    person_count: int = 0
    people_by_interest_level: dict[str, int] = {}
    most_recent_signal_at: Optional[str] = None
    # Phase 4 -- Company Enrichment: the most recent EnrichmentJob, if any.
    # Honestly null until a company has actually been enriched (via
    # POST /companies/{id}/enrich or a batch run) -- never backfilled with
    # a placeholder, same "report the scaffold as it is" rule as the ICP
    # fields above.
    enrichment_status: Optional[str] = None
    enrichment_summary: Optional[str] = None
    enrichment_tech_stack: list[str] = []
    enrichment_ai_maturity: Optional[str] = None
    last_enrichment_at: Optional[str] = None
    generated_at: datetime


@app.get("/companies/{company_id}/insights", response_model=CompanyInsights, dependencies=[Depends(_require_worker_api_key)])
def get_company_insights(company_id: str) -> CompanyInsights:
    """Backs the AI Insights panel: rolls up ICP scoring (once that
    milestone writes it), research activity, and the Conversation
    Intelligence state of everyone at the company into one snapshot.
    """
    with TwentyClient(_settings.twenty) as client:
        company = client.get_record("companies", company_id, depth=0)
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")

        latest_icp = client.find_records(
            "icpScores",
            filter_query=f"company.id[eq]:{company_id}",
            limit=1,
            depth=0,
            order_by="createdAt[DescNullsLast]",
        )
        icp_reasoning = latest_icp[0].get("reasoning") if latest_icp else None
        icp_rubric_version = latest_icp[0].get("rubricVersion") if latest_icp else None

        research_jobs = client.find_records(
            "researchJobs",
            filter_query=f"company.id[eq]:{company_id}",
            limit=200,
            depth=0,
            order_by="createdAt[DescNullsLast]",
        )

        people = client.find_records(
            "people",
            filter_query=f"company.id[eq]:{company_id}",
            limit=200,
            depth=0,
        )

        latest_enrichment = client.find_records(
            "enrichmentJobs",
            filter_query=f"company.id[eq]:{company_id}",
            limit=1,
            depth=0,
            order_by="createdAt[DescNullsLast]",
        )

    by_interest: dict[str, int] = {}
    most_recent_signal_at: Optional[str] = None
    for person in people:
        level = person.get("latestInterestLevel") or "NONE"
        by_interest[level] = by_interest.get(level, 0) + 1
        signal_at = person.get("lastConversationSignalAt")
        if signal_at and (most_recent_signal_at is None or signal_at > most_recent_signal_at):
            most_recent_signal_at = signal_at

    return CompanyInsights(
        company_id=company_id,
        company_name=company.get("name"),
        latest_icp_score=company.get("latestIcpScore"),
        latest_icp_priority=company.get("latestIcpPriority"),
        last_enriched_at=company.get("lastEnrichedAt"),
        icp_reasoning=icp_reasoning,
        icp_rubric_version=icp_rubric_version,
        research_job_count=len(research_jobs),
        last_research_at=research_jobs[0].get("createdAt") if research_jobs else None,
        person_count=len(people),
        people_by_interest_level=by_interest,
        most_recent_signal_at=most_recent_signal_at,
        enrichment_status=latest_enrichment[0].get("status") if latest_enrichment else None,
        enrichment_summary=latest_enrichment[0].get("summary") if latest_enrichment else None,
        enrichment_tech_stack=(
            [t.strip() for t in latest_enrichment[0]["techStack"].split(",") if t.strip()]
            if latest_enrichment and latest_enrichment[0].get("techStack")
            else []
        ),
        enrichment_ai_maturity=latest_enrichment[0].get("aiMaturity") if latest_enrichment else None,
        last_enrichment_at=company.get("lastEnrichedAt"),
        generated_at=datetime.now(timezone.utc),
    )
