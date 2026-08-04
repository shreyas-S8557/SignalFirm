# Security

This document is an honest checklist of this service's security posture:
what's handled in code today, what's a deployment-time decision left to
whoever runs it, and what genuinely hasn't been done and needs a human
(not this codebase) to close. Same "report the scaffold as it is, don't
fake progress" convention as the rest of this repo.

## Handled in code

- **API key auth is opt-in and constant-time.** `WORKER_API_KEY` (empty by
  default) gates the read/action endpoints Twenty's own proxy logic
  functions call. Comparison uses `hmac.compare_digest` (see
  `api.py::_require_worker_api_key`), not `==`, so response timing can't
  leak the key one byte at a time.
- **Secrets are never logged or committed.** `.env.example` documents
  every variable name with a placeholder, never a real value; `.env` is
  gitignored. `config.py` reads every credential from the environment,
  never hardcodes a default that looks like a real key.
- **In-process rate limiting** (`observability.py::RateLimitMiddleware`)
  on every endpoint, keyed by API key or client IP. Defense-in-depth, not
  a replacement for an edge rate limiter -- see its own docstring for the
  multi-instance caveat.
- **SQL injection:** not applicable in the way it would be for a
  hand-rolled SQL service -- Twenty access goes through its REST API
  (`twenty_client.py`), and the one place this service does raw SQL
  (`progress.py`, `outbound/sequence.py`) uses parameterized `sqlite3`
  queries throughout, never string-formatted SQL.
- **LLM prompt injection surface is bounded.** Every LLM completion
  (Conversation Intelligence, Research, Outbound Messaging) is parsed into
  a strict pydantic schema before anything reaches a caller or gets
  written to Twenty (see each module's `normalize_result`) -- a prompt
  injection in scraped/enriched text can influence *what the model says*,
  but can't make it emit arbitrary fields, execute code, or escape the
  validated shape.
- **No secrets in generated content.** Outbound drafts and research
  hypotheses are explicitly instructed not to fabricate facts/pricing/
  commitments (see each module's prompt), and nothing in this codebase
  feeds API keys or internal config into an LLM prompt.
- **Dependency manifest is pinned to minimum versions**
  (`requirements.txt`, `frontend/package-lock.json`) -- see "Outstanding"
  below for what pinning alone doesn't cover.
- **LinkedIn automation is deliberately not implemented**
  (`outbound/send/linkedin_adapter.py`) -- not a gap, a decision: scripted
  LinkedIn activity violates their ToS and risks the account being
  restricted, so there's no code path that could be misused for it.

## Deployment-time decisions (this codebase enables them, doesn't force them)

- **TLS termination.** This service speaks plain HTTP -- `docker-
  compose.prod.yml` ships a commented-out reverse-proxy stub
  (Caddy/Traefik/nginx) rather than a baked-in cert, because there's no
  safe default domain/cert to assume. Terminate TLS in front of this
  service before it's reachable from anywhere untrusted.
- **Network exposure.** `docker-compose.prod.yml` publishes no host ports
  except through the reverse-proxy placeholder -- the `api`/`worker`/
  scheduler containers are only reachable inside the compose network by
  default. Keep it that way; only the reverse proxy (or your platform's
  own LB/ingress) should be internet-facing.
- **Secret storage.** `.env` files are fine for local dev; a real
  deployment should use your platform's secret manager (Docker/Swarm
  secrets, Kubernetes Secrets, AWS SSM/Secrets Manager, etc) instead of a
  plaintext file on a host's disk.
- **CORS is wide open by default** (`api.py`, `allow_origins=["*"]`) to
  keep the Phase 9 standalone frontend working out of the box against an
  internal-network deployment. Tighten to your actual frontend origin(s)
  before exposing this API beyond a trusted network.
- **Backups.** Twenty's own database is the system of record and is out
  of this repo's scope to back up. This service's own local state
  (`scrapegraph_jobs.db` -- job progress + outbound sequence schedule) is
  disposable/rebuildable, not something that needs a backup strategy, but
  confirm that assumption still holds if you extend what's stored there.
- **Least-privilege API keys.** `TWENTY_API_KEY` should be scoped to the
  minimum Twenty workspace permissions this service actually needs, not a
  workspace owner key, per Twenty's own key-scoping options -- a repo-side
  README can't enforce this, it has to be done when the key is issued.

## Outstanding -- needs a human, not more code

- **No professional penetration test or third-party security audit has
  been performed on this codebase.** Everything above is defensive coding
  practice and configuration guidance, not a substitute for one. Get one
  before handling real prospect PII at scale or connecting a production
  Twenty workspace with real customer data.
- **CI lints and tests; it doesn't scan for known-vulnerable dependencies
  yet.** `.github/dependabot.yml` opens weekly update PRs for pip/npm/
  Docker/Actions dependencies, which surfaces *some* known-CVE upgrades,
  but nothing runs `pip-audit`/`npm audit` against the current lockfile in
  CI on every PR. Adding that is a small, concrete next step deliberately
  left out of this pass rather than added without anyone reviewing what
  it flags.
- **No formal secrets-scanning pre-commit hook** (e.g. `gitleaks`,
  `trufflehog`) is configured. Worth adding before this repo has a long
  commit history to worry about.
- **Multi-tenant / multi-workspace isolation has not been reviewed.** This
  service is built around a single `TWENTY_API_KEY` for a single
  workspace; running it against multiple customers' Twenty workspaces
  from one deployment would need real isolation work (separate
  credentials, separate job stores, no cross-tenant data paths) that
  hasn't been designed here.
- **Rate limiting is single-instance only** (see
  `observability.py::RateLimitMiddleware`'s docstring) -- a distributed
  rate limiter (Redis-backed, or handled by an edge gateway) is needed
  before running more than one `api` replica behind a load balancer if
  the limiter is meant to hold across replicas.
- **No incident-response runbook exists yet** for this service
  specifically (who gets paged, how to roll back a bad deploy, how to
  rotate a leaked `TWENTY_API_KEY`/`LLM_API_KEY`/`WORKER_API_KEY`). Write
  one before this is handling production traffic.

If you find an actual vulnerability, please report it privately rather
than opening a public issue -- replace this line with your real
disclosure process/email before this repo is public.
