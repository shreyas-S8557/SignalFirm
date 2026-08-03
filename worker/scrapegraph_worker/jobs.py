"""The actual unit of work an RQ worker executes: scrape -> sync -> progress.

This is the module RQ imports the job function from (`run_import_job`), and
is also called directly (no queue) by tests and by the CLI in `worker_main.py
--sync` for local runs without Redis.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from redis import Redis
from rq import Queue

from .config import WorkerSettings, load_settings
from .models import JobRecord, JobStage
from .progress import JobStore, push_progress_to_twenty
from .scrape_adapter import count_csv_rows, load_scraped_rows, run_scrape_phase
from .sync import sync_lead
from .twenty_client import TwentyClient

logger = logging.getLogger(__name__)


def get_queue(settings: Optional[WorkerSettings] = None) -> Queue:
    settings = settings or load_settings()
    redis_conn = Redis.from_url(settings.queue.redis_url)
    return Queue(settings.queue.queue_name, connection=redis_conn)


def enqueue_import_job(
    *,
    repo_path: str,
    target: int,
    phases: Optional[str] = None,
    settings: Optional[WorkerSettings] = None,
) -> str:
    settings = settings or load_settings()
    job_id = str(uuid.uuid4())
    store = JobStore(settings.job_store_url.replace("sqlite:///", ""))
    store.save(
        JobRecord(
            id=job_id,
            stage=JobStage.QUEUED,
            params={"repo_path": repo_path, "target": target, "phases": phases},
        )
    )
    queue = get_queue(settings)
    queue.enqueue(
        run_import_job,
        job_id=job_id,
        repo_path=repo_path,
        target=target,
        phases=phases,
        job_timeout=settings.queue.job_timeout_seconds,
        retry=None,  # explicit retry handled at the RQ Retry layer by callers if desired
    )
    return job_id


def run_import_job(
    job_id: str,
    *,
    repo_path: str,
    target: int,
    phases: Optional[str] = None,
) -> None:
    """The full pipeline for one job: scrape -> load rows -> sync each row
    into Twenty -> keep JobRecord (and optionally Twenty's own ResearchJob
    record via the webhook) up to date throughout.
    """
    settings = load_settings()
    store = JobStore(settings.job_store_url.replace("sqlite:///", ""))
    job = store.get(job_id) or JobRecord(id=job_id, params={"repo_path": repo_path, "target": target})

    def checkpoint(**kwargs) -> None:
        for key, value in kwargs.items():
            setattr(job, key, value)
        store.save(job)
        push_progress_to_twenty(settings.twenty, job)

    try:
        checkpoint(stage=JobStage.SCRAPING)
        csv_path = run_scrape_phase(repo_path=repo_path, target=target, phases=phases)
        total = count_csv_rows(csv_path)
        checkpoint(stage=JobStage.SYNCING, total_rows=total)

        with TwentyClient(settings.twenty) as client:
            for row_index, lead in enumerate(load_scraped_rows(csv_path), start=1):
                result = sync_lead(client, lead, source_run_id=job_id)
                _tally(job, result.outcome.value)
                job.processed_rows = row_index
                if row_index % 10 == 0 or row_index == total:
                    checkpoint()  # periodic checkpoint, not on every single row

        checkpoint(stage=JobStage.COMPLETED)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s failed", job_id)
        job.errors.append(str(exc))
        checkpoint(stage=JobStage.FAILED, error_count=job.error_count + 1)
        raise
    finally:
        from datetime import datetime, timezone

        job.finished_at = datetime.now(timezone.utc)
        store.save(job)


def _tally(job: JobRecord, outcome: str) -> None:
    if outcome == "CREATED":
        job.created_count += 1
    elif outcome == "UPDATED":
        job.updated_count += 1
    elif outcome == "DUPLICATE_SKIPPED":
        job.duplicate_count += 1
    elif outcome == "ERROR":
        job.error_count += 1
