"""Optional paid firmographic-data providers for Company Enrichment.

This package answers the gap the root README's "What's NOT connected to
anything yet" section used to call out honestly: enrichment's tech-stack/
hiring/buying signals are keyword-and-proxy-based by design (see
`enrichment/signals.py`), not sourced from a real data vendor. This package
adds that as an *optional* supplementary layer -- if you configure an API
key for one of these, `enrichment/engine.py` calls it after the website
crawl and folds real employee-count/industry/revenue/tech-stack data into
the same `EnrichmentResult` the crawl produces. With no key configured,
behavior is byte-for-byte identical to before this package existed.

Deliberately NOT included: Clearbit. HubSpot acquired it in December 2023
and folded it into "Breeze Intelligence" -- a HubSpot-only, credit-based
feature. Standalone API access was cut off for new (non-HubSpot) customers
during 2025, so there is no self-serve key a deployer of this codebase
could obtain to use it, the way there is for Apollo and PDL. Wiring in a
provider nobody can actually sign up to use would be dead code with a
misleading README entry, not a real integration.

Two adapters, same shape as `outbound/send/`'s adapters: one interface
(`base.DataProvider`), one concrete implementation per vendor, never
raising -- a provider outage or an unrecognized response shape degrades to
"no supplementary data," never a failed enrichment run (the crawl-based
result stands on its own either way).
"""
