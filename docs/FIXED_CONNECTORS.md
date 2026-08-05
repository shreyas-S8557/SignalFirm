# Fixed Connectors — Problems, Causes, and Fixes

This document describes the connector / integration bugs found while bringing SignalFirm up end-to-end (Frontend ↔ Worker API ↔ Scrapegraph ↔ Twenty CRM ↔ FreeLLMAPI), why they failed, and what was changed on the `fixed-connectors` branch.

**Scope of code changes:** primarily `worker/` plus a local Twenty self-host compose under `twenty-self-hosted/`. Secrets (`.env`) are not committed.

---

## System under test

| Surface | URL (local) | Role |
|---------|-------------|------|
| Frontend dashboard | `http://localhost:5173` | Vite React UI → worker API |
| Worker API + RQ | `http://localhost:8000` | Scrape, sync, enrichment, LLM |
| Twenty CRM | `http://localhost:3000` | Companies / People / Notes / custom objects |
| FreeLLMAPI | `http://localhost:3001/v1` | OpenAI-compatible LLM gateway |
| Scrapegraph | mounted at `/scrapegraph` in Docker | Lead scrape CLI / collector |

---

## 1. RQ `job_id` never reached the job function

### Problem
Scrape (and enrichment) jobs crashed immediately with a `TypeError` because the worker function did not receive its `job_id` argument. Jobs never progressed past enqueue into real SCRAPING/SYNCING work.

### Why
RQ reserves the keyword argument `job_id=` on `queue.enqueue(...)` for Redis’s own job id. Passing `job_id=...` as a keyword meant RQ consumed it and never forwarded it into the Python function parameters.

### Fix
Pass the application `job_id` positionally (or under a non-reserved name) and keep RQ’s Redis id separate. Covered by `worker/tests/test_jobs_enqueue.py`.

**Files:** `worker/scrapegraph_worker/jobs.py`

---

## 2. Scrape adapter looked for the wrong CSV filename

### Problem
After a scrape run, the adapter could not find lead rows to sync — path / filename mismatch against what Scrapegraph actually writes.

### Why
The adapter expected `data/us_cpa_partners_1000.csv`. The pipeline writes `data/us_angel_investors_1000.csv` (and related variants).

### Fix
Point the adapter at the real CSV path(s) produced by the Scrapegraph repo.

**Files:** `worker/scrapegraph_worker/scrape_adapter.py`

---

## 3. Worker Docker image too old for Scrapegraph

### Problem
In-container scrape failed with import / runtime errors (e.g. missing OpenAI / collector stack). Host Windows venvs also could not run inside Linux containers as-is.

### Why
Scrapegraph’s current collector stack needs **Python 3.12+**, Playwright Chromium, and `scrapegraphai[collector]`. The worker image was on an older base without those deps.

### Fix
Bump `worker/Dockerfile` to `python:3.12-slim`, install `scrapegraphai[collector]`, and install Playwright Chromium with OS deps.

**Files:** `worker/Dockerfile`

---

## 4. Twenty REST create/get responses were mis-unwrapped

### Problem
`create_record` / `get_record` failed or returned `None` even when Twenty succeeded. Company insights returned **404** (“company not found”) for records that clearly existed. Sync could not reliably read back created companies.

### Why
1. Twenty’s mutation payloads use keys like `createCompany` / `updatePerson`, not bare `company` / `person`.
2. Naive singularization turned `companies` → `companie` (strip trailing `s`), so GET unwrapping looked under the wrong key.

### Fix
- Irregular plural map (`companies` → `company`, `people` → `person`, custom objects, etc.).
- Unwrap mutation payloads via `create{Singular}` / `update{Singular}` (with fallback to singular).

**Files:** `worker/scrapegraph_worker/twenty_client.py`

---

## 5. Notes API: `body` field no longer exists

### Problem
Lead sync created company/person then failed on the activity note with HTTP 400: *Object note doesn't have any "body" field.* Sync outcome became `ERROR` and research-job bookkeeping often never ran for that attempt.

### Why
Current Twenty Note objects use RICH_TEXT **`bodyV2`** (e.g. `{ "markdown": "..." }`), not a plain `body` string. Same issue affected outreach draft notes.

### Fix
Write notes as `bodyV2: { markdown: ... }` in sync and outbound engines.

**Files:**
- `worker/scrapegraph_worker/sync.py`
- `worker/scrapegraph_worker/outbound/engine.py`

---

## 6. NoteTargets morph relations: `companyId` / `personId` invalid

