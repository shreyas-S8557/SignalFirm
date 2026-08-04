"""Adapter for Apollo.io's Organization Enrichment API.

    GET https://api.apollo.io/api/v1/organizations/enrich?domain=<domain>
    Header: X-Api-Key: <your Apollo API key>

Requires your own Apollo account and API key (a free tier exists; paid
tiers unlock higher volume) -- get one at https://app.apollo.io under
Settings -> API. Apollo's response schema can shift slightly between plans
and API versions, so every field below is read with `.get()` and a
provider-side rename just means that one field comes back `None`, not a
crash -- verify against a live response from your own account if a field
you expect isn't showing up in `ProviderCompanyProfile`.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .base import DataProvider
from .models import ProviderCompanyProfile

logger = logging.getLogger(__name__)

_ENRICH_URL = "https://api.apollo.io/api/v1/organizations/enrich"


class ApolloProvider(DataProvider):
    name = "apollo"

    def __init__(self, api_key: str, *, timeout_seconds: float = 15.0, http_client: Optional[httpx.Client] = None):
        self._api_key = api_key
        self._http = http_client or httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self._http.close()

    def lookup_company(self, domain: str) -> Optional[ProviderCompanyProfile]:
        try:
            response = self._http.get(
                _ENRICH_URL,
                params={"domain": domain},
                headers={"X-Api-Key": self._api_key, "Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            logger.warning("Apollo enrichment request failed for %s: %s", domain, exc)
            return None

        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            logger.warning("Apollo enrichment returned %s for %s: %s", response.status_code, domain, response.text[:300])
            return None

        try:
            payload = response.json()
        except ValueError:
            logger.warning("Apollo enrichment returned non-JSON for %s", domain)
            return None

        org = payload.get("organization") or {}
        if not org:
            return None

        technologies = org.get("technology_names") or org.get("technologies") or []
        technologies = [t if isinstance(t, str) else t.get("name") for t in technologies]

        return ProviderCompanyProfile(
            source=self.name,
            employee_count=org.get("estimated_num_employees"),
            industry=org.get("industry"),
            estimated_annual_revenue=_format_revenue(org.get("annual_revenue")),
            founded_year=org.get("founded_year"),
            technologies=[t for t in technologies if t],
            linkedin_url=org.get("linkedin_url"),
            short_description=org.get("short_description"),
            raw=org,
        )


def _format_revenue(value) -> Optional[str]:
    if value is None:
        return None
    try:
        return f"${int(value):,}"
    except (TypeError, ValueError):
        return str(value)
