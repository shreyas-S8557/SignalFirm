# Opika CRM Sync — Scrapegraph × Twenty integration

```
opika-crm-sync/
├── worker/       Python background service (FastAPI + RQ). Runs OUTSIDE Twenty,
│                 as its own Docker containers. Drives your existing Scrapegraph
│                 CLI pipeline and syncs results into Twenty via its REST API.
│                 Also hosts the Conversation Intelligence LLM analysis
│                 (`/conversation/analyze`) -- same reasoning as the scraping
│                 half: arbitrary LLM calls don't belong inside Twenty's own
│                 15-minute function sandbox.
│
└── twenty-app/   TypeScript Twenty App. Runs INSIDE Twenty (synced via
                  `yarn twenty dev` into a Twenty monorepo checkout). Declares
                  the ResearchJob / EnrichmentJob / ICPScore / ConversationSignal
                  custom objects, a webhook route for live job progress, a
                  database-event trigger that forwards inbound email replies
                  to the worker, and a second webhook route that receives the
                  analysis back.
```

**One repo for version control convenience — still two separate deploys.** `worker/` and `twenty-app/` run in different processes and get installed differently; putting them in one folder doesn't merge their runtimes (Twenty's own extension mechanism caps a function at 15 minutes and doesn't run arbitrary Python with a Playwright browser attached, which is why the scraping half has to live outside Twenty). What this folder structure buys you: one `git clone`, one place to look, obviously-paired READMEs, and relative paths (`../twenty-app`, `../worker`) that stay correct as long as you keep them siblings.

## The one thing that actually couples them

A shared secret + two URLs, used in **both directions**:

- `twenty-app` has server variables `SCRAPE_WORKER_WEBHOOK_SHARED_SECRET` (the shared secret) and `CONVERSATION_WORKER_BASE_URL` (where the worker lives, so Twenty can call *into* it)
- `worker/.env` has `TWENTY_WEBHOOK_SHARED_SECRET` (must match the above, character-for-character), `TWENTY_PROGRESS_WEBHOOK_URL`, and `TWENTY_CONVERSATION_SIGNAL_WEBHOOK_URL` (the two routes the worker calls *back into* Twenty on)

Worker → Twenty was the whole integration surface originally (job progress). Conversation Intelligence added the reverse direction (Twenty → worker, to hand off a reply for analysis) and reuses the same shared secret rather than introducing a second one — so it's still one secret to keep in sync, just checked on both sides now instead of one. Everything else each side does is independent — `worker/` talks to Twenty's ordinary REST API (Companies/People/Opportunities/Notes) with a plain API key, not through `twenty-app` at all.

## Deploy order

