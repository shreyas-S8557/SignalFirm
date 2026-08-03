# Phase 9 — Frontend

A standalone dashboard for the six pieces from the Phase 9 list:

| Ask | Where it lives |
|---|---|
| Daily dashboard | `src/pages/DailyDashboard.tsx` |
| Recommendations widget | `src/components/RecommendationsWidget.tsx` (embedded in the dashboard; also its own page at `src/pages/RecommendationsPage.tsx`) |
| Suggested Message button | `src/components/SuggestedMessageButton.tsx` (used by both the recommendations widget and the conversation panel) |
| Conversation panel | `src/pages/ConversationPanel.tsx` |
| AI Insights panel | `src/pages/AIInsightsPanel.tsx` |
| Research tab | `src/pages/ResearchTab.tsx` |

## Why this is a standalone app, not Twenty panels

This repo has `twenty-app/` (custom objects/fields/webhooks) and `worker/`
(the Python service), but not Twenty's own frontend — that's a separate,
enormous monorepo this project doesn't check out. There's currently no way
to compile a real "Company side panel" or "Person record tab" without that
checkout to build against.

So this is built as its own React app that talks directly to the worker's
API and is organized so each piece is a drop-in candidate for embedding
later:

- **Conversation panel** and **AI Insights panel** are written to receive a
  single `{ id, name }` entity and render standalone — exactly the shape
  a Twenty side-panel slot would hand them.
- **Research tab** is written to be one tab among others on a Company
  record, not a full page — it assumes it's already scoped to one company.
- **Recommendations widget** and **Suggested Message button** have no
  page-level assumptions at all; they're already just components.
- **Daily dashboard** is the one piece that's inherently its own page
  (a morning briefing, not a per-record panel) either way.

The `EntityPicker` dropdowns and the left `Sidebar` in `App.tsx` exist only
to give these components something to be scoped to outside of Twenty's own
record pages — that shell is the part to throw away first when porting
into a real Twenty app; the panels/pages underneath it are the part to keep.

## Running it

```bash
cd frontend
npm install
cp .env.example .env.local   # point VITE_API_BASE_URL at your worker, or leave unset
npm run dev
```

With no worker running (or no `VITE_API_BASE_URL` set), every page falls
back to realistic fixture data (`src/lib/fixtures.ts`) and shows a **Sample
data** badge instead of **Live**, so the whole UI is browsable on its own.

To run against a real worker:

```bash
# in worker/
uvicorn scrapegraph_worker.api:app --reload
```

then set `VITE_API_BASE_URL=http://localhost:8000` in `frontend/.env.local`.

## What changed in `worker/`

Three new read-only endpoints were added to `worker/scrapegraph_worker/api.py`
(see that file's "Phase 9" docstring) because the pieces above needed data
the worker computes but never exposed as a list:

- `GET /people/{person_id}/conversation-signals` — a person's full
  ConversationSignal history, newest first.
- `GET /companies/{company_id}/research-jobs` — a company's ResearchJob
  history, newest first.
- `GET /companies/{company_id}/insights` — a rollup of ICP score,
  enrichment status, research activity, and conversation-intelligence
  breakdown for a company, gathered from three reads into one response.

All three are thin passthroughs onto `TwentyClient.find_records` /
`get_record` — no new writes, no new business logic. CORS was opened
(`allow_origins=["*"]`) since this is the first browser-origin caller this
service has had; every other caller (Twenty logic-functions, the RQ
worker) talks server-to-server. Tighten this to a specific origin before
deploying anywhere that isn't an internal network.

## Known gaps / next steps

- **No auth on the new endpoints.** The existing `/conversation/analyze`
  route checks a shared-secret Bearer token because it's server-to-server;
  a browser can't hold that secret safely. These read endpoints have no
  equivalent yet — fine for a local/internal dashboard, not fine to expose
  publicly as-is.
- **No "list all people/companies" endpoint.** `src/lib/api.ts`'s
  `listPeople`/`listCompanies` reconstruct a picker list from the daily
  digest, which only includes people with at least one conversation
  signal (see `recommendations/engine.py`'s own scope note). A real
  picker should hit `/rest/people` / `/rest/companies` directly — either
  proxied through the worker or called from within Twenty once embedded.
- **AI Insights panel's ICP fields will mostly read empty right now** —
  `Company.latestIcpScore` is a scaffolded field nothing writes to yet
  (see `company-latest-icp-score.field.ts`), so the panel is built to
  show a clear "not scored yet" state rather than a fake number, and will
  fill in once that milestone ships.
- **The dashboard's `top_pick`/`ranked_by_buying_intent` come straight from
  `/recommendations/daily-digest`**, so anything wrong with the underlying
  scoring (see `recommendations/scorer.py`) shows up here unchanged —
  this UI doesn't re-derive or second-guess that ranking.
