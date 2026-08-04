"""Signature-based technology detection, in the spirit of Wappalyzer --
looks for known script sources, meta tags, and HTML markers in already-
crawled pages. No network calls here; this only ever looks at
`CrawledPage.html` the crawler already fetched.

Deliberately a small, named, auditable signature list rather than a
generic "any third-party script domain" scanner -- every hit in
`tech_stack_hits` can be explained by pointing at exactly which signature
matched (`TechStackHit.matched_on`), which matters because this ends up
attributed to a real company record in the CRM.
"""

from __future__ import annotations

import re

from .models import CrawledPage, TechStackHit

# (display name, category, compiled pattern to search for in raw HTML)
# Patterns are intentionally simple substring/regex checks against script
# src, link href, meta tags, or inline markers -- not full DOM parsing --
# since that's what nearly every real signature-detection tool actually
# keys off of.
_SIGNATURES: list[tuple[str, str, re.Pattern]] = [
    # CMS / site builders
    ("WordPress", "CMS", re.compile(r"wp-content|wp-includes|/wp-json/", re.I)),
    ("Webflow", "CMS", re.compile(r"webflow\.com|data-wf-site", re.I)),
    ("Squarespace", "CMS", re.compile(r"squarespace\.com|static1\.squarespace\.com", re.I)),
    ("Wix", "CMS", re.compile(r"wix\.com|wixstatic\.com", re.I)),
    ("Shopify", "Ecommerce", re.compile(r"cdn\.shopify\.com|Shopify\.theme", re.I)),
    ("Drupal", "CMS", re.compile(r"Drupal\.settings|/sites/default/files", re.I)),
    # Frameworks
    ("Next.js", "Framework", re.compile(r"/_next/static/|__NEXT_DATA__", re.I)),
    ("React", "Framework", re.compile(r"data-reactroot|react-dom(\.min)?\.js", re.I)),
    ("Gatsby", "Framework", re.compile(r"gatsby-announcer|/page-data/app-data\.json", re.I)),
    ("Vue.js", "Framework", re.compile(r"vue(\.min)?\.js|data-v-app", re.I)),
    # Analytics
    ("Google Analytics", "Analytics", re.compile(r"www\.google-analytics\.com|gtag\(|googletagmanager\.com/gtag", re.I)),
    ("Google Tag Manager", "Analytics", re.compile(r"googletagmanager\.com/gtm\.js", re.I)),
    ("Mixpanel", "Analytics", re.compile(r"cdn\.mxpnl\.com|mixpanel\.init", re.I)),
    ("Amplitude", "Analytics", re.compile(r"cdn\.amplitude\.com", re.I)),
    ("Segment", "Analytics", re.compile(r"cdn\.segment\.com/analytics\.js", re.I)),
    ("Hotjar", "Analytics", re.compile(r"static\.hotjar\.com", re.I)),
    ("Plausible", "Analytics", re.compile(r"plausible\.io/js", re.I)),
    # Marketing / CRM
    ("HubSpot", "Marketing", re.compile(r"js\.hs-scripts\.com|js\.hubspot\.com|hs-analytics", re.I)),
    ("Marketo", "Marketing", re.compile(r"munchkin\.marketo\.net", re.I)),
    ("Mailchimp", "Marketing", re.compile(r"chimpstatic\.com|list-manage\.com", re.I)),
    ("Salesforce", "CRM", re.compile(r"force\.com|salesforce-communities\.com", re.I)),
    ("Pardot", "Marketing", re.compile(r"pi\.pardot\.com", re.I)),
    ("Klaviyo", "Marketing", re.compile(r"static\.klaviyo\.com", re.I)),
    # Support / chat
    ("Intercom", "Support", re.compile(r"widget\.intercom\.io|intercomcdn\.com", re.I)),
    ("Drift", "Support", re.compile(r"js\.driftt\.com", re.I)),
    ("Zendesk", "Support", re.compile(r"static\.zdassets\.com|zendesk\.com/embeddable", re.I)),
    ("Crisp", "Support", re.compile(r"client\.crisp\.chat", re.I)),
    ("Front", "Support", re.compile(r"chat-assets\.frontapp\.com", re.I)),
    # Payments
    ("Stripe", "Payments", re.compile(r"js\.stripe\.com", re.I)),
    ("PayPal", "Payments", re.compile(r"paypal\.com/sdk/js", re.I)),
    ("Recurly", "Payments", re.compile(r"js\.recurly\.com", re.I)),
    # Infra / CDN (weaker signal, still worth surfacing)
    ("Cloudflare", "Infrastructure", re.compile(r"cdnjs\.cloudflare\.com|__cf_bm", re.I)),
    ("Fastly", "Infrastructure", re.compile(r"fastly\.net", re.I)),
    ("Vercel", "Infrastructure", re.compile(r"vercel\.app|x-vercel-id", re.I)),
    ("Netlify", "Infrastructure", re.compile(r"netlify\.app|__netlify", re.I)),
    # Recruiting (relevant to hiring-signal cross-checks)
    ("Greenhouse", "Recruiting", re.compile(r"boards\.greenhouse\.io|greenhouse\.io/embed", re.I)),
    ("Lever", "Recruiting", re.compile(r"jobs\.lever\.co", re.I)),
    ("Workable", "Recruiting", re.compile(r"apply\.workable\.com", re.I)),
    ("Ashby", "Recruiting", re.compile(r"jobs\.ashbyhq\.com", re.I)),
    # A/B testing
    ("Optimizely", "Experimentation", re.compile(r"cdn\.optimizely\.com", re.I)),
    ("LaunchDarkly", "Experimentation", re.compile(r"app\.launchdarkly\.com", re.I)),
]

_META_GENERATOR = re.compile(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']', re.I)


def detect_tech_stack(pages: list[CrawledPage]) -> list[TechStackHit]:
    """Scans every crawled page's raw HTML and returns de-duplicated hits.
    Same technology matched across multiple pages is reported once, on the
    first page it was found on.
    """
    seen: dict[str, TechStackHit] = {}

    for page in pages:
        if not page.ok or not page.html:
            continue

        generator_match = _META_GENERATOR.search(page.html)
        if generator_match:
            generator = generator_match.group(1).strip()
            if generator and generator not in seen:
                seen[f"meta:{generator}"] = TechStackHit(
                    name=generator,
                    category="CMS",
                    matched_on=f"<meta name=generator> on {page.url}",
                )

        for name, category, pattern in _SIGNATURES:
            if name in {h.name for h in seen.values()}:
                continue
            match = pattern.search(page.html)
            if match:
                seen[name] = TechStackHit(
                    name=name,
                    category=category,
                    matched_on=f"matched {match.group(0)[:60]!r} on {page.url}",
                )

    return list(seen.values())
