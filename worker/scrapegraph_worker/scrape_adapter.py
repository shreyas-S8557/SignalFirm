"""Adapter between this worker and the existing Scrapegraph pipeline.

Deliberate design choice: the scrape phase runs as a **subprocess**, not an
in-process import of `pipeline.orchestrator.run_pipeline`. Two reasons:

1. `scrapegraphai` drives a real Playwright browser and owns its own asyncio
   event loop; running it out-of-process means a stuck browser or a crash in
   that pipeline can't take down the worker process that's also serving the
   /jobs API and talking to Twenty.
2. The existing pipeline is a CLI script today (argparse in, CSV out) --
   subprocess is the integration surface it already has, so this adapter adds
   a worker/queue *around* Scrapegraph rather than rewriting Scrapegraph's
   internals, which matches "convert into a background worker" rather than
   "rebuild the scraper."

NOTE on naming: the CPA-firm collection entrypoint in the current repo is
`scripts/collect_us_angel_investors_1000.py` (its output path and comments
say CPA firms; the filename is a holdover from an earlier dataset). This is
flagged as technical debt in the architecture analysis (§2.2) -- worth
renaming, but not blocking. `SCRAPEGRAPH_ENTRYPOINT` below is intentionally
configurable so a rename doesn't require code changes here.
"""

from __future__ import annotations

import csv
import logging
import subprocess
import sys
from pathlib import Path
from typing import Iterator, Optional

from .models import ScrapedLead

logger = logging.getLogger(__name__)

# Relative to the Scrapegraph repo root (SCRAPEGRAPH_REPO_PATH in config/env).
SCRAPEGRAPH_ENTRYPOINT = "scripts/collect_us_angel_investors_1000.py"


class ScrapeSubprocessError(RuntimeError):
    pass


def run_scrape_phase(
    *,
    repo_path: str,
    target: int,
    phases: Optional[str] = None,
    output_csv: Optional[str] = None,
    fresh: bool = False,
    timeout_seconds: int = 3000,
) -> Path:
    """Runs the existing Scrapegraph CLI pipeline and returns the path to the
    CSV it wrote. Raises ScrapeSubprocessError on non-zero exit.
    """
    repo = Path(repo_path)
    entrypoint = repo / SCRAPEGRAPH_ENTRYPOINT
    if not entrypoint.exists():
        raise ScrapeSubprocessError(f"Scrapegraph entrypoint not found at {entrypoint}")

    cmd = [sys.executable, str(entrypoint), "--target", str(target)]
    if phases:
        cmd += ["--phases", phases]
    if output_csv:
        cmd += ["--output", output_csv]
    if fresh:
        cmd.append("--fresh")

    logger.info("Running scrape phase: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise ScrapeSubprocessError(
            f"Scrapegraph pipeline exited {result.returncode}\nstdout:\n{result.stdout[-4000:]}\n"
            f"stderr:\n{result.stderr[-4000:]}"
        )

    resolved_output = Path(output_csv) if output_csv else (repo / "data" / "us_cpa_partners_1000.csv")
    if not resolved_output.exists():
        raise ScrapeSubprocessError(f"Scrapegraph pipeline reported success but {resolved_output} does not exist")
    return resolved_output


def load_scraped_rows(csv_path: Path) -> Iterator[ScrapedLead]:
    """Streams `InvestorRow`-shaped CSV rows (see Scrapegraph's
    scripts/pipeline/models.py) into ScrapedLead. Company name / website are
    not present in today's row shape, so they're intentionally left unset
    here -- `sync.py`'s heuristic fallback and confidence handling take over
    from that point, rather than this loader guessing.
    """
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield ScrapedLead(
                full_name=row.get("name") or None,
                job_title=row.get("profile_title") or None,
                linkedin_url=row.get("linkedin_url") or None,
                email=row.get("email") or None,
                phone=row.get("phone") or None,
                location=row.get("location") or None,
                industry=row.get("industries") or None,
                source=row.get("source") or "scrapegraph",
                summary=row.get("summary") or None,
                company_name=row.get("company_name") or None,  # present only if upstream schema is extended
                website=row.get("website") or None,  # present only if upstream schema is extended
                raw=dict(row),
            )


def count_csv_rows(csv_path: Path) -> int:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return sum(1 for _ in csv.DictReader(fh))
