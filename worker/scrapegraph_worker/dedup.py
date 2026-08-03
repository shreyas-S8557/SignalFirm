"""Deterministic, non-AI deduplication helpers.

Deliberately no LLM calls in this module (per this milestone's scope: data
plumbing only, AI comes later). The existing `similarity.py` in the
Scrapegraph repo does LLM-based similarity scoring for a different purpose
(comparing a company against a reference ICP) -- this module solves a
narrower problem: "is this scraped row the same real-world company/person we
already have in Twenty?" using normalization + exact/fuzzy string matching,
which is enough for the CRM-population step and keeps this layer fast and
free to run on every row.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|llc|llp|pllc|pc|co|corp|corporation|company|ltd|group|partners?|"
    r"associates?|cpas?|firm|and)\b\.?",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Below this, two names are not considered a match at all.
NAME_SIMILARITY_THRESHOLD = 0.88


def normalize_domain(url_or_domain: str) -> str:
    """"https://www.Acme-CPA.com/about" -> "acme-cpa.com" """
    value = (url_or_domain or "").strip().lower()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    host = urlparse(value).netloc or urlparse(value).path
    host = host.split(":")[0]  # strip port
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_company_name(name: str) -> str:
    """Lowercase, strip legal suffixes and punctuation, collapse whitespace.
    Used only for comparison -- never written back as the display name.
    """
    value = (name or "").strip().lower()
    value = _COMPANY_SUFFIXES.sub("", value)
    value = _NON_ALNUM.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_linkedin_url(url: str) -> str:
    value = (url or "").strip().lower()
    value = re.sub(r"^https?://(www\.)?", "", value)
    value = re.sub(r"\?.*$", "", value)  # drop query params (tracking, etc.)
    return value.rstrip("/")


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_company_name(a), normalize_company_name(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def is_likely_same_company(
    *,
    candidate_name: str,
    candidate_domain: str,
    existing_name: str,
    existing_domain: str,
) -> bool:
    """A domain match is decisive (company websites are effectively unique
    identifiers). Absent a domain on either side, fall back to fuzzy name
    matching with a conservative threshold to avoid merging distinct firms
    that happen to share a common word ("Smith & Associates CPAs" x2 in
    different cities, etc.) -- callers should combine this with a location
    check when available; that's a `sync.py` concern, not this module's.
    """
    cd, ed = normalize_domain(candidate_domain), normalize_domain(existing_domain)
    if cd and ed:
        return cd == ed
    return name_similarity(candidate_name, existing_name) >= NAME_SIMILARITY_THRESHOLD


def is_likely_same_person(
    *,
    candidate_email: str,
    candidate_linkedin: str,
    existing_email: str,
    existing_linkedin: str,
) -> bool:
    ce, ee = (candidate_email or "").strip().lower(), (existing_email or "").strip().lower()
    if ce and ee:
        return ce == ee
    cl, el = normalize_linkedin_url(candidate_linkedin), normalize_linkedin_url(existing_linkedin)
    if cl and el:
        return cl == el
    return False


_TITLE_COMPANY_PATTERNS = [
    # "Managing Partner at Smith & Co CPAs" -> "Smith & Co CPAs"
    re.compile(r"\bat\s+(.+)$", re.IGNORECASE),
    # "Partner, Smith & Co CPAs" -> "Smith & Co CPAs"
    re.compile(r",\s*(.+)$"),
]


def derive_company_name_from_title(profile_title: str) -> str:
    """Heuristic-only fallback for rows with no explicit `company_name`
    (the current gap flagged in the architecture analysis, §4.1). Returns ""
    rather than a wrong guess when no pattern matches -- callers must treat
    an empty result as "unknown," not as a real value.
    """
    title = (profile_title or "").strip()
    if not title:
        return ""
    for pattern in _TITLE_COMPANY_PATTERNS:
        match = pattern.search(title)
        if match:
            candidate = match.group(1).strip(" .")
            if len(candidate) >= 3:
                return candidate
    return ""
