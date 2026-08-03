"""Test fixtures. No network, no Redis, no real Twenty instance required --
`FakeTwentyClient` is an in-memory stand-in that implements the same surface
`sync.py` calls, so dedup/sync logic can be verified offline.
"""

from __future__ import annotations

import itertools
from typing import Optional

import pytest


class FakeTwentyClient:
    """Implements just the methods sync.py calls, backed by plain dicts."""

    def __init__(self):
        self._ids = itertools.count(1)
        self.companies: dict[str, dict] = {}
        self.people: dict[str, dict] = {}
        self.opportunities: dict[str, dict] = {}
        self.notes: dict[str, dict] = {}
        self.note_targets: list[dict] = []
        self.research_jobs: dict[str, dict] = {}
        self.calls: list[tuple] = []

    def _new_id(self) -> str:
        return str(next(self._ids))

    # -- generic dispatch used by sync.py --------------------------------

    def find_records(self, object_name_plural, *, filter_query=None, search_query=None, limit=25, depth=0):
        self.calls.append(("find_records", object_name_plural, filter_query))
        store = self._store_for(object_name_plural)
        if store is None:
            return []
        if not filter_query:
            return list(store.values())[:limit]
        # Extremely small filter-language subset for tests: "field[op]:value"
        field, rest = filter_query.split("[", 1)
        op, value = rest.split("]:", 1)
        value = value.strip("%").strip('"')
        results = []
        for record in store.values():
            actual = _get_path(record, field)
            if actual is None:
                continue
            if op == "eq" and actual == value:
                results.append(record)
            elif op == "ilike" and value.lower() in str(actual).lower():
                results.append(record)
        return results[:limit]

    def create_record(self, object_name_plural, fields):
        self.calls.append(("create_record", object_name_plural, fields))
        store = self._store_for(object_name_plural)
        record = {"id": self._new_id(), **fields}
        if object_name_plural == "noteTargets":
            self.note_targets.append(record)
            return record
        store[record["id"]] = record
        return record

    def update_record(self, object_name_plural, record_id, fields):
        self.calls.append(("update_record", object_name_plural, record_id, fields))
        store = self._store_for(object_name_plural)
        store[record_id].update(fields)
        return store[record_id]

    def find_company_by_domain(self, domain: str) -> Optional[dict]:
        for c in self.companies.values():
            if (c.get("domainName") or {}).get("primaryLinkUrl", "").endswith(domain):
                return c
        return None

    def find_person_by_email(self, email: str) -> Optional[dict]:
        for p in self.people.values():
            if (p.get("emails") or {}).get("primaryEmail") == email:
                return p
        return None

    def find_person_by_linkedin(self, linkedin_url: str) -> Optional[dict]:
        for p in self.people.values():
            if (p.get("linkedinLink") or {}).get("primaryLinkUrl") == linkedin_url:
                return p
        return None

    def _store_for(self, object_name_plural: str):
        return {
            "companies": self.companies,
            "people": self.people,
            "opportunities": self.opportunities,
            "notes": self.notes,
            "researchJobs": self.research_jobs,
        }.get(object_name_plural)


def _get_path(record: dict, dotted: str):
    value = record
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


@pytest.fixture
def fake_client() -> FakeTwentyClient:
    return FakeTwentyClient()
