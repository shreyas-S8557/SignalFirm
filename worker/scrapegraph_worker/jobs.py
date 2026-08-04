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
from .enrichment.engine import enrich_company
from .enrichment.models import EnrichmentStatus
from .models import JobRecord, JobStage
from .progress import JobStore, push_progress_to_twenty
from .research.engine import research_company
from .research.models import ResearchStatus
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
            newly_created_company_ids: set[str] = set()
            for row_index, lead in enumerate(load_scraped_rows(csv_path), start=1):
                result = sync_lead(client, lead, source_run_id=job_id)
                _tally(job, result.outcome.value)
                job.processed_rows = row_index
                if result.company_id:
                    newly_created_company_ids.add(result.company_id)
                if row_index % 10 == 0 or row_index == total:
                    checkpoint()  # periodic checkpoint, not on every single row

            # Phase 7 -- Workflow Automation: chain Import -> Enrichment
            # automatically when AUTO_ENRICH_ON_IMPORT=true (off by
            # default -- see config.py::WorkflowSettings). Best-effort and
            # tolerant of per-company failure, same as the sync loop above
            # -- one company's crawl failing must never fail the import job
            # that already succeeded.
            if settings.workflow.auto_enrich_on_import and newly_created_company_ids:
                checkpoint(stage=JobStage.ENRICHING)
                for company_id in newly_created_company_ids:
                    try:
                        enrichment_result = enrich_company(client, company_id, llm_settings=settings.llm)
                        if enrichment_result.status == EnrichmentStatus.FAILED:
                            logger.info(
                                "Auto-enrichment failed for company %s: %s",
                                company_id,
                                enrichment_result.error_message,
                            )
                            continue  # no grounding material -> research would fail anyway

                        # Phase 5 -- Research Automation: the "automatic
                        # research after scraping" hand-off. Gated on its
                        # own flag (research costs LLM tokens per company)
                        # and equally tolerant of per-company failure.
                        if settings.workflow.auto_research_after_enrichment:
                            research_result = research_company(
                                client, company_id, llm_settings=settings.llm, source_run_id=job_id
                            )
                            if research_result.status == ResearchStatus.RESEARCH_FAILED:
                                logger.info(
                                    "Auto-research failed for company %s: %s",
                                    company_id,
                                    research_result.error_message,
                                )
                    except Exception:  # noqa: BLE001 - never let post-import automation fail the import job
                        logger.exception("Post-import automation raised for company %s", company_id)

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


# ---------------------------------------------------------------------------
# Phase 4 -- Company Enrichment batch jobs
#
# Same JobRecord/JobStore infrastructure as the scrape/sync import job above
# (reused rather than duplicated -- see models.py::JobStage.ENRICHING),
# polled the same way via GET /jobs/{id}. `company_ids` is stored in
# `params` for the same reason `repo_path`/`target` are on the import job:
# so `GET /jobs/{id}` can show what was actually requested.
# ---------------------------------------------------------------------------


def enqueue_enrichment_job(
    *,
    company_ids: list[str],
    settings: Optional[WorkerSettings] = None,
) -> str:
    settings = settings or load_settings()
    job_id = str(uuid.uuid4())
    store = JobStore(settings.job_store_url.replace("sqlite:///", ""))
    store.save(
        JobRecord(
            id=job_id,
            stage=JobStage.QUEUED,
            params={"kind": "enrichment", "company_ids": company_ids},
            total_rows=len(company_ids),
        )
    )
    queue = get_queue(settings)
    queue.enqueue(
        run_enrichment_job,
        job_id=job_id,
        company_ids=company_ids,
        job_timeout=settings.queue.job_timeout_seconds,
        retry=None,
    )
    return job_id


def run_enrichment_job(job_id: str, *, company_ids: list[str]) -> None:
    """Runs `enrich_company` for each company in the batch, checkpointing
    progress the same way `run_import_job` does. One company failing (e.g.
    unreachable site) does not stop the batch -- `enrich_company` already
    catches and reports per-company failures via EnrichmentStatus.FAILED,
    same as `sync_lead` does for a bad row.
    """
    settings = load_settings()
    store = JobStore(settings.job_store_url.replace("sqlite:///", ""))
    job = store.get(job_id) or JobRecord(
        id=job_id, params={"kind": "enrichment", "company_ids": company_ids}, total_rows=len(company_ids)
    )

    def checkpoint(**kwargs) -> None:
        for key, value in kwargs.items():
            setattr(job, key, value)
        store.save(job)
        push_progress_to_twenty(settings.twenty, job)

    try:
        checkpoint(stage=JobStage.ENRICHING)
        with TwentyClient(settings.twenty) as client:
            for index, company_id in enumerate(company_ids, start=1):
                result = enrich_company(client, company_id, llm_settings=settings.llm)
                if result.status == EnrichmentStatus.SUCCEEDED:
                    job.created_count += 1
                elif result.status == EnrichmentStatus.PARTIAL:
                    job.updated_count += 1
                else:
                    job.error_count += 1
                    if result.error_message:
                        job.errors.append(f"{company_id}: {result.error_message}")
                job.processed_rows = index
                if index % 5 == 0 or index == len(company_ids):
                    checkpoint()

        checkpoint(stage=JobStage.COMPLETED)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Enrichment batch job %s failed", job_id)
        job.errors.append(str(exc))
        checkpoint(stage=JobStage.FAILED, error_count=job.error_count + 1)
        raise
    finally:
        from datetime import datetime, timezone

        job.finished_at = datetime.now(timezone.utc)
        store.save(job)
