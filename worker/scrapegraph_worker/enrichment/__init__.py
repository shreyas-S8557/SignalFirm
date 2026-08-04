"""Phase 4: Company Enrichment.

Given a Company already in Twenty (created by the sync pipeline in
`scrapegraph_worker.sync`), this package fills in the gap between "we have a
name and a domain" and "we understand this company enough to prioritize and
personalize outreach to it":

  website_crawler.py    -- fetches the company's own public site (a handful
                            of likely pages: home, about, careers, blog/news)
  tech_stack.py          -- signature-based detection of technologies in use,
                            from the HTML/headers the crawler already fetched
  signals.py              -- hiring signals, buying signals, growth
                            indicators, and a LinkedIn-*derived* headcount/
                            seniority proxy computed from People records this
                            workspace already has (not a live LinkedIn fetch)
  llm_synthesis.py        -- turns crawled text + signals into a short
                            company summary and an AI-maturity read, via the
                            same OpenAI-compatible LLM backend Conversation
                            Intelligence uses; degrades to a heuristic
                            summary if no LLM is configured
  engine.py                -- orchestrates the above into one EnrichmentJob
                            record per run, written to Twenty

Deliberate scope boundary: no paid data provider (Clearbit, Apollo, People
Data Labs, etc.) is used or assumed. Every signal here is derived from (a)
the company's own public website, fetched directly, or (b) data this
workspace already legitimately has via the existing scrape/sync pipeline.
LinkedIn's own pages are never scraped directly -- see
`signals.py`'s module docstring for why, and what's used instead.
"""
