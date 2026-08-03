# CRM Sync (Scrapegraph) — Twenty App

Custom-object data model for the Scrapegraph → Twenty integration. Declares:

- **`ResearchJob`** (`/rest/researchJobs`) — one record per scrape-to-CRM sync attempt. Written by `../worker/scrapegraph_worker/sync.py` today.
- **`EnrichmentJob`** (`/rest/enrichmentJobs`) — one record per enrichment attempt. **Scaffolded, not written to yet** — reserved for the enrichment milestone.
- **`ICPScore`** (`/rest/icpScores`) — one record per ICP scoring run. **Scaffolded, not written to yet** — reserved for the ICP scoring milestone.
- Denormalized convenience fields on the standard `Company` object: `latestIcpScore`, `latestIcpPriority`, `lastEnrichedAt` — also not written to yet.
- A `POST /s/crm-sync/job-progress` HTTP route (`src/logic-functions/job-progress-webhook.ts`) that the worker service calls to push live progress onto matching `ResearchJob` records.

**No AI/LLM logic is in this app.** Everything here is schema + a thin webhook — by design, per this milestone's scope.

## Why EnrichmentJob and ICPScore exist already, unused

They're scaffolded now (empty of write-logic) rather than added in a later milestone so the **data model** — and anything built against it (UI panels, relations, the `Company` badges) — doesn't need a breaking schema change when the enrichment/research/scoring logic functions are added. Fields default to `isNullable: true` / zeroed numbers so their presence today is invisible in the UI until something starts writing to them.

## Deploying this app

This package is source only — it hasn't been scaffolded or built inside an actual Twenty checkout, since doing that requires a running Twenty dev server and the `twenty` CLI, neither of which exist in this environment. To deploy:

1. Copy **this `twenty-app/` directory** (not the repo root) into your Twenty CRM checkout under `packages/twenty-apps/public/crm-sync/` (or scaffold a fresh app with `yarn twenty dev:add app` and copy these `src/` files in over the scaffold, keeping the generated `.claude`/config files it produces).
2. Run `yarn install` at the monorepo root so `twenty-sdk` / `twenty-client-sdk` resolve.
3. `yarn twenty dev` — this starts a local Twenty server and syncs the app's objects/fields into your dev workspace. Check **Settings → Data model** to confirm `Research Job`, `Enrichment Job`, and `ICP Score` all appear, tagged with this app.
4. Set `SCRAPE_WORKER_WEBHOOK_SHARED_SECRET` for this app's registration (Settings → Apps → CRM Sync → server variables) to the same value as `TWENTY_WEBHOOK_SHARED_SECRET` in the worker service's `.env`.
5. Point the worker service's `TWENTY_PROGRESS_WEBHOOK_URL` at this route: `https://{your-domain}/s/crm-sync/job-progress` (self-hosted) — see the worker's own README.

## What I could not verify here

I don't have a running Twenty instance or the `twenty-sdk`/`twenty-client-sdk` packages installed in this sandbox (no network access), so **none of this TypeScript has been compiled or synced against a real workspace**. It's written to match Twenty's documented `defineObject`/`defineField`/`defineLogicFunction` conventions exactly (verified against `packages/twenty-docs/developers/extend/apps/*` in your own repo and the shipped `exa`/`document-generator` example apps), but the first real `yarn twenty dev` run is the actual test — expect to fix minor issues (an import path, a missing `CoreApiClient` method name) that only surface at that point, and report back what breaks so the client and constants files can be corrected precisely.

## Known simplification in the webhook

`job-progress-webhook.ts` currently only updates `status` on match (to `FAILED` when the job fails). It does not yet write `processedRows`/`totalRows`/counts onto the `ResearchJob` record itself, because those are per-sync-attempt facts already captured by each `ResearchJob`'s own existence/status, not job-level aggregate facts — modeling "job-level progress" cleanly (e.g. a separate `SyncRun` object keyed by `sourceRunId`) is a reasonable follow-up if you want per-job aggregate progress visible as a single CRM record rather than only via the worker's `/jobs` API.
