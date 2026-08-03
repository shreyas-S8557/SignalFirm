"""FastAPI service: the front door for triggering scrape/sync jobs and
monitoring their progress. Run with:

    uvicorn scrapegraph_worker.api:app --reload

Actual scraping happens in a separate RQ worker process
(`python -m scrapegraph_worker.worker_main`) -- this process only enqueues
jobs and reads their recorded progress, so it stays responsive even while a
scrape is running.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .config import load_settings
from .conversation.analyzer import analyze_reply
from .conversation.llm_client import LLMClient
from .conversation.models import ReplyAnalysisRequest
from .conversation.twenty_push import push_conversation_signal_to_twenty
from .jobs import enqueue_import_job
from .models import JobRecord, JobStage
from .progress import JobStore

app = FastAPI(title="Scrapegraph Worker", version="0.1.0")
_settings = load_settings()
_store = JobStore(_settings.job_store_url.replace("sqlite:///", ""))


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