### Problem
Attaching notes to companies/people returned HTTP 400. Workflow code that searched outreach notes via `companyId` filters also missed targets.

### Why
Twenty moved note targets to **morph relations**. REST create/read uses:
- `targetCompanyId` (not `companyId`)
- `targetPersonId` (not `personId`)
- Filters: `targetCompanyId[eq]:...`

(`noteId` is still valid.)

### Fix
Create and query noteTargets with `targetCompanyId` / `targetPersonId`. Update workflow note lookup accordingly. Align unit-test fakes/assertions.

**Files:**
- `worker/scrapegraph_worker/sync.py`
- `worker/scrapegraph_worker/outbound/engine.py`
- `worker/scrapegraph_worker/workflow/derive.py`
- `worker/tests/test_outbound.py`
- `worker/tests/test_workflow.py`

---

## 7. Bulk sync hammered Twenty’s rate limit (429)

### Problem
Small `sync_lead` worked, but scrape jobs with hundreds/thousands of rows logged waves of `429 Limit reached (100 tokens per 60000 ms)`, driving high `error_count` and incomplete CRM fills.

### Why
Twenty’s default REST rate limit is tight (~100 tokens / 60s). Dedup lookups (e.g. person-by-LinkedIn) issue many GETs per lead with no backoff.

### Fix
Retry `_request` on `429` / `502` / `503` / `504` with `Retry-After` when present, otherwise exponential backoff (capped).

**Files:** `worker/scrapegraph_worker/twenty_client.py`

**Remaining caveat:** Bulk sync is still slower under the limit; retries make it resilient rather than instant.

---

## 8. FreeLLMAPI 401 from the worker container

### Problem
Worker → `http://host.docker.internal:3001/v1` returned **Invalid API key** even when the same key worked from the host (sometimes).

### Why
Two processes bound port **3001**:
- Host FreeLLMAPI on `0.0.0.0:3001` (correct unified key)
- Docker `freellmapi` publishing `127.0.0.1:3001` (different DB / key)

IPv4 `127.0.0.1` and Docker Desktop’s `host.docker.internal` path preferred the wrong listener → 401.

### Fix (ops, not a repo code change)
Stop the conflicting Docker FreeLLM container while using the host FreeLLMAPI. Confirm worker can `GET /v1/models` with `LLM_API_KEY`.

Do **not** run two FreeLLM instances on the same host port.

---

## 9. Twenty self-hosted layout for local CRM

### Problem
SignalFirm expects a Twenty instance; there was no in-repo compose for a local CRM next to the worker.

### Why
Twenty is a separate deploy. Without a documented local stack, connector testing depended on ad-hoc installs.

### Fix
Add `twenty-self-hosted/` with `docker-compose.yml` and `.env.example` (secrets stay in local `.env`, gitignored).

**Files:**
- `twenty-self-hosted/docker-compose.yml`
- `twenty-self-hosted/.env.example`

---

## Verification checklist (post-fix)

After `docker compose up --build` in `worker/` and Twenty on `:3000`:

1. `GET http://localhost:8000/health` → `ok`
2. `GET http://localhost:8000/health/ready` → `twenty: ok`
3. Frontend `VITE_API_BASE_URL=http://localhost:8000` — digest / insights / research-jobs return **200** with `Access-Control-Allow-Origin: *`
4. `sync_lead` creates company + person + note (`bodyV2`) + researchJob
5. `POST /jobs` with `{"repo_path":"/scrapegraph","target":1}` reaches **SCRAPING** then **SYNCING**
6. Worker container: authenticated `GET {LLM_BASE_URL}/models` → **200**

---

## File change summary

| Area | Change |
|------|--------|
| `jobs.py` | RQ `job_id` enqueue fix |
| `scrape_adapter.py` | Correct Scrapegraph CSV path |
| `Dockerfile` | Python 3.12 + scrapegraphai + Playwright |
| `twenty_client.py` | Singularization, mutation unwrap, 429 retries |
| `sync.py` / `outbound/engine.py` | `bodyV2` + morph noteTargets |
| `workflow/derive.py` | `targetCompanyId` filters |
| Tests | Enqueue test + noteTarget field updates |
| `twenty-self-hosted/` | Local Twenty compose + env example |

---

## What was intentionally not committed

- `worker/.env`, `twenty-self-hosted/.env`, `frontend/.env.local` (secrets)
- `worker/scrapegraph_jobs.db` (local runtime SQLite)
- Yarn `install-state.gz` noise
