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

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import load_settings
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
