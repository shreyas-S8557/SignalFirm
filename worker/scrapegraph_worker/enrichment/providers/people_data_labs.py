"""Adapter for People Data Labs' Company Enrichment API.

    GET https://api.peopledatalabs.com/v5/company/enrich?website=<domain>
    Header: X-Api-Key: <your PDL API key>

Requires your own PDL account and API key (self-signup dashboard; free
tier available, rate-limited) -- see https://www.peopledatalabs.com. As
with the Apollo adapter, every field is read with `.get()` so an
unexpected response shape degrades to a thinner profile, never a crash.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .base import DataProvider
from .models import ProviderCompanyProfile

logger = logging.getLogger(__name__)

_ENRICH_URL = "https://api.peopledatalabs.com/v5/company/enrich"


class PeopleDataLabsProvider(DataProvider):
    name = "people_data_labs"

    def __init__(self, api_key: str, *, timeout_seconds: float = 15.0, http_client: Optional[httpx.Client] = None):
        self._api_key = api_key
        self._http = http_client or httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self._http.close()

    def lookup_company(self, domain: str) -> Optional[ProviderCompanyProfile]:
        try:
            response = self._http.get(
                _ENRICH_URL,
                params={"website": domain},
                headers={"X-Api-Key": self._api_key, "accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            logger.warning("PDL enrichment request failed for %s: %s", domain, exc)
            return None

        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            logger.warning("PDL enrichment returned %s for %s: %s", response.status_code, domain, response.text[:300])
            return None

        try:
            data = response.json()
        except ValueError:
            logger.warning("PDL enrichment returned non-JSON for %s", domain)
            return None

        if not data or data.get("status") not in (200, None):
            return None

        tags = data.get("tags") or []  # PDL's free-text company tags -- an imperfect tech-stack proxy, included anyway
        revenue = data.get("inferred_revenue")

        return ProviderCompanyProfile(
            source=self.name,
            employee_count=data.get("employee_count"),
            industry=data.get("industry"),
            estimated_annual_revenue=str(revenue) if revenue is not None else None,
            founded_year=data.get("founded"),
            technologies=[t for t in tags if isinstance(t, str)][:20],
            linkedin_url=data.get("linkedin_url"),
            short_description=data.get("summary"),
            raw=data,
        )
