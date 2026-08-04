"""Finds which companies are due for (re-)enrichment: never enriched, or
last enriched more than `stale_after_days` ago.

Filtered client-side after a bounded fetch rather than pushed down as a
Twenty REST filter -- Twenty's REST filter grammar's support for null/date-
range comparisons on a custom field isn't something this module wants to
depend on being available; a plain fetch-then-filter is simpler and the
company counts this is meant for (tens to low thousands per workspace) make
that fine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from ..twenty_client import TwentyClient

# Twenty companies list can be large; this is a safety cap on how many
# candidate companies get pulled down before filtering, independent of
# EnrichmentScheduleSettings.max_companies_per_run (which caps the actual
# enrichment batch size after filtering).
_CANDIDATE_FETCH_LIMIT = 500


def find_companies_due_for_enrichment(
    client: TwentyClient,
    *,
    stale_after_days: int,
    max_results: int,
) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_after_days)

    companies = client.find_records(
        "companies",
        limit=_CANDIDATE_FETCH_LIMIT,
        depth=0,
        order_by="createdAt[AscNullsLast]",  # oldest-created-first: prioritize companies that have waited longest
    )

    due: list[str] = []
    for company in companies:
        if _is_due(company.get("lastEnrichedAt"), cutoff):
            due.append(company["id"])
        if len(due) >= max_results:
            break
    return due


def _is_due(last_enriched_at: Optional[str], cutoff: datetime) -> bool:
    if not last_enriched_at:
        return True
    try:
        enriched_dt = datetime.fromisoformat(last_enriched_at.replace("Z", "+00:00"))
    except ValueError:
        # Unparseable timestamp -- treat conservatively as "due" rather
        # than silently skipping the company forever.
        return True
    return enriched_dt < cutoff
