"""Standalone process that sweeps for due follow-up-sequence steps (see
`outbound/sequence.py`) and dispatches each one to the right send adapter,
on a daily schedule.

    python -m scrapegraph_worker.outbound_scheduler_main

Same shape as `enrichment_scheduler_main.py` / `recommendations_scheduler_
main.py` -- its own long-running BlockingScheduler process, kept separate
from the request-serving `api` service.

What actually happens to a "due" step depends entirely on its channel:
EMAIL sends for real only when `OUTBOUND_AUTO_SEND_EMAIL=true` (and even
then, `OUTBOUND_DRY_RUN` still short-circuits to a log line); every other
channel (LinkedIn, call) is always QUEUED_FOR_MANUAL_SEND -- see
outbound/send/*_adapter.py for why. Either way, `mark_step_sent` is called
so the same step is never presented twice, whether a human sent it
manually or the email adapter sent it automatically.

Unlike the enrichment sweep, there's no "disabled by default" flag here:
this process only does anything if sequences have actually been scheduled
(which itself only happens after a human-reviewable draft exists), and
every non-email channel is inherently manual regardless of whether this
process runs at all. Run it to get a daily "what's due" surface + automatic
email sends where opted in; skip running it and the drafts are still fully
visible as Notes on the Company/Person in Twenty either way.
"""

from __future__ import annotations

import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from .config import load_settings
from .observability import configure_logging
from .outbound.send.base import SendOutcome
from .outbound.send.router import get_adapter
from .outbound.sequence import SequenceStore

configure_logging()  # Phase 9 -- structured logging + optional Sentry, see observability.py
logger = logging.getLogger(__name__)


def run_once() -> None:
    settings = load_settings()
    store = SequenceStore(settings.job_store_url.replace("sqlite:///", ""))

    due = store.due_steps(limit=settings.outbound.max_sequence_steps_per_run)
    sent = queued = failed = 0

    for item in due:
        step = item["step"]
        adapter = get_adapter(step.channel, settings.outbound)
        recipient = item.get("recipient_email") or ""

        result = adapter.send(recipient=recipient, subject=None, body=step.body)
        store.mark_step_sent(person_id=item["person_id"], step_number=step.step_number)

        if result.outcome == SendOutcome.SENT:
            sent += 1
        elif result.outcome == SendOutcome.FAILED:
            failed += 1
            logger.warning(
                "Follow-up step %d for person %s failed: %s", step.step_number, item["person_id"], result.error_message
            )
        else:
            queued += 1

    logger.info(
        "Outbound sequence sweep complete: due=%d sent=%d queued_for_manual_send=%d failed=%d",
        len(due),
        sent,
        queued,
        failed,
    )


def main() -> int:
    settings = load_settings()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_once, trigger="cron", hour=8, minute=0, id="outbound-sequence-sweep")
    logger.info(
        "Outbound sequence scheduler started -- daily sweep at 08:00 UTC (auto_send_email=%s, dry_run=%s).",
        settings.outbound.auto_send_email,
        settings.outbound.dry_run,
    )
    scheduler.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
