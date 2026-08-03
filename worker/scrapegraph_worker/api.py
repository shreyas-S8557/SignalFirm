"""FastAPI service: the front door for triggering scrape/sync jobs and
monitoring their progress. Run with:

    uvicorn scrapegraph_worker.api:app --reload

Actual scraping happens in a separate RQ worker process
(`python -m scrapegraph_worker.worker_main`) -- this process only enqueues
jobs and reads their recorded progress, so it stays responsive even while a
scrape is running.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .config import load_settings
from .conversation.analyzer import analyze_reply
from .conversation.llm_client import LLMClient
from .conversation.models import ReplyAnalysisRequest
from .conversation.twenty_push import push_conversation_signal_to_twenty
from .jobs import enqueue_import_job
from .models import JobRecord, JobStage
from .progress import JobStore
from .recommendations.delivery import deliver_digest
from .recommendations.engine import build_daily_digest
from .recommendations.models import DailyDigest
from .recommendations.render import render_markdown
from .twenty_client import TwentyClient

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


class CreateJobRequest(BaseModel):
    repo_path: str
    target: int = 100
    phases: Optional[str] = None


class CreateJobResponse(BaseModel):
    job_id: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


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


@app.get("/recommendations/daily-digest", response_model=DailyDigest)
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


@app.get("/people/{person_id}/conversation-signals")
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


@app.get("/companies/{company_id}/research-jobs")
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
    ICP fields are honestly null until the ICP Scoring milestone (see
    `company-latest-icp-score.field.ts`) starts writing them -- this
    endpoint never fabricates a score, it reports the scaffold as it is.
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
    generated_at: datetime


@app.get("/companies/{company_id}/insights", response_model=CompanyInsights)
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
        generated_at=datetime.now(timezone.utc),
    )
