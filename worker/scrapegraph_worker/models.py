"""Data models shared across the worker: scraped rows, job records, sync results.

These are intentionally decoupled from Twenty's own schema -- `sync.py` is the
only module that knows how a `ScrapedLead` maps onto Twenty records.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScrapedLead(BaseModel):
    """Normalized shape of a single scraped record, regardless of which
    Scrapegraph phase produced it (LinkedIn harvest, directory crawl, etc.).

    `company_name` / `website` are optional on purpose -- today's pipeline
    output (see scripts/pipeline/models.py::InvestorRow) doesn't reliably
    populate them yet (tracked as a known gap in the architecture analysis).
    When absent, `sync.py` falls back to a conservative heuristic and marks
    the resulting Company record as low-confidence rather than guessing hard.
    """

    # Person / contact
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    # Company
    company_name: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None

    # Provenance
    source: str = "scrapegraph"
    summary: Optional[str] = None
    raw: dict = Field(default_factory=dict)


class JobStage(str, Enum):
    QUEUED = "QUEUED"
    SCRAPING = "SCRAPING"
    DEDUPING = "DEDUPING"
    SYNCING = "SYNCING"
    ENRICHING = "ENRICHING"  # Phase 4: batch company-enrichment jobs (see jobs.py::run_enrichment_job)
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobRecord(BaseModel):
    """Persisted state for a single scrape/sync job, backing GET /jobs/{id}."""

    id: str
    stage: JobStage = JobStage.QUEUED
    params: dict = Field(default_factory=dict)
    total_rows: int = 0
    processed_rows: int = 0
    created_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None

    @property
    def progress_pct(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return round(100.0 * self.processed_rows / self.total_rows, 1)


class SyncOutcome(str, Enum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"
    ERROR = "ERROR"


class SyncResult(BaseModel):
    """What happened when one ScrapedLead was synced into Twenty."""

    outcome: SyncOutcome
    company_id: Optional[str] = None
    person_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    note_id: Optional[str] = None
    research_job_id: Optional[str] = None
    reason: Optional[str] = None
    matched_existing_company_id: Optional[str] = None
