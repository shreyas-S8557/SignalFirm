"""Standalone process that automatically enriches companies which are
missing enrichment or overdue for it, on a daily schedule. This is Phase
4's "Automatic execution" requirement.

    python -m scrapegraph_worker.enrichment_scheduler_main

Same shape as `recommendations_scheduler_main.py` (its own long-running
process using APScheduler's BlockingScheduler) for the same reasons: needs
to stay alive continuously to fire at the scheduled hour, and shouldn't
share a process with the request-serving `api` service.

Disabled by default (`ENRICHMENT_SCHEDULE_ENABLED=false`) -- running an
unattended crawl of every company's website on a schedule is a bigger
default footprint than the rest of this service has, so it's opt-in rather
than on by default. Even when enabled, a single run is capped at
`ENRICHMENT_MAX_PER_RUN` companies (see config.py) rather than sweeping an
entire workspace in one pass.

If you'd rather trigger enrichment from an external cron/scheduler you
already run, hit `POST /enrichment/jobs` (see api.py) with your own
company_ids instead of running this at all.
"""

from __future__ import annotations

import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from .config import load_settings
from .observability import configure_logging
from .enrichment.engine import enrich_company
from .enrichment.models import EnrichmentStatus
from .enrichment.scheduling import find_companies_due_for_enrichment
from .twenty_client import TwentyClient

configure_logging()  # Phase 9 -- structured logging + optional Sentry, see observability.py
logger = logging.getLogger(__name__)


def run_once() -> None:
    """Finds companies due for enrichment and enriches each one in-process
    (not via the RQ queue -- this process already runs on its own schedule,
    same as recommendations_scheduler_main.py's digest send, so there's no
    need to hop through another queue). Exposed as its own function for
    tests and manual runs, same convention as recommendations_scheduler_main.
    """
    settings = load_settings()
    with TwentyClient(settings.twenty) as client:
        company_ids = find_companies_due_for_enrichment(
            client,
            stale_after_days=settings.enrichment_schedule.stale_after_days,
            max_results=settings.enrichment_schedule.max_companies_per_run,
        )

        succeeded = partial = failed = 0
        for company_id in company_ids:
            result = enrich_company(client, company_id, llm_settings=settings.llm)
            if result.status == EnrichmentStatus.SUCCEEDED:
                succeeded += 1
            elif result.status == EnrichmentStatus.PARTIAL:
                partial += 1
            else:
                failed += 1

    logger.info(
        "Scheduled enrichment sweep complete: candidates=%d succeeded=%d partial=%d failed=%d",
        len(company_ids),
        succeeded,
        partial,
        failed,
    )


def main() -> int:
    settings = load_settings()
    if not settings.enrichment_schedule.enabled:
        logger.info("ENRICHMENT_SCHEDULE_ENABLED is false -- exiting without starting the scheduler.")
        return 0

    scheduler = BlockingScheduler(timezone=settings.enrichment_schedule.timezone)
    scheduler.add_job(
        run_once,
        trigger="cron",
        hour=settings.enrichment_schedule.schedule_hour,
        minute=settings.enrichment_schedule.schedule_minute,
        id="automatic-company-enrichment",
    )
    logger.info(
        "Enrichment scheduler started -- sweep at %02d:%02d %s (stale_after_days=%d, max_per_run=%d)",
        settings.enrichment_schedule.schedule_hour,
        settings.enrichment_schedule.schedule_minute,
        settings.enrichment_schedule.timezone,
        settings.enrichment_schedule.stale_after_days,
        settings.enrichment_schedule.max_companies_per_run,
    )
    scheduler.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