1. **`twenty-app/`** — copy into your Twenty monorepo, `yarn twenty dev`, confirm the four custom objects appear under Settings → Data model, set the shared secret and `CONVERSATION_WORKER_BASE_URL`. Full steps: [`twenty-app/README.md`](./twenty-app/README.md).
2. **`worker/`** — create a Twenty API key, fill in `worker/.env` (Twenty URL, API key, the same shared secret, the two webhook URLs from step 1, and an `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY` for whichever provider you're using), `docker compose up --build`. Full steps: [`worker/README.md`](./worker/README.md).
3. Run a small test job (`target: 5`) before a real one — see the worker README's testing section.
4. Connect a mailbox in Twenty (Settings → Accounts) so inbound replies actually create `Message` records for step 5 to trigger on -- Conversation Intelligence rides on Twenty's own email sync rather than a separate inbox integration.
5. Reply to a test outreach email from a second mailbox and confirm a `ConversationSignal` record shows up on that contact's Person record within a few seconds.

If you deploy `worker/` before `twenty-app/` is synced, Companies/People/Opportunities/Notes still get created fine (they don't depend on the app) — only `ResearchJob` writes and Conversation Intelligence get skipped (with a logged warning, or a silent no-op on the trigger side) until the app catches up. Nothing breaks, you just won't see progress or reply analysis inside Twenty until both sides are up.

## Conversation Intelligence

**When replies arrive**, this module detects **interest, objections, urgency, and sentiment**, then recommends a **reply, follow-up, and next action** -- all as a `ConversationSignal` record for a human to review, never auto-sent or auto-applied.

- *Interest / urgency / sentiment* -- classified by an LLM call, then coerced into a fixed enum before anything is written to Twenty (see `worker/scrapegraph_worker/conversation/analyzer.py`). The model's own wording never reaches a Twenty field directly.
- *Objections* -- a short list the model pulls out of the reply text, capped and sanitized before storage.
- *Recommended next action* -- one of send reply / schedule follow-up / escalate to a human / mark won / mark lost / no action.
- *Recommended reply draft* -- for a human to review and send.
- *Recommended follow-up date* -- only when a follow-up is recommended, computed by the worker from a day-count the model supplies, not parsed from any timestamp the model invents itself.
- *What triggers it* -- a genuine inbound reply, not every `Message` write (see the flow below for how that's determined).

**Flow:** a mailbox reply lands as a Twenty `Message` → `reply-intelligence-trigger.ts` (a database-event trigger, not a webhook) checks it's a genuine inbound reply (not your own outbound send, not a draft) via `MessageChannelMessageAssociation.direction`, resolves the sender to a `Person` via `MessageParticipant`, and POSTs the text to the worker's `/conversation/analyze` → the worker calls the configured LLM, validates/normalizes the result → `conversation-signal-webhook.ts` writes a `ConversationSignal` record and denormalizes `latestInterestLevel`/`latestUrgency`/`lastConversationSignalAt` onto the Person.

**LLM backend is pluggable, not hardcoded.** `worker/scrapegraph_worker/conversation/llm_client.py` speaks the OpenAI-compatible `/chat/completions` schema, so `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY` in `worker/.env` is a one-line swap between providers -- a free-tier API (Groq, OpenRouter, etc.) or a local Ollama all work without a code change.

**What this module deliberately does NOT do:** it never sends a reply, never moves an Opportunity to won/lost, and never books a follow-up on a calendar. `MARK_WON` / `MARK_LOST` / `SCHEDULE_FOLLOW_UP` are recommendations sitting on a `ConversationSignal` record for a human to act on -- turning those into automatic Opportunity/Task writes is a deliberate scope boundary for this milestone, not an oversight, in keeping with `recommendedReplyDraft` never being auto-sent.

## Recommendation Engine

**Every morning**, this module turns what Conversation Intelligence has already
learned into a ranked digest: **who to contact, who to ignore, who's hot,
who's cold, highest buying intent, and a best-first message for each** --
answering exactly the questions above, in that order.

- *Scope* -- only considers People with at least one `ConversationSignal`
  (i.e. `Person.lastConversationSignalAt` is set). Prioritizing brand-new,
  never-contacted prospects is a different question (ICP scoring) that
  isn't wired up yet -- see "What's NOT connected to anything yet" below --
  so this milestone deliberately doesn't answer it either.
- *Scoring* -- a deterministic 0-100 "buying intent" score from interest
  level, urgency, sentiment, and signal recency (a decay curve, so a hot
  reply from six weeks ago doesn't outrank a lukewarm one from yesterday),
  plus an optional bonus from `Company.latestIcpScore`/`latestIcpPriority`
  once a later milestone starts populating those. No new LLM calls happen
  here -- every input is already an enum Conversation Intelligence
  normalized (see `worker/scrapegraph_worker/conversation/analyzer.py`).
- *Contact vs. ignore* -- a separate decision from hot/cold: a resolved
  deal (`MARK_WON`/`MARK_LOST`) or a thread stale past 45 days is always
  "ignore," no matter how hot its last signal looked; an explicit
  `SEND_REPLY`/`ESCALATE_TO_HUMAN` or a due follow-up is always "contact
  today," no matter the score.
- *Best message* -- reuses Conversation Intelligence's own
  `recommendedReplyDraft` whenever the recommended action calls for one
  (that draft already has full thread context a re-derivation from just the
  score wouldn't); falls back to a short, generic re-engagement template
  only when no such draft exists.
- *Delivery* -- `worker/scrapegraph_worker/recommendations_scheduler_main.py`
  runs as its own always-on process and fires the digest at a configured
  time daily (`DIGEST_SCHEDULE_HOUR`/`DIGEST_SCHEDULE_MINUTE`/
  `DIGEST_TIMEZONE`), delivered via email (SMTP) and/or Slack (incoming
  webhook) -- both optional and independent, same "missing config means
  don't send this way, not crash" philosophy as the rest of the worker. On
  demand, hit `GET /recommendations/daily-digest` (JSON) or
  `GET /recommendations/daily-digest.md` (rendered Markdown), or
  `POST /recommendations/daily-digest/send` to trigger delivery manually.
  Full config: [`worker/README.md`](./worker/README.md).
- *What this module deliberately does NOT do* -- no auto-sending: every
  message is a draft for a human to review, same boundary as Conversation
  Intelligence's `recommendedReplyDraft`. It also never writes anything back
  into Twenty (no new object, no field write) -- it only reads existing
  Person/Company/ConversationSignal data and produces a digest.

## What's NOT connected to anything yet

`EnrichmentJob`, `ICPScore`, and the `Company.latestIcpScore`/`latestIcpPriority`/`lastEnrichedAt` fields are declared in `twenty-app/` but nothing writes to them — they're scaffolded now so a later milestone (enrichment, AI research, ICP scoring) doesn't require a breaking schema change. Conversation Intelligence (above) is the first AI/LLM code in this repo; enrichment and ICP scoring still have none. The Recommendation Engine (above) reads `latestIcpScore`/`latestIcpPriority` as an *optional* bonus input if present, but doesn't require them — until a later milestone starts writing them, its ranking runs purely on Conversation Intelligence signal.

