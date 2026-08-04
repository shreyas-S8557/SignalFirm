# CRM Sync (Scrapegraph) — Twenty App

Custom-object data model for the Scrapegraph → Twenty integration, plus (as of Phase 8) native UI panels embedded in Twenty's own record pages. Declares:

- **`ResearchJob`** (`/rest/researchJobs`) — one record per scrape-to-CRM sync attempt. Written by `../worker/scrapegraph_worker/sync.py`.
- **`EnrichmentJob`** (`/rest/enrichmentJobs`) — one record per Company Enrichment attempt (Phase 4). Written by `../worker/scrapegraph_worker/enrichment/engine.py`.
- **`ICPScore`** (`/rest/icpScores`) — one record per ICP scoring run. **Scaffolded, not written to yet** — reserved for the ICP scoring milestone (see the top-level README's "What's NOT connected to anything yet").
- Denormalized convenience fields on the standard `Company` object: `latestIcpScore`, `latestIcpPriority` (not written to yet), `lastEnrichedAt` (written by Phase 4).
- Webhook/trigger logic functions: `job-progress-webhook.ts`, `reply-intelligence-trigger.ts`, `conversation-signal-webhook.ts` (worker ↔ Twenty, pre-Phase-8).
- **Phase 8** proxy logic functions (`worker-read-proxy.ts`, `worker-daily-digest-proxy.ts`, `worker-action-proxy.ts`) and front components (`src/front-components/*.front-component.tsx`) — see below.

**No AI/LLM logic is in this app.** Everything here is schema, webhooks, and UI plumbing — all LLM calls happen in the worker service.

## Phase 8 — native UI panels (front components)

Four `defineFrontComponent`s, embedded into Twenty's own UI via `definePageLayoutTab` (extending Twenty's *standard* Company/Person record pages) and one `definePageLayout` (a standalone dashboard this app owns entirely):

| Component | Where it renders | Backed by |
|---|---|---|
| `ai-insights-panel` | Company record page → "AI Insights" tab | `GET /companies/{id}/insights` (Phase 9) + `GET /companies/{id}/workflow` (Phase 7), "Enrich now" button → `POST /companies/{id}/enrich` (Phase 4) |
| `research-tab` | Company record page → "Research" tab | `GET /companies/{id}/research-jobs` + `GET /companies/{id}/enrichment-jobs`, merged into one timeline; "Advance workflow" button → `POST /companies/{id}/workflow/advance` |
| `conversation-panel` | Person record page → "Conversation" tab | `GET /people/{id}/conversation-signals`; folds in the "Suggested Message" feature as a copy-to-clipboard button per signal, rather than a separate component |
| `recommendations-widget` | Standalone "Recommendations" page (this app owns the layout) | `GET /recommendations/daily-digest` |

None of these front components talk to the worker service directly — they call three new logic-function **proxy routes** (`worker-read-proxy.ts`, `worker-daily-digest-proxy.ts`, `worker-action-proxy.ts`), which forward server-to-server to the worker. This is deliberate: a front component runs in the browser and can't hold a secret, so the worker's optional `WORKER_API_KEY` (see `worker/.env.example`) never reaches client code — the actual access control on these routes is `isAuthRequired: true`, meaning Twenty only invokes them for a logged-in, authenticated user in the first place.

### Before you can sync this app: two placeholder IDs need real values

`company-ai-insights-tab.ts`, `company-research-tab.ts`, and `person-conversation-tab.ts` each declare a `pageLayoutUniversalIdentifier` constant currently set to a literal placeholder string (`REPLACE_WITH_YOUR_WORKSPACE_COMPANY_RECORD_PAGE_LAYOUT_ID` / `..._PERSON_...`). This has to be the real universalIdentifier of your workspace's standard Company/Person record page layout. I could not find this documented as a fixed SDK-exported constant (Twenty's own docs example hardcodes a literal value the same way, rather than importing one), and had no live workspace in this sandbox to look it up against — find yours (`yarn twenty entity:list` or your Data Model settings) and replace both placeholders before `yarn twenty app:dev`/`app:publish`. Sync will fail with a clear validation error if you don't, per Twenty's own documented behavior for a missing/invalid `pageLayoutUniversalIdentifier`.

### Also unverified in this sandbox

