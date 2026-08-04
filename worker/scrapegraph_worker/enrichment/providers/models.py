from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ProviderCompanyProfile(BaseModel):
    """Normalized shape every provider adapter returns, regardless of each
    vendor's own field names -- `enrichment/engine.py` only ever reads this
    shape, never a provider's raw response, so adding a third provider
    later doesn't touch the engine.
    """

    source: str  # "apollo" | "people_data_labs"
    employee_count: Optional[int] = None
    industry: Optional[str] = None
    estimated_annual_revenue: Optional[str] = None
    founded_year: Optional[int] = None
    technologies: list[str] = Field(default_factory=list)
    linkedin_url: Optional[str] = None
    short_description: Optional[str] = None
    raw: dict = Field(default_factory=dict)  # the untouched provider response, for debugging a bad match
