"""Scrapegraph background worker/service: turns the existing CPA-firm scrape
pipeline into a queued job with progress tracking, and syncs its output into
Twenty CRM as Companies, Contacts, Opportunities (Leads), and Notes
(Activities), with deduplication. No AI/LLM logic lives in this package --
see the architecture-analysis document for where that comes in later.
"""
