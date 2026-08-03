# Opika CRM Sync — Scrapegraph × Twenty integration

```
opika-crm-sync/
├── worker/       Python background service (FastAPI + RQ). Runs OUTSIDE Twenty,
│                 as its own Docker containers. Drives your existing Scrapegraph
│                 CLI pipeline and syncs results into Twenty via its REST API.
│
└── twenty-app/   TypeScript Twenty App. Runs INSIDE Twenty (synced via
                  `yarn twenty dev` into a Twenty monorepo checkout). Declares
                  the ResearchJob / EnrichmentJob / ICPScore custom objects and
                  a webhook route for live progress.
```

**One repo for version control convenience — still two separate deploys.** `worker/` and `twenty-app/` run in different processes and get installed differently; putting them in one folder doesn't merge their runtimes (Twenty's own extension mechanism caps a function at 15 minutes and doesn't run arbitrary Python with a Playwright browser attached, which is why the scraping half has to live outside Twenty). What this folder structure buys you: one `git clone`, one place to look, obviously-paired READMEs, and relative paths (`../twenty-app`, `../worker`) that stay correct as long as you keep them siblings.

## The one thing that actually couples them

A shared secret + a URL:

- `twenty-app` has a server variable `SCRAPE_WORKER_WEBHOOK_SHARED_SECRET`
- `worker/.env` has `TWENTY_WEBHOOK_SHARED_SECRET` (must match, character-for-character) and `TWENTY_PROGRESS_WEBHOOK_URL` (points at the app's webhook route)

That's the entire integration surface. Everything else each side does is independent — `worker/` talks to Twenty's ordinary REST API (Companies/People/Opportunities/Notes) with a plain API key, not through `twenty-app` at all.

## Deploy order

1. **`twenty-app/`** — copy into your Twenty monorepo, `yarn twenty dev`, confirm the three custom objects appear under Settings → Data model, set the shared secret. Full steps: [`twenty-app/README.md`](./twenty-app/README.md).
2. **`worker/`** — create a Twenty API key, fill in `worker/.env` (Twenty URL, API key, the same shared secret, the webhook URL from step 1), `docker compose up --build`. Full steps: [`worker/README.md`](./worker/README.md).
3. Run a small test job (`target: 5`) before a real one — see the worker README's testing section.

If you deploy `worker/` before `twenty-app/` is synced, Companies/People/Opportunities/Notes still get created fine (they don't depend on the app) — only `ResearchJob` writes get skipped (with a logged warning) until the app catches up. Nothing breaks, you just won't see progress inside Twenty until both sides are up.

## What's NOT connected to anything yet

`EnrichmentJob`, `ICPScore`, and the `Company.latestIcpScore`/`latestIcpPriority`/`lastEnrichedAt` fields are declared in `twenty-app/` but nothing writes to them — they're scaffolded now so a later milestone (enrichment, AI research, ICP scoring) doesn't require a breaking schema change. No AI/LLM code exists anywhere in this repo by design, per this milestone's scope.
