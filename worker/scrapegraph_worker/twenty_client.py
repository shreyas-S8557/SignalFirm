"""Thin, typed wrapper around Twenty's Core REST API.

Twenty generates a REST endpoint per object using its `namePlural`
(e.g. Company -> /rest/companies, Person -> /rest/people, Opportunity ->
/rest/opportunities, Note -> /rest/notes). Custom objects get the same
treatment (ResearchJob -> /rest/researchJobs, EnrichmentJob ->
/rest/enrichmentJobs, ICPScore -> /rest/icpScores), once the Twenty App in
`twenty-app-crm-sync/` has been synced into the workspace.

This module intentionally does zero business logic (no dedup, no field
mapping decisions) -- that all lives in `sync.py`. It just knows how to talk
to the API: auth header, base URL, batching, pagination, and turning non-2xx
responses into a single exception type the rest of the worker can catch.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Optional

import httpx

from .config import TwentySettings

logger = logging.getLogger(__name__)

# Twenty's default API rate limit is ~100 tokens / 60s. Bulk scrape sync
# exceeds that quickly; retry on 429 instead of failing every lead.
_MAX_RETRIES = 6
_RETRYABLE = {429, 502, 503, 504}


class TwentyAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, payload: Any = None):
        super().__init__(f"Twenty API error {status_code}: {message}")
        self.status_code = status_code
        self.payload = payload


class TwentyClient:
    """Sync HTTP client. Kept synchronous deliberately -- the worker calls this
    from RQ jobs (which are themselves synchronous), so there's no async
    runtime to plug into here.
    """

    def __init__(self, settings: TwentySettings, http_client: Optional[httpx.Client] = None):
        self._settings = settings
        self._http = http_client or httpx.Client(
            base_url=settings.base_url.rstrip("/"),
            timeout=settings.timeout_seconds,
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "TwentyClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- low-level helpers ---------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        last_error: Optional[TwentyAPIError] = None
        for attempt in range(_MAX_RETRIES):
            response = self._http.request(method, path, **kwargs)
            if response.status_code in _RETRYABLE:
                # Prefer Retry-After when present; otherwise exponential backoff.
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else min(2 ** attempt, 30)
                except ValueError:
                    delay = min(2 ** attempt, 30)
                logger.warning(
                    "Twenty %s %s -> %s; retry %s/%s in %.1fs",
                    method,
                    path,
                    response.status_code,
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                try:
                    payload = response.json()
                    message = payload.get("messages", [payload]) if isinstance(payload, dict) else payload
                except ValueError:
                    payload = response.text
                    message = payload
                last_error = TwentyAPIError(response.status_code, str(message), payload)
                continue
            if response.status_code >= 400:
                try:
                    payload = response.json()
                    message = payload.get("messages", [payload]) if isinstance(payload, dict) else payload
                except ValueError:
                    payload = response.text
                    message = payload
                raise TwentyAPIError(response.status_code, str(message), payload)
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        assert last_error is not None
        raise last_error

    # -- generic record CRUD ---------------------------------------------

    def find_records(
        self,
        object_name_plural: str,
        *,
        filter_query: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 25,
        depth: int = 0,
        order_by: Optional[str] = None,
    ) -> list[dict]:
        """GET /rest/{objectNamePlural}. `filter_query` is Twenty's REST filter
        syntax, e.g. "domainName[eq]:acme.com" or "name[ilike]:%acme%".
        `order_by` is Twenty's REST sort syntax, e.g.
        "createdAt[DescNullsLast]" -- used by the Recommendation Engine
        (`recommendations/engine.py`) to fetch a person's *most recent*
        ConversationSignal rather than an arbitrary one. Omitted by default
        so existing callers that don't care about order see no change.
        """
        params: dict[str, Any] = {"limit": limit, "depth": depth}
        if filter_query:
            params["filter"] = filter_query
        if search_query:
            params["searchQuery"] = search_query
        if order_by:
            params["orderBy"] = order_by
        data = self._request("GET", f"/rest/{object_name_plural}", params=params)
        return data.get("data", {}).get(object_name_plural, []) if data else []

    def get_record(self, object_name_plural: str, record_id: str, *, depth: int = 0) -> Optional[dict]:
        try:
            data = self._request("GET", f"/rest/{object_name_plural}/{record_id}", params={"depth": depth})
        except TwentyAPIError as exc:
            if exc.status_code == 404:
                return None
            raise
        return data.get("data", {}).get(_singular(object_name_plural)) if data else None

    def create_record(self, object_name_plural: str, fields: dict) -> dict:
        object_name_singular = _singular(object_name_plural)
        data = self._request("POST", f"/rest/{object_name_plural}", json=fields)
        return _unwrap_mutation_payload(data.get("data") or {}, "create", object_name_singular)

    def update_record(self, object_name_plural: str, record_id: str, fields: dict) -> dict:
        object_name_singular = _singular(object_name_plural)
        data = self._request("PATCH", f"/rest/{object_name_plural}/{record_id}", json=fields)
        return _unwrap_mutation_payload(data.get("data") or {}, "update", object_name_singular)

    def create_records_batch(self, object_name_plural: str, records: list[dict]) -> list[dict]:
        """Create up to `settings.max_batch_size` records in one call."""
        if len(records) > self._settings.max_batch_size:
            raise ValueError(
                f"Batch of {len(records)} exceeds Twenty's max batch size of {self._settings.max_batch_size}"
            )
        if not records:
            return []
        data = self._request("POST", f"/rest/batch/{object_name_plural}", json=records)
        return data["data"][object_name_plural]

    # -- domain-specific convenience lookups ------------------------------

    def find_company_by_domain(self, domain: str) -> Optional[dict]:
        matches = self.find_records("companies", filter_query=f"domainName.primaryLinkUrl[ilike]:%{domain}%", limit=1)
        return matches[0] if matches else None

    def find_company_by_name(self, name: str) -> Optional[dict]:
        matches = self.find_records("companies", filter_query=f"name[ilike]:{_escape_filter(name)}", limit=1)
        return matches[0] if matches else None

    def find_person_by_email(self, email: str) -> Optional[dict]:
        matches = self.find_records("people", filter_query=f"emails.primaryEmail[eq]:{_escape_filter(email)}", limit=1)
        return matches[0] if matches else None

    def find_person_by_linkedin(self, linkedin_url: str) -> Optional[dict]:
        matches = self.find_records(
            "people", filter_query=f"linkedinLink.primaryLinkUrl[eq]:{_escape_filter(linkedin_url)}", limit=1
        )
        return matches[0] if matches else None


def _singular(name_plural: str) -> str:
    # Matches Twenty's REST mutation/query payload keys. Irregular plurals
    # must be listed -- naive "strip trailing s" turns companies -> companie.
    irregular = {
        "people": "person",
        "companies": "company",
        "opportunities": "opportunity",
        "researchJobs": "researchJob",
        "enrichmentJobs": "enrichmentJob",
        "icpScores": "icpScore",
        "conversationSignals": "conversationSignal",
        "noteTargets": "noteTarget",
    }
    if name_plural in irregular:
        return irregular[name_plural]
    if name_plural.endswith("ies"):
        return name_plural[:-3] + "y"
    if name_plural.endswith("s"):
        return name_plural[:-1]
    return name_plural


def _mutation_payload_key(action: str, singular: str) -> str:
    # Twenty Core REST returns createCompany / updatePerson / etc.
    return f"{action}{singular[:1].upper()}{singular[1:]}"


def _unwrap_mutation_payload(payload: dict, action: str, singular: str) -> dict:
    for key in (_mutation_payload_key(action, singular), singular):
        if key in payload:
            return payload[key]
    raise KeyError(
        f"Twenty {action} response missing expected keys "
        f"{_mutation_payload_key(action, singular)!r}/{singular!r}; got {list(payload)}"
    )


def _escape_filter(value: str) -> str:
    # Twenty's REST filter grammar uses ":" and "," as separators; a value
    # containing either must be quoted. Kept intentionally conservative.
    if any(c in value for c in [":", ",", "(", ")"]):
        return f'"{value}"'
    return value
