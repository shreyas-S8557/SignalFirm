"""Fetches a company's own public website -- the one data source every
company in the CRM has, regardless of whether any paid enrichment provider
is configured.

Deliberately narrow: a handful of well-known paths off the homepage, not a
general-purpose crawler that follows arbitrary links. That keeps this fast,
predictable, and low-risk to run automatically on every company rather than
something that needs a crawl budget or depth limit tuned per site.

robots.txt is checked and respected before fetching anything beyond the
robots.txt request itself -- this crawler only ever reads a company's own
public marketing site (the same pages a human visitor or search engine
would see), and respecting robots.txt keeps it that way even though these
are low-traffic informational pages that virtually every site allows.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .models import CrawledPage

logger = logging.getLogger(__name__)

# Relative paths tried off the homepage. Order matters a little (cheaper,
# higher-hit-rate paths first) but every reachable one is fetched -- this
# isn't a "stop at first match" list.
CANDIDATE_PATHS = [
    "/",
    "/about",
    "/about-us",
    "/company",
    "/careers",
    "/jobs",
    "/blog",
    "/news",
]

DEFAULT_USER_AGENT = "OpikaEnrichmentBot/1.0 (+https://github.com/opika/crm-sync; contact via workspace admin)"
MAX_PAGES = 8
MAX_HTML_BYTES = 1_500_000  # guard against being handed a huge non-HTML response


class CrawlBlockedByRobots(RuntimeError):
    pass


def _robots_allows(base_url: str, path: str, client: httpx.Client, user_agent: str) -> bool:
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    try:
        response = client.get(robots_url, timeout=10)
        if response.status_code >= 400:
            # No robots.txt (or it errors) -- conventionally treated as
            # "no restrictions stated", same as most crawlers do.
            return True
        parser.parse(response.text.splitlines())
    except httpx.HTTPError:
        # Can't reach robots.txt -- fail open for a marketing-site GET the
        # same way a browser would, rather than blocking the whole crawl on
        # a transient robots.txt fetch failure.
        return True
    return parser.can_fetch(user_agent, urljoin(base_url, path))


def crawl_company_site(
    domain: str,
    *,
    timeout_seconds: float = 10.0,
    user_agent: str = DEFAULT_USER_AGENT,
    max_pages: int = MAX_PAGES,
    http_client: Optional[httpx.Client] = None,
) -> list[CrawledPage]:
    """Fetches CANDIDATE_PATHS (up to `max_pages`) off `domain`. Tries https
    first, falls back to http on connection failure. Never raises for a
    single page's fetch failure -- that page's CrawledPage just carries
    `fetch_error` and everything downstream (tech_stack, signals, LLM
    synthesis) treats a partial page set as normal, expected input, not an
    exceptional case.
    """
    if not domain:
        return []

    base_url = f"https://{domain}"
    owns_client = http_client is None
    client = http_client or httpx.Client(
        follow_redirects=True,
        headers={"User-Agent": user_agent},
        timeout=timeout_seconds,
    )

    pages: list[CrawledPage] = []
    try:
        # Confirm https resolves at all; fall back to http for the whole
        # crawl if not, rather than mixing schemes page-to-page.
        scheme_base = base_url
        try:
            probe = client.get(base_url, timeout=timeout_seconds)
            if probe.status_code >= 400 and probe.status_code != 404:
                # A non-404 error on the homepage itself (e.g. 495 TLS
                # error via some CDNs) is a signal https may not be served;
                # try http as a fallback base.
                scheme_base = f"http://{domain}"
        except httpx.HTTPError:
            scheme_base = f"http://{domain}"

        for path in CANDIDATE_PATHS[:max_pages]:
            url = urljoin(scheme_base, path)
            try:
                if not _robots_allows(scheme_base, path, client, user_agent):
                    pages.append(CrawledPage(url=url, fetch_error="disallowed by robots.txt"))
                    continue
                response = client.get(url, timeout=timeout_seconds)
                content = response.content[:MAX_HTML_BYTES]
                html = content.decode(response.encoding or "utf-8", errors="ignore")
                text = _extract_text(html) if response.status_code < 400 else ""
                pages.append(
                    CrawledPage(url=str(response.url), status_code=response.status_code, html=html, text=text)
                )
            except httpx.HTTPError as exc:
                logger.info("Enrichment crawl: %s failed: %s", url, exc)
                pages.append(CrawledPage(url=url, fetch_error=str(exc)))
    finally:
        if owns_client:
            client.close()

    return pages


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    # Collapse whitespace; crawled marketing HTML is often heavily nested
    # and get_text() leaves long runs of spaces from layout whitespace.
    return " ".join(text.split())
