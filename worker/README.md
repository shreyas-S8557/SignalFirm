# Scrapegraph Worker — background service for CRM population

Turns your existing Scrapegraph CLI pipeline into a queued background job and
syncs its output into Twenty CRM as Companies, Contacts, Opportunities
("Leads"), and Notes ("Activities"), with deduplication. It also hosts
Conversation Intelligence (LLM-based reply analysis, see the top-level
README) and the Recommendation Engine (the every-morning digest built on top
of it, see below) — the only two places LLM/derived-scoring logic lives in
this repo.

## How a scraped row becomes CRM records

| Scrapegraph concept | Twenty object | Notes |
|---|---|---|
| CPA firm | `Company` | matched by domain (decisive) or fuzzy name (fallback) before creating a new one |
| Decision maker | `Person` | matched by email or LinkedIn URL |
| "this is a new prospect" | `Opportunity` | created **once**, the first time a Company is seen — re-syncing doesn't open duplicate pipeline entries |
| Import event | `Note` | attached to the Company (and Person, if present) via `noteTargets`; shows up in Twenty's timeline automatically |
| Sync attempt (audit trail) | `ResearchJob` (custom object) | see `../twenty-app/` — degrades gracefully (logs a warning, doesn't fail the sync) if that app isn't installed yet |

Twenty has no separate "Lead" object — `Opportunity` is used as the lead/prospect record, consistent with how Twenty's own pipeline concept works.

Company Enrichment (tech stack, hiring/buying signals, AI-maturity read) runs as a separate step *after* a Company exists — see "Company Enrichment" below — not as part of the scrape/sync flow above.

## Architecture

```
FastAPI (api.py)  ---enqueue--->  Redis (RQ queue)  ---pulls--->  Worker (worker_main.py)
     |                                                                    |
GET /jobs/{id}  <---------------  SQLite job store  <----progress--------+
                                        |                                |
                                        +--optional webhook push-------> Twenty ResearchJob
                                                                          (../twenty-app/)
                                                                                |
                                                                  Worker also syncs directly
                                                                  into Twenty via REST Core API
                                                                  (twenty_client.py)
```

The scrape itself runs as a **subprocess** (`scrape_adapter.py`), not an in-process import — `scrapegraphai` drives a real Playwright browser with its own asyncio loop, so isolating it protects the API/worker process from a stuck browser or crash.

## Setup

```bash
cp .env.example .env
# fill in TWENTY_BASE_URL, TWENTY_API_KEY (Settings -> APIs & Webhooks in Twenty)
docker compose up --build
```

Or without Docker:

```bash
pip install -r requirements.txt --break-system-packages
uvicorn scrapegraph_worker.api:app --reload &
python -m scrapegraph_worker.worker_main &
```

## Usage

```bash
# Start a scrape+sync job
curl -X POST localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/scrapegraph", "target": 100}'
# => {"job_id": "..."}

# Check progress
curl localhost:8000/jobs/<job_id>
# => {"stage": "SYNCING", "processed_rows": 40, "total_rows": 100,
#     "created_count": 12, "updated_count": 5, "duplicate_count": 23,
#     "error_count": 0, "progress_pct": 40.0, ...}

# List recent jobs
curl localhost:8000/jobs

# Retry a failed job
curl -X POST localhost:8000/jobs/<job_id>/retry
```

## Workflow Automation — one observable pipeline, no fake stages

Given the full target pipeline (Scrape → Import → Enrichment → Research →
ICP Scoring → Generate Outreach → Wait → Analyze Reply → Update CRM →
Recommendations), this milestone wires together every stage that now has a
real engine in this codebase and automates the hand-offs that are
concretely automatable: **Import → Enrichment → Research → ICP Scoring →
Outreach Drafting**. It does **not** fabricate progress past drafting —
*sending* outreach is a deliberate human step for every channel except
opt-in email (see "AI Outbound Messaging" below), so a company with drafts
ready sits at an honest `OUTREACH_DRAFTED` stage with a `blockedReason`
saying exactly that, rather than silently pretending to have contacted
anyone.

**Deliberate design choice: no new custom object for most of this.** Every
stage already writes an append-only audit record with a Company/Person
relation (`EnrichmentJob`, `ResearchJob`, `ICPScore`, `ConversationSignal`)
— rather than adding a mutable `WorkflowRun` record that could drift out of
sync with those, a company's current stage is *derived on read* from the
records that already exist (`workflow/derive.py`). Outreach drafts are the
one exception worth calling out: they're stored as a `Note` (see "AI
Outbound Messaging" below) rather than a new custom object, for the same
"ship without a schema migration" reasoning.

```bash
# Where is this company in the pipeline, and why (read-only)?
curl localhost:8000/companies/COMPANY_ID/workflow

# Execute the single next automatable action (idempotent -- safe to call
# repeatedly; a company past the automatable part of the pipeline reports
# a documented no-op rather than erroring)
curl -X POST localhost:8000/companies/COMPANY_ID/workflow/advance
```

Stages (`workflow/models.py::WorkflowStage`):

| Stage | Meaning |
|---|---|
| `IMPORTED` | Company exists, no `EnrichmentJob` yet — next action: enrich |
| `FAILED` | Most recent `EnrichmentJob` failed — next action: retry (same as first attempt) |
| `ENRICHED` | Enriched, no research run yet — next action: run the research pass |
| `RESEARCH_FAILED` | Most recent research run failed — next action: retry |
| `PENDING_ICP_SCORE` | Researched, no `ICPScore` yet — next action: run ICP Scoring |
| `ICP_SCORING_FAILED` | Most recent ICP scoring run failed — next action: retry |
| `PENDING_OUTREACH_DRAFT` | ICP-scored, no outreach draft yet — next action: draft outreach messaging |
| `OUTREACH_DRAFT_FAILED` | Most recent outreach-drafting run failed — next action: retry |
| `OUTREACH_DRAFTED` | Drafts exist as Notes on the Company/Person — next action is a human one: review and send |
| `RECOMMENDATIONS_ACTIVE` | At least one Person at this company has a `ConversationSignal` — already covered by the existing Recommendation Engine digest, nothing left for the workflow engine to do |

`POST /companies/{id}/workflow/advance` executes exactly one step; `POST /companies/{id}/workflow/advance-all` runs the chain to completion (up to 6 steps) and returns every step taken, in order.

To close the Scrape → Import → Enrichment loop automatically (rather than
requiring a human, or the enrichment scheduler, to trigger it separately),
set `AUTO_ENRICH_ON_IMPORT=true` — every newly-created Company from a
scrape/import job is enriched immediately, in the same job, tolerant of
per-company failure the same way the sync loop itself is. Off by default
for the same "unattended crawl is a bigger footprint than this service's
other defaults" reason `ENRICHMENT_SCHEDULE_ENABLED` is.

**What happens after a reply today already works without this milestone
doing anything new:** `reply-intelligence-trigger.ts` →
`/conversation/analyze` → `conversation-signal-webhook.ts` →
`ConversationSignal` → the Recommendation Engine's daily digest is a loop
that existed before Phase 7 and needed no orchestration layer added on top
— `derive_workflow_state` just *reports* that a company has reached that
point, it doesn't drive it.

## ICP Scoring — deterministic fit score against a configurable rubric

`icp/` scores a company 0-100 against `data/icp_rubric.yaml` (industry fit,
company-size proxy, buying/hiring-signal strength, tech-stack fit, AI
maturity, and how much the Research pass produced) and writes an `ICPScore`
record plus `Company.latestIcpScore`/`latestIcpPriority`. Deliberately
**not** LLM-based — see `icp/rubric.py`'s module docstring for why an ICP
fit score is arithmetic against a rubric the business defines, not
something to ask a model to guess at.

```bash
# Score one company now (deterministic, no LLM call, fast)
curl -X POST localhost:8000/companies/COMPANY_ID/icp-score
```

Tune `data/icp_rubric.yaml` to your actual ICP — target/disqualifying
industries, complementary/competitor tech, size sweet spot, priority
thresholds. Bump its `version` field whenever you change the weights in a
way that makes old scores not comparable to new ones; every `ICPScore`
record carries the `rubricVersion` it was scored against.

## AI Outbound Messaging — LinkedIn, email, call scripts, and a follow-up sequence, all drafted, none sent without you

`outbound/` generates a full first-touch outreach set for a company's
top contact once it's ICP-scored: a LinkedIn connection note, a LinkedIn
DM, two A/B cold-email variants, a meeting-request email, a call script
(opening / discovery questions / pitch / objection handling / close), and
a 4-6 step follow-up sequence spanning ~2-3 weeks. Every message is
grounded in the Research pass's pain-point/sales-angle *hypotheses* and
the ICP score's reasoning — the prompt is explicit that those are
inferences, not facts to assert to the prospect (`outbound/prompts.py`).

```bash
# Draft outreach for one company's top contact now
curl -X POST localhost:8000/companies/COMPANY_ID/outreach/draft
```

The draft is saved as a `Note` on the Company (and Person, if one was
found) — titled `AI Outreach Draft - <company>` — rather than a new Twenty
custom object, so it shows up directly in Twenty's own record timeline
with zero schema migration required.

**What actually gets sent, and by what:**

| Channel | Automated? |
|---|---|
| Email (cold email, meeting request) | Opt-in via `OUTBOUND_AUTO_SEND_EMAIL=true` (off by default), sent through `OUTBOUND_SMTP_*`. `OUTBOUND_DRY_RUN=true` (the default) logs instead of sending even when enabled. |
| LinkedIn (connection note, DM) | **Never automated.** Scripting LinkedIn actions violates their Terms of Service and risks the account being restricted, and LinkedIn's official Messaging APIs are partner-gated — there's no compliant "just call an API" path for a self-hosted worker like this one. `outbound/send/linkedin_adapter.py` always reports the message as ready for manual send. |
| Call script | Inherently manual — it's a script for a human to use on a call. |

The generated follow-up sequence is scheduled per-person in a small SQLite
table (`outbound/sequence.py`) the moment a draft is written. Run
`python -m scrapegraph_worker.outbound_scheduler_main` to sweep for due
steps daily — it sends the due EMAIL steps for real only if
`OUTBOUND_AUTO_SEND_EMAIL` is on, and always leaves LinkedIn/call steps for
a human, same as the draft itself.

## Research Automation — company summary, pain-point and sales-angle hypotheses



Takes what enrichment observed and turns it into the read a rep needs before first contact. One `ResearchJob` record per run (status `RESEARCHED` / `RESEARCH_FAILED`), appended to the same timeline as the import records — as the object's original scaffold planned, rather than a parallel object.

```bash
# Run the research pass for one company (synchronous)
curl -X POST localhost:8000/companies/COMPANY_ID/research

# Or let the workflow engine sequence enrichment -> research for you
curl -X POST localhost:8000/companies/COMPANY_ID/workflow/advance-all
```

| Output | What it is |
|---|---|
| `researchSummary` | Grounded restatement of what the company does — no new facts |
| `painPoints` | **Hypotheses.** Problems the company *may* have, each citing what it was inferred from |
| `salesAngles` | **Hypotheses.** Conversation openers, each tied to a pain point |
| `researchBuyingSignals` | The LLM's *interpretation* of buying-signal excerpts Phase 4 already found by keyword match |
| `grounding` | Which EnrichmentJob and source URLs the run was based on |
| `researchConfidence` | Computed deterministically from how much grounding material the run had |

**The design constraint that shaped this whole module.** Enrichment deals in observations ("this string appeared on this page"); research necessarily deals in inference — and inference about a company you've never spoken to is exactly where an LLM will produce a confident, specific, plausible falsehood. Here that falsehood would sit on a real company's CRM record and be read by a rep about to contact them. So:

- **No enrichment, no research.** A company with no successful `EnrichmentJob` returns `RESEARCH_FAILED` rather than letting the model free-associate from a company name.
- **No LLM, no research.** Unlike enrichment (which has a real heuristic fallback), there's no non-LLM way to produce a pain-point hypothesis worth anything, so this fails loudly instead of emitting keyword-template filler dressed up as analysis.
- **Uncited claims are dropped, not stored.** `research/agent.py::normalize_result` discards any pain point or sales angle whose `derived_from` is missing or a placeholder — an uncited hypothesis is indistinguishable from a fabrication.
- **The model interprets quotes, it doesn't supply them.** Interpreted buying signals whose excerpt/URL doesn't match one actually present in the enrichment input are dropped, so the model can't invent or silently reword a quote.
- **Confidence is computed, not self-reported.** Deterministic, from how much grounding material existed and how much of the model's output survived normalization — a run whose hypotheses were mostly dropped for missing citations scores *lower*, rather than hiding that.

To run research automatically after a scrape, set both `AUTO_ENRICH_ON_IMPORT=true` and `AUTO_RESEARCH_AFTER_ENRICHMENT=true` (both off by default; research is a separate flag because it costs LLM tokens per company, which enrichment largely doesn't).

## Company Enrichment — website crawl, tech stack, hiring/buying signals, AI-maturity read

Given a Company already synced (see the table above), `POST
/companies/{id}/enrich` crawls that company's own public website (home,
about, careers, blog/news — see `enrichment/website_crawler.py`) and turns
what it finds into:

| Signal | How it's produced |
|---|---|
| Tech stack | Signature matching against crawled HTML (`enrichment/tech_stack.py`) — ~35 known technologies (HubSpot, WordPress, Salesforce, Stripe, Greenhouse, etc.) |
| Hiring signals | Keyword counts by department on the company's own careers/jobs page (`enrichment/signals.py`) |
| Buying signals | Keyword-matched excerpts (funding, expansion, leadership changes, RFPs) — always the exact quote + source URL, never a synthesized claim |
| Growth indicators | Headcount **proxy**: count of this company's already-synced People records, plus open-role mention volume |
| LinkedIn-derived signals | Seniority mix / top job titles computed from already-synced People (see below — **not** a live LinkedIn scrape) |
| Company summary + AI-maturity read | LLM synthesis over crawled text (`enrichment/llm_synthesis.py`), using the same `LLM_*` backend as Conversation Intelligence; falls back to a heuristic title/meta-description summary if no LLM is configured |

Written to Twenty as one `EnrichmentJob` record per run (see
`../twenty-app/src/objects/enrichment-job.object.ts`), plus
`Company.lastEnrichedAt`.

```bash
# Enrich one company now, synchronously (also written to Twenty)
curl -X POST localhost:8000/companies/COMPANY_ID/enrich

# Enrich a batch asynchronously (poll GET /jobs/{id} the same way scrape
# jobs are polled -- stage will show ENRICHING while it runs)
curl -X POST localhost:8000/enrichment/jobs \
  -H 'Content-Type: application/json' \
  -d '{"company_ids": ["...", "..."]}'

# Every EnrichmentJob for a company, newest first
curl localhost:8000/companies/COMPANY_ID/enrichment-jobs
```

**A note on "LinkedIn enrichment" specifically:** LinkedIn's Terms of
Service prohibit automated scraping of linkedin.com, so this pipeline never
fetches LinkedIn pages directly. Instead, `enrichment/signals.py` computes
signals from People records this workspace already has — each one carries
a `linkedinUrl` captured by the existing Scrapegraph collection step (a
public-search-based pipeline, not a linkedin.com scrape) at import time.
That's enough for a relative headcount/seniority-mix proxy across companies
in this workspace, but it is **not** a source of real LinkedIn firmographic
data (follower counts, verified headcount, etc.) — that would require
LinkedIn's own official APIs under a partnership agreement, which would
slot in as a new `provider` value in `EnrichmentResult` if it's ever
available, rather than requiring a different pipeline.

**Optional paid data providers** (see `enrichment/providers/`) — Apollo.io and
People Data Labs both have real, self-serve REST APIs and can supplement
the crawl-based signals above with real employee-count/industry/revenue/
tech-stack data: set `APOLLO_API_KEY` and/or `PDL_API_KEY` and the next
enrichment run picks it up automatically, folded into the same
`EnrichmentResult` (merged tech stack, a firmographics paragraph appended
to the summary, `EnrichmentJob.provider` gaining a `+apollo`/
`+people_data_labs` suffix). Neither key set (the default) means
enrichment behaves exactly as described above — everything from the
company's own public site or data already in this workspace. Deliberately
no Clearbit adapter: HubSpot acquired Clearbit and folded it into Breeze
Intelligence, a HubSpot-only, credit-based feature — standalone API access
was cut off for non-HubSpot customers in 2025, so there's no self-serve key
a deployer of this codebase could actually obtain to use it (see
`enrichment/providers/__init__.py` for the full explanation). Provider
field-name mappings are documented inline in `enrichment/providers/apollo.py`
and `people_data_labs.py` and read defensively (`.get()` throughout), since
both vendors' response schemas can shift between plans and API versions —
worth a spot-check against a live response from your own account.

To run enrichment automatically rather than triggering it yourself, start
the scheduler process (opt-in — disabled by default):

```bash
ENRICHMENT_SCHEDULE_ENABLED=true python -m scrapegraph_worker.enrichment_scheduler_main
```

Configure via `.env` (see `.env.example`'s `ENRICHMENT_*` block):

| Variable | Purpose |
|---|---|
| `ENRICHMENT_SCHEDULE_ENABLED` | Off by default — an unattended crawl sweep is a bigger footprint than this service's other defaults |
| `ENRICHMENT_SCHEDULE_HOUR` / `ENRICHMENT_SCHEDULE_MINUTE` / `ENRICHMENT_TIMEZONE` | When the scheduler fires each day |
| `ENRICHMENT_STALE_AFTER_DAYS` | A company is "due" if never enriched, or last enriched longer ago than this |
| `ENRICHMENT_MAX_PER_RUN` | Safety cap on companies crawled per scheduled sweep |

## Recommendation Engine — every morning: contact / ignore / hot / cold / buying intent / best message

See the top-level README for the full description. Quick reference for this service:

```bash
# On-demand digest as JSON (buckets, scores, reasons, best_message per person)
curl localhost:8000/recommendations/daily-digest

# Same digest, pre-rendered as Markdown (what actually gets emailed/Slacked)
curl localhost:8000/recommendations/daily-digest.md

# Trigger delivery now through whatever's configured in .env (email/Slack/
# local-file fallback) -- returns which transport(s) actually succeeded
curl -X POST localhost:8000/recommendations/daily-digest/send
```

To have it run automatically every day at a set time, start the scheduler
process alongside `api`/`worker` (already wired into `docker-compose.yml` as
the `recommendations-scheduler` service):

```bash
python -m scrapegraph_worker.recommendations_scheduler_main
```

Configure via `.env` (see `.env.example`'s `DIGEST_*` block):

| Variable | Purpose |
|---|---|
| `DIGEST_SCHEDULE_HOUR` / `DIGEST_SCHEDULE_MINUTE` / `DIGEST_TIMEZONE` | When the scheduler fires each day |
| `DIGEST_SMTP_*` / `DIGEST_EMAIL_TO` | Optional email delivery |
| `DIGEST_SLACK_WEBHOOK_URL` | Optional Slack delivery |
| `DIGEST_FALLBACK_FILE_PATH` | Where the digest is written if neither of the above is configured |

Every delivery transport is independently optional — the digest is always
computable and always available via the two `GET` endpoints above regardless
of what's configured for delivery.

**Scope reminder:** only People with at least one `ConversationSignal` are
considered (see `scrapegraph_worker/recommendations/engine.py`'s module
docstring) — this ranks people you've already heard back from, it does not
prioritize cold outreach to never-contacted prospects.

## Testing

```bash
pip install -r requirements.txt --break-system-packages
pytest tests/ -v
```

`tests/test_dedup.py` and `tests/test_sync.py` run fully offline — `test_sync.py` uses `FakeTwentyClient` (`tests/conftest.py`), an in-memory stand-in implementing the same surface `sync.py` calls, so the create/dedupe/update logic is verified without a real Twenty instance, Redis, or network access. `tests/test_recommendations_*.py` cover the Recommendation Engine the same way: `test_recommendations_scorer.py` is pure unit tests on `scorer.py` (no fakes needed — it's arithmetic), and `test_recommendations_engine.py`/`test_recommendations_render.py` reuse the same `FakeTwentyClient`, extended with a `conversationSignals` store and minimal `order_by` support, to verify bucketing/ranking/message-selection end to end. `tests/test_enrichment.py` covers Company Enrichment the same way — `website_crawler.crawl_company_site` and the LLM backend are both monkeypatched (no real network/LLM call), and `FakeTwentyClient` was extended with an `enrichmentJobs` store and a `get_record` method for this milestone. `tests/test_workflow.py` covers Workflow Automation the same way again — `derive_workflow_state`'s stage logic and `advance()`'s action-selection are both pure functions of what's in `FakeTwentyClient`, so no crawler/LLM mocking is even needed except for the one test that actually exercises the enrichment hand-off.

**I was not able to actually run this test file in the sandbox this session** — the sandbox had no network access to `pip install` the project's dependencies (`fastapi`, `pydantic`, `httpx`, `pytest`, etc. were not preinstalled; only `beautifulsoup4` happened to already be present). I syntax-checked every new/changed file (`python -m py_compile`) and traced through each test by hand against the implementation, but that is not a substitute for actually executing `pytest`. Please run `pip install -r requirements.txt && pytest tests/test_enrichment.py tests/test_workflow.py tests/test_research.py -v` before trusting this milestone the way the rest of this README's "I ran the full suite" claims apply to earlier milestones — I'd rather flag that gap explicitly than imply a verification that didn't happen. The same caveat applies to `tests/test_workflow.py` and `tests/test_research.py`, added under the same no-network constraint — `test_research.py` in particular is worth running first, since most of it exercises the normalization rules that keep unfounded model output out of the CRM, and those are exactly the assertions you want verified rather than assumed.

What I could **not** verify here, for lack of network/a live Twenty instance: the actual REST endpoint shapes (`/rest/companies`, `/rest/enrichmentJobs`, filter-query syntax) against a real Twenty server, and the RQ/Redis queueing end-to-end for `POST /enrichment/jobs`. Those follow Twenty's documented REST conventions closely (same client, same patterns as ResearchJob), but a first real run against your dev workspace is the true test.

**Same caveat applies to ICP Scoring, AI Outbound Messaging, and Production Readiness** (`tests/test_icp_rubric.py`, `tests/test_outbound.py`, `tests/test_observability.py`) — same sandbox, same no-network constraint, same "syntax-checked and traced by hand, not actually executed" honesty. `test_observability.py` in particular needs `httpx` installed (a `fastapi.testclient.TestClient` dependency) alongside the rest of `requirements.txt`. Run the full suite — `pytest tests/ -v` — before trusting any of this beyond what a careful read of the code supports.

## Known gap this milestone does not fix

`ScrapedLead.company_name` / `.website` are usually empty because the current Scrapegraph CSV output (`InvestorRow`) doesn't populate them — `sync.py` falls back to a regex heuristic (`dedup.derive_company_name_from_title`) that returns `""` rather than a wrong guess when it can't confidently derive a name. This is the same gap flagged in the architecture-analysis document (§4.1) and is upstream of this integration — fixing the scrape phase to emit a real `company_name`/`website` column (e.g. by wiring in the existing `company_profile.py` from the similarity-layer branch) will make `sync.py`'s Company matching meaningfully more accurate without any changes to this worker.

## What's intentionally NOT in this milestone

- The Recommendation Engine never auto-sends anything and never writes back into Twenty — it only reads Person/Company/ConversationSignal data and produces a digest, the same "draft for a human to review" boundary Conversation Intelligence draws around `recommendedReplyDraft`. AI Outbound Messaging (see above) drafts real send-ready copy, but sending itself keeps that same human-in-the-loop boundary for every channel except opt-in email.
- It also doesn't prioritize cold, never-contacted prospects — see its scope note above.
- Company Enrichment's crawl-based signals ("buying signals," "growth indicators") stay keyword/proxy-based, not sourced from a real intent-data or headcount-tracking provider — but optional Apollo/People Data Labs adapters (see "Company Enrichment" above) now supply real firmographic data (employee count, industry, revenue, tech stack) when you configure an API key for either. No live LinkedIn integration exists, and none is planned — see the ToS note in "Company Enrichment" above for why that's a deliberate boundary, not a gap waiting on an API key.
- Company Enrichment's website crawl is a handful of well-known paths (home/about/careers/blog), not a general crawler — companies whose relevant content lives elsewhere (a separate careers site, a PDF, a gated blog) will get a thin or `PARTIAL` result.
- Workflow Automation now automates Import → Enrichment → Research → ICP Scoring → Outreach Drafting. `workflow/engine.py::advance()` still never fakes progress past what it can actually do — a company sits at `OUTREACH_DRAFTED` until a human (or the opt-in email auto-send) actually sends something, since sending is the one step this milestone deliberately keeps manual for every channel except email.
- Research pain points and sales angles are **hypotheses, not findings** — labelled as such in the prompt, the models, the CRM field descriptions, and the rendered output. They're a starting point for a human to validate on a call, never something to assert to a prospect as known fact.
- Research has no non-LLM fallback (unlike enrichment). With `LLM_BASE_URL`/`LLM_MODEL` unset, the research pass returns `RESEARCH_FAILED` with a stated reason rather than emitting keyword-template "insights" that look like analysis but aren't.
- AI Outbound Messaging never automates LinkedIn sending, for ToS/account-risk reasons that no amount of code quality changes — see the "AI Outbound Messaging" section above and `outbound/send/linkedin_adapter.py`.
- Production Readiness (below) is infrastructure scaffolding, not a completed production deployment — no live deploy target, no completed pen test, and rate limiting/observability are single-instance-scoped. See `SECURITY.md` for the full, honest list of what's still outstanding.

## Production Readiness

Phase 9. What exists:

- **CI** (`.github/workflows/ci.yml`): lint (`ruff check`), the full offline
  test suite with coverage, a Docker build sanity-check, and a frontend
  build, on every push/PR to `main`. `.github/dependabot.yml` opens weekly
  dependency-update PRs for pip/npm/Docker/Actions.
- **Production compose** (`docker-compose.prod.yml`): healthchecks,
  `restart: unless-stopped`, per-service resource limits, log rotation, a
  persistent Redis volume, and no ports published except through a
  commented-out reverse-proxy placeholder — see that file's own header
  comment for exactly what it does and doesn't decide for you (it is a
  starting point, not a deploy-target decision).
- **Structured logging + request correlation**
  (`scrapegraph_worker/observability.py`): `LOG_FORMAT=json` for
  aggregator-friendly logs, every line tagged with the request that
  produced it (`X-Request-Id`, echoed back on the response).
- **Health/readiness/metrics**: `GET /health` (liveness only), `GET
  /health/ready` (checks Twenty + the local job store are actually
  reachable, 503s if not), `GET /metrics` (Prometheus format — request
  counts/latency by route, rate-limit rejections).
- **Auth hardening**: `WORKER_API_KEY` comparison is constant-time
  (`hmac.compare_digest`), and an in-process sliding-window rate limiter
  sits in front of every endpoint (`RATE_LIMIT_MAX_REQUESTS`/
  `RATE_LIMIT_WINDOW_SECONDS`, `0` to disable).
- **Load test skeleton** (`loadtest/locustfile.py`): a starting Locust
  script weighted toward the cheap read endpoints, with the LLM-backed
  endpoints deliberately low-weight — see its own docstring.
- **`SECURITY.md`**: an honest checklist of what's handled in code, what's
  a deployment-time decision this repo enables but doesn't force
  (TLS termination, network exposure, secret storage), and what's
  genuinely outstanding and needs a human (a real pen test, dependency
  vulnerability scanning in CI, an incident-response runbook).

What this deliberately does **not** include: an actual chosen deploy
target (k8s manifests, ECS task defs, a specific cloud), a completed
third-party security audit, or CI-integrated dependency vulnerability
scanning beyond Dependabot's update PRs — see `SECURITY.md`'s "Outstanding"
section for the honest list rather than a claim of completeness here.


