"""Standalone process that triggers the Recommendation Engine's daily
digest at a configured time every day.

    python -m scrapegraph_worker.recommendations_scheduler_main

Kept as its own long-running process, the same way `worker_main.py` is --
it needs to stay alive continuously to fire at the scheduled hour, and
shouldn't share a process with the request-serving `api` service. Uses
APScheduler's `BlockingScheduler`, which is enough here: unlike scrape jobs
(`jobs.py`, fanned out across RQ workers), exactly one digest should run per
day, on a single schedule, with no queueing or retries needed.

This process is optional -- if you'd rather trigger the digest from an
external cron/scheduler you already run, hit `POST
/recommendations/daily-digest/send` (see `api.py`) on whatever schedule you
like instead of running this at all.
"""

from __future__ import annotations

import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from .config import load_settings
from .recommendations.delivery import deliver_digest
from .recommendations.engine import build_daily_digest
from .recommendations.render import render_markdown
from .twenty_client import TwentyClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def run_once() -> None:
    """Builds and delivers one digest. Exposed as its own function so tests
    and manual runs (`python -c "from scrapegraph_worker.recommendations_scheduler_main import run_once; run_once()"`)
    don't need to spin up a scheduler.
    """
    settings = load_settings()
    with TwentyClient(settings.twenty) as client:
        digest = build_daily_digest(client)
    markdown = render_markdown(digest)
    results = deliver_digest(settings.digest, markdown=markdown)
    logger.info(
        "Daily digest delivered: considered=%d contact_today=%d ignore=%d hot=%d cold=%d transports=%s",
        digest.considered_count,
        len(digest.contact_today),
        len(digest.ignore),
        len(digest.hot),
        len(digest.cold),
        results,
    )


def main() -> int:
    settings = load_settings()
    scheduler = BlockingScheduler(timezone=settings.digest.timezone)
    scheduler.add_job(
        run_once,
        trigger="cron",
        hour=settings.digest.schedule_hour,
        minute=settings.digest.schedule_minute,
        id="daily-recommendation-digest",
    )
    logger.info(
        "Recommendation Engine scheduler started -- daily digest at %02d:%02d %s",
        settings.digest.schedule_hour,
        settings.digest.schedule_minute,
        settings.digest.timezone,
    )
    scheduler.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
