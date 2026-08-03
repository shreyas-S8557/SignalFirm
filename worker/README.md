# Scrapegraph Worker — background service for CRM population

Turns your existing Scrapegraph CLI pipeline into a queued background job and
syncs its output into Twenty CRM as Companies, Contacts, Opportunities
("Leads"), and Notes ("Activities"), with deduplication. **No AI/LLM logic
lives here** — this milestone is data plumbing only, per scope.

## How a scraped row becomes CRM records

| Scrapegraph concept | Twenty object | Notes |
|---|---|---|
| CPA firm | `Company` | matched by domain (decisive) or fuzzy name (fallback) before creating a new one |
| Decision maker | `Person` | matched by email or LinkedIn URL |
| "this is a new prospect" | `Opportunity` | created **once**, the first time a Company is seen — re-syncing doesn't open duplicate pipeline entries |
| Import event | `Note` | attached to the Company (and Person, if present) via `noteTargets`; shows up in Twenty's timeline automatically |
| Sync attempt (audit trail) | `ResearchJob` (custom object) | see `../twenty-app/` — degrades gracefully (logs a warning, doesn't fail the sync) if that app isn't installed yet |

Twenty has no separate "Lead" object — `Opportunity` is used as the lead/prospect record, consistent with how Twenty's own pipeline concept works.

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

## Testing

```bash
pip install -r requirements.txt --break-system-packages
pytest tests/ -v
```

`tests/test_dedup.py` and `tests/test_sync.py` run fully offline — `test_sync.py` uses `FakeTwentyClient` (`tests/conftest.py`), an in-memory stand-in implementing the same surface `sync.py` calls, so the create/dedupe/update logic is verified without a real Twenty instance, Redis, or network access. **I ran this suite in the sandbox while building it** (15/15 passing) — it caught and fixed two real bugs in the dedup normalization logic before this was ever pointed at real data.

What I could **not** verify here, for lack of network/a live Twenty instance: the actual REST endpoint shapes (`/rest/companies`, `/rest/noteTargets`, filter-query syntax) against a real Twenty server, and the RQ/Redis queueing end-to-end. Those follow Twenty's documented REST conventions closely, but a first real run against your dev workspace is the true test — expect to need small fixes to exact field names (e.g. whether it's `domainName.primaryLinkUrl` or a different path in your Twenty version) once you point this at a real instance, and I'd rather you hit those directly and report back than have me guess further blind.

## Known gap this milestone does not fix

`ScrapedLead.company_name` / `.website` are usually empty because the current Scrapegraph CSV output (`InvestorRow`) doesn't populate them — `sync.py` falls back to a regex heuristic (`dedup.derive_company_name_from_title`) that returns `""` rather than a wrong guess when it can't confidently derive a name. This is the same gap flagged in the architecture-analysis document (§4.1) and is upstream of this integration — fixing the scrape phase to emit a real `company_name`/`website` column (e.g. by wiring in the existing `company_profile.py` from the similarity-layer branch) will make `sync.py`'s Company matching meaningfully more accurate without any changes to this worker.

## What's intentionally NOT in this milestone

- No AI/LLM calls anywhere in `scrapegraph_worker/`.
- `EnrichmentJob` and `ICPScore` custom objects exist in the Twenty App but nothing writes to them yet.
- No message generation, conversation intelligence, or recommendations.

These come in the milestones that follow, per the sequencing in the architecture-analysis document.
