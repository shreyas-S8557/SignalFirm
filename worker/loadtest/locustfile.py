"""Phase 9 -- basic load test.

    pip install locust
    WORKER_API_KEY=... locust -f loadtest/locustfile.py --host http://localhost:8000

Then open http://localhost:8089 to set concurrent users / ramp-up and
start the run, or drive it headless:

    locust -f loadtest/locustfile.py --host http://localhost:8000 \\
        --headless -u 20 -r 2 -t 5m --csv=loadtest-results

This is intentionally read-heavy by weight: `/health`, `/jobs`, and
`/companies/{id}/workflow` (all cheap, no LLM call) are exercised far more
than `/companies/{id}/icp-score` or `/companies/{id}/outreach/draft`
(LLM-backed, meant to run once per company, not hammered). Point
COMPANY_IDS at real ids from your Twenty workspace before running anything
beyond the read-only tasks -- with no ids configured, the write-ish tasks
are skipped rather than 404ing repeatedly.

This does not replace a real capacity-planning exercise (that needs your
actual Twenty instance's latency, your actual LLM provider's rate limits,
and your actual expected concurrency) -- see worker/README.md's Production
Readiness section for what's still a deployment-specific decision.
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, task

COMPANY_IDS = [c.strip() for c in os.getenv("LOADTEST_COMPANY_IDS", "").split(",") if c.strip()]
API_KEY = os.getenv("WORKER_API_KEY", "")


class WorkerUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        if API_KEY:
            self.client.headers.update({"X-Api-Key": API_KEY})

    @task(10)
    def health(self) -> None:
        self.client.get("/health", name="/health")

    @task(5)
    def list_jobs(self) -> None:
        self.client.get("/jobs", name="/jobs")

    @task(5)
    def company_workflow(self) -> None:
        if not COMPANY_IDS:
            return
        company_id = random.choice(COMPANY_IDS)
        self.client.get(f"/companies/{company_id}/workflow", name="/companies/[id]/workflow")

    @task(3)
    def company_insights(self) -> None:
        if not COMPANY_IDS:
            return
        company_id = random.choice(COMPANY_IDS)
        self.client.get(f"/companies/{company_id}/insights", name="/companies/[id]/insights")

    @task(1)
    def icp_score(self) -> None:
        # Low weight on purpose -- this triggers a real scoring run (a
        # handful of Twenty API calls + a rubric write), not something a
        # normal traffic pattern would hit repeatedly per company.
        if not COMPANY_IDS:
            return
        company_id = random.choice(COMPANY_IDS)
        self.client.post(f"/companies/{company_id}/icp-score", name="/companies/[id]/icp-score")

    @task(1)
    def daily_digest(self) -> None:
        self.client.get("/recommendations/daily-digest", name="/recommendations/daily-digest")