- **How a front component calls this app's own HTTP routes.** `src/front-components/lib/call-app-route.ts` assumes a plain relative `fetch('/s/crm-sync/...')` resolves correctly from inside the Remote-DOM Web Worker sandbox front components run in. I found solid documentation for `CoreApiClient` (Twenty's own data) and for the worker-service webhook direction, but not for this specific "front component calling its own app's route" case. If it doesn't work as-is, open your browser's Network tab after clicking into one of these tabs and update `APP_ROUTE_BASE_PATH` in that one file — every front component goes through it.
- **The Recommendations page has no sidebar navigation item yet.** Twenty's docs mention navigation items exist as their own linkable entity, but I couldn't confirm the exact `defineNavigationItem`-style API without a live workspace, and didn't want to ship a guessed function signature. Until that's added, reach the page via its direct URL (visible in your workspace's app/developer settings once synced) rather than the sidebar.
- **The exact `RoutePayload.pathParameters` behavior** for the `:resource/:recordId`-style paths in `worker-read-proxy.ts`/`worker-action-proxy.ts`. I found `pathParameters` documented as part of `RoutePayload`'s shape, but the only worked example in what I could access used a router-param-free path — first real deploy is the test for whether Twenty's route matcher parses `:recordId` the way I'm assuming.

## Why EnrichmentJob and ICPScore exist already, unused

They're scaffolded now (empty of write-logic) rather than added in a later milestone so the **data model** — and anything built against it (UI panels, relations, the `Company` badges) — doesn't need a breaking schema change when the enrichment/research/scoring logic functions are added. Fields default to `isNullable: true` / zeroed numbers so their presence today is invisible in the UI until something starts writing to them.

## Deploying this app

This package is source only — it hasn't been scaffolded or built inside an actual Twenty checkout, since doing that requires a running Twenty dev server and the `twenty` CLI, neither of which exist in this environment. To deploy:

1. Copy **this `twenty-app/` directory** (not the repo root) into your Twenty CRM checkout under `packages/twenty-apps/public/crm-sync/` (or scaffold a fresh app with `yarn twenty dev:add app` and copy these `src/` files in over the scaffold, keeping the generated `.claude`/config files it produces).
2. Run `yarn install` at the monorepo root so `twenty-sdk` / `twenty-client-sdk` resolve.
3. `yarn twenty dev` — this starts a local Twenty server and syncs the app's objects/fields into your dev workspace. Check **Settings → Data model** to confirm `Research Job`, `Enrichment Job`, and `ICP Score` all appear, tagged with this app.
4. Set `SCRAPE_WORKER_WEBHOOK_SHARED_SECRET` for this app's registration (Settings → Apps → CRM Sync → server variables) to the same value as `TWENTY_WEBHOOK_SHARED_SECRET` in the worker service's `.env`. Set `CONVERSATION_WORKER_BASE_URL` to the worker's reachable base URL (also used by Phase 8's proxy routes now, not just `reply-intelligence-trigger.ts`). Optionally set `CRM_SYNC_WORKER_API_KEY` if you've set `WORKER_API_KEY` on the worker side.
5. Point the worker service's `TWENTY_PROGRESS_WEBHOOK_URL` at this route: `https://{your-domain}/s/crm-sync/job-progress` (self-hosted) — see the worker's own README.
6. Replace the two page-layout-ID placeholders described in "Phase 8" above before syncing, or the three tab-adding files will fail validation.

## What I could not verify here

I don't have a running Twenty instance or the `twenty-sdk`/`twenty-client-sdk` packages installed in this sandbox (no network access), so **none of this TypeScript has been compiled, type-checked, or synced against a real workspace** — that applies to the Phase 8 front components and proxy routes just as much as the original objects/fields. I researched the current documented `defineFrontComponent`/`definePageLayoutTab`/`RoutePayload` APIs via web search specifically to avoid guessing at a possibly-stale mental model of this fast-moving SDK, and everything here is written to match what I could confirm, with the specific unconfirmed points called out inline (see "Also unverified in this sandbox" above) rather than glossed over. `vitest` is wired up in `package.json` but I did not add any `*.test.ts` files this session — there was no existing test in this app to follow the convention of, and I'd rather flag that as a gap than invent a testing pattern I can't run. The first real `yarn twenty app:dev` run is the actual test for all of it; please report back what breaks.

## Known simplification in the webhook

`job-progress-webhook.ts` currently only updates `status` on match (to `FAILED` when the job fails). It does not yet write `processedRows`/`totalRows`/counts onto the `ResearchJob` record itself, because those are per-sync-attempt facts already captured by each `ResearchJob`'s own existence/status, not job-level aggregate facts — modeling "job-level progress" cleanly (e.g. a separate `SyncRun` object keyed by `sourceRunId`) is a reasonable follow-up if you want per-job aggregate progress visible as a single CRM record rather than only via the worker's `/jobs` API.
