"""Job progress tracking.

Two independent things happen here, and callers can use either or both:

1. Local persistence (SQLite) of a JobRecord, so the worker's own
   `GET /jobs/{id}` endpoint can answer progress questions without depending
   on Twenty being reachable.
2. An optional push of the same progress info into Twenty (via the Twenty
   App's HTTP-route logic function, see twenty-app-crm-sync/), so progress is
   visible on the ResearchJob/EnrichmentJob record inside the CRM itself, not
   just via this service's API. This is best-effort: a failure to reach
   Twenty logs a warning and never fails the underlying scrape job.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import httpx

from .config import TwentySettings
from .models import JobRecord, JobStage

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
"""


class JobStore:
    """Minimal SQLite-backed key-value store for JobRecord JSON blobs.

    Deliberately not an ORM: this table has one job, store/load a pydantic
    model by id, and it needs to work with zero extra infra for a
    single-instance worker.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True) if Path(db_path).parent != Path(".") else None
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save(self, job: JobRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (id, data) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
                (job.id, job.model_dump_json()),
            )

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        return JobRecord.model_validate_json(row[0])

    def list(self, *, stage: Optional[JobStage] = None, limit: int = 50) -> list[JobRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT data FROM jobs ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        jobs = [JobRecord.model_validate_json(row[0]) for row in rows]
        if stage:
            jobs = [j for j in jobs if j.stage == stage]
        return jobs


def push_progress_to_twenty(settings: TwentySettings, job: JobRecord) -> None:
    """Best-effort POST of current job progress to the Twenty App's webhook
    route. No-op if `progress_webhook_url` isn't configured.
    """
    if not settings.progress_webhook_url:
        return
    try:
        httpx.post(
            settings.progress_webhook_url,
            timeout=10,
            headers={
                "Authorization": f"Bearer {settings.webhook_shared_secret}",
                "Content-Type": "application/json",
            },
            content=json.dumps(
                {
                    "sourceRunId": job.id,
                    "stage": job.stage.value,
                    "processedRows": job.processed_rows,
                    "totalRows": job.total_rows,
                    "createdCount": job.created_count,
                    "updatedCount": job.updated_count,
                    "duplicateCount": job.duplicate_count,
                    "errorCount": job.error_count,
                }
            ),
        )
    except httpx.HTTPError:
        logger.warning("Failed to push job %s progress to Twenty webhook", job.id, exc_info=True)
