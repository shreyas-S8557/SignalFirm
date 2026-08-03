"""Environment-driven configuration for the Scrapegraph worker/service.

Nothing here talks to the network at import time -- safe to import in tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TwentySettings:
    # Base URL of the Twenty instance, e.g. "https://crm.yourcompany.com" or
    # "http://localhost:3000" for a local self-hosted dev server.
    base_url: str = field(default_factory=lambda: os.getenv("TWENTY_BASE_URL", "http://localhost:3000"))
    # Workspace API key, created under Settings -> APIs & Webhooks in Twenty.
    api_key: str = field(default_factory=lambda: os.getenv("TWENTY_API_KEY", ""))
    # Request timeout for calls into Twenty's REST Core API.
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv("TWENTY_TIMEOUT_SECONDS", "30")))
    # Twenty enforces max 60 records per batch call -- kept as a named constant
    # so call sites never hardcode a magic number.
    max_batch_size: int = 60
    # Shared secret the worker sends on progress-webhook calls into the Twenty
    # App's HTTP route, and that the Twenty App is expected to validate.
    webhook_shared_secret: str = field(default_factory=lambda: os.getenv("TWENTY_WEBHOOK_SHARED_SECRET", ""))
    # Full URL of the Twenty App's progress-webhook logic function route, e.g.
    # "https://crm.yourcompany.com/s/crm-sync/job-progress". Optional -- if
    # unset, progress is tracked locally only (still visible via the worker's
    # own /jobs API) and never pushed into Twenty's ResearchJob/EnrichmentJob
    # records.
    progress_webhook_url: str = field(default_factory=lambda: os.getenv("TWENTY_PROGRESS_WEBHOOK_URL", ""))


@dataclass(frozen=True)
class QueueSettings:
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    queue_name: str = field(default_factory=lambda: os.getenv("SCRAPE_QUEUE_NAME", "scrapegraph-jobs"))
    job_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("SCRAPE_JOB_TIMEOUT_SECONDS", "3600")))
    default_retry_limit: int = field(default_factory=lambda: int(os.getenv("SCRAPE_JOB_RETRY_LIMIT", "2")))


@dataclass(frozen=True)
class WorkerSettings:
    twenty: TwentySettings = field(default_factory=TwentySettings)
    queue: QueueSettings = field(default_factory=QueueSettings)
    # Where job state (progress, logs, counts) is persisted for the /jobs API.
    # SQLite is enough for a single-instance worker; swap for Postgres by
    # changing this URL if the worker is ever scaled horizontally.
    job_store_url: str = field(default_factory=lambda: os.getenv("JOB_STORE_URL", "sqlite:///./scrapegraph_jobs.db"))
    dry_run: bool = field(default_factory=lambda: _env_bool("SCRAPE_DRY_RUN", False))


def load_settings() -> WorkerSettings:
    return WorkerSettings()
