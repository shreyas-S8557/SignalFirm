"""Hiring signals, buying signals, growth indicators, and a LinkedIn-
*derived* headcount/seniority proxy.

A note on LinkedIn specifically, since "LinkedIn enrichment" was requested
for this milestone: LinkedIn's Terms of Service prohibit automated scraping
of linkedin.com (this is also the subject of ongoing litigation and
technical countermeasures on their side), so this pipeline never fetches
linkedin.com pages directly -- no headless browser hitting profile pages,
no scraping company pages for headcount. What it does instead is compute
signals from data this workspace *already has*: every synced Person record
carries a `linkedinUrl` captured by the existing Scrapegraph collection
step (a public-search-based pipeline, not a linkedin.com scrape -- see
scrape_adapter.py) at import time. This module aggregates that
already-collected data per company (headcount proxy, seniority mix from job
titles) rather than re-fetching anything from LinkedIn itself. If true
LinkedIn firmographic data (real headcount, company page followers, etc.)
is needed later, that requires LinkedIn's own official APIs under a
partnership agreement -- a provider integration, not a scraper, and it
would slot into this same module as a new provider once available.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from ..twenty_client import TwentyClient
from .models import BuyingSignalHit, CrawledPage, GrowthIndicators, HiringSignal, LinkedInDerivedSignals

# Department keyword buckets for hiring-signal grouping. Intentionally
# coarse (a handful of buckets, not a job-title taxonomy) -- this is a
# signal for "are they hiring, and roughly where", not a precise org chart.
_DEPARTMENT_KEYWORDS: dict[str, list[str]] = {
    "Engineering": ["engineer", "developer", "swe", "software", "devops", "sre", "backend", "frontend", "full stack"],
    "Sales": ["sales", "account executive", "sdr", "bdr", "business development"],
    "Marketing": ["marketing", "growth", "brand", "content", "demand gen"],
    "Product": ["product manager", "product designer", "ux", "ui designer"],
    "AI/ML": ["machine learning", "ml engineer", "ai engineer", "data scientist", "applied scientist", "llm"],
    "Customer Success": ["customer success", "support specialist", "account manager"],
    "Operations": ["operations", "finance", "hr ", "people ops", "recruiter", "recruiting"],
}

_HIRING_PAGE_HINTS = re.compile(r"careers|jobs|join.?us|we.?re hiring|open positions|open roles", re.I)

# Buying-signal keywords: phrases that plausibly indicate active change --
# funding, leadership change, expansion, or an active vendor search. Each
# hit is reported with its exact surrounding excerpt, never paraphrased or
# inferred into a bigger claim.
_BUYING_SIGNAL_KEYWORDS = [
    "raised a", "series a", "series b", "series c", "seed round", "funding round",
    "new office", "opening an office", "expanding into", "expansion",
    "new ceo", "new cto", "new vp", "appoints", "welcomes", "joins as",
    "acquisition", "acquired", "merger", "partnership with",
    "request a demo", "request a quote", "rfp", "looking for a partner",
    "now hiring", "we're growing", "record growth", "record quarter",
]

_EXCERPT_RADIUS = 80


def detect_hiring_signals(pages: list[CrawledPage]) -> list[HiringSignal]:
    """Scans crawled career/jobs pages (and any page that mentions hiring)
    for department-keyword mention counts. Not a real ATS integration --
    just what's visible in the page text a human visitor would also see.
    """
    signals: list[HiringSignal] = []
    for page in pages:
        if not page.ok or not page.text:
            continue
        is_hiring_page = bool(_HIRING_PAGE_HINTS.search(page.url)) or bool(_HIRING_PAGE_HINTS.search(page.text[:500]))
        if not is_hiring_page:
            continue

        lowered = page.text.lower()
        for department, keywords in _DEPARTMENT_KEYWORDS.items():
            count = sum(lowered.count(kw) for kw in keywords)
            if count > 0:
                signals.append(HiringSignal(department=department, mention_count=count, source_url=page.url))

    return signals


def detect_buying_signals(pages: list[CrawledPage]) -> list[BuyingSignalHit]:
    hits: list[BuyingSignalHit] = []
    for page in pages:
        if not page.ok or not page.text:
            continue
        lowered = page.text.lower()
        for keyword in _BUYING_SIGNAL_KEYWORDS:
            idx = lowered.find(keyword)
            if idx == -1:
                continue
            start = max(0, idx - _EXCERPT_RADIUS)
            end = min(len(page.text), idx + len(keyword) + _EXCERPT_RADIUS)
            excerpt = page.text[start:end].strip()
            hits.append(BuyingSignalHit(keyword=keyword, excerpt=excerpt, source_url=page.url))

    return hits


_SENIOR_TITLE_KEYWORDS = {
    "C-Level": ["chief", "ceo", "cto", "cfo", "coo", "cmo", "cro"],
    "VP": ["vp ", "vice president"],
    "Director": ["director"],
    "Manager": ["manager", "head of"],
    "Individual Contributor": [],  # fallback bucket, filled in below
}


def _bucket_seniority(job_title: str) -> str:
    lowered = (job_title or "").lower()
    for bucket, keywords in _SENIOR_TITLE_KEYWORDS.items():
        if bucket == "Individual Contributor":
            continue
        if any(kw in lowered for kw in keywords):
            return bucket
    return "Individual Contributor"


def compute_linkedin_derived_signals(client: TwentyClient, company_id: str) -> LinkedInDerivedSignals:
    """Aggregates People already synced for this company. See module
    docstring for why this reads already-synced data rather than fetching
    linkedin.com.
    """
    people = client.find_records("people", filter_query=f"company.id[eq]:{company_id}", limit=200, depth=0)

    with_linkedin = 0
    seniority_counter: Counter[str] = Counter()
    title_counter: Counter[str] = Counter()

    for person in people:
        linkedin_link = (person.get("linkedinLink") or {}).get("primaryLinkUrl")
        if linkedin_link:
            with_linkedin += 1
        job_title = person.get("jobTitle")
        if job_title:
            seniority_counter[_bucket_seniority(job_title)] += 1
            title_counter[job_title] += 1

    return LinkedInDerivedSignals(
        people_with_linkedin_url=with_linkedin,
        seniority_mix=dict(seniority_counter),
        top_job_titles=[title for title, _ in title_counter.most_common(5)],
    )


def compute_growth_indicators(
    client: TwentyClient, company_id: str, hiring_signals: list[HiringSignal]
) -> GrowthIndicators:
    people_count = len(client.find_records("people", filter_query=f"company.id[eq]:{company_id}", limit=200, depth=0))
    open_role_mentions = sum(s.mention_count for s in hiring_signals)

    notes: list[str] = []
    if people_count == 0:
        notes.append("No People records synced yet for this company -- headcount proxy unavailable.")
    if open_role_mentions == 0:
        notes.append("No hiring-page mentions detected -- either not actively hiring, or no careers page was reachable.")

    return GrowthIndicators(
        synced_people_count=people_count,
        open_role_mentions=open_role_mentions,
        notes=notes,
    )


def resolve_company_domain(client: TwentyClient, company_id: str) -> Optional[str]:
    """Small helper so engine.py doesn't need to know Twenty's
    domainName field shape directly.
    """
    company = client.get_record("companies", company_id, depth=0)
    if not company:
        return None
    link = (company.get("domainName") or {}).get("primaryLinkUrl") or ""
    if not link:
        return None
    # domainName is stored as a full URL (see sync.py::_upsert_company);
    # strip scheme/path down to a bare host for the crawler.
    return link.split("://", 1)[-1].split("/", 1)[0]
