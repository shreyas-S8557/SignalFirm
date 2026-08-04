"""RQ worker process entrypoint.

    python -m scrapegraph_worker.worker_main

Runs indefinitely, pulling jobs off the queue configured in `config.py` and
executing `jobs.run_import_job`. Scale horizontally by running multiple
instances of this process against the same Redis -- RQ handles the fan-out.
"""

from __future__ import annotations

import logging
import sys

from redis import Redis
from rq import Worker

from .config import load_settings
from .observability import configure_logging

configure_logging()  # Phase 9 -- structured logging + optional Sentry, see observability.py


def main() -> int:
    settings = load_settings()
    redis_conn = Redis.from_url(settings.queue.redis_url)
    worker = Worker([settings.queue.queue_name], connection=redis_conn)
    worker.work(with_scheduler=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
