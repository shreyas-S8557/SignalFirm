"""Environment-driven configuration for the Scrapegraph worker/service.

Nothing here talks to the network at import time -- safe to import in tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TwentySettings:
    # Base URL of the Twenty instance, e.g. "https://crm.yourcompany.com" or
    # "http://localhost:3000" for a local self-hosted dev server.
    base_url: str = field(default_factory=lambda: os.getenv("TWENTY_BASE_URL", "http://localhost:3000"))
    # Workspace API key, created under Settings -> APIs & Webhooks in Twenty.
    api_key: str = field(default_factory=lambda: os.getenv("TWENTY_API_KEY", ""))
    # Request timeout for calls into Twenty's REST Core API.
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv("TWENTY_TIMEOUT_SECONDS", "30")))
    # Twenty enforces max 60 records per batch call -- kept as a named constant
    # so call sites never hardcode a magic number.
    max_batch_size: int = 60
    # Shared secret the worker sends on progress-webhook calls into the Twenty
    # App's HTTP route, and that the Twenty App is expected to validate.
    webhook_shared_secret: str = field(default_factory=lambda: os.getenv("TWENTY_WEBHOOK_SHARED_SECRET", ""))
    # Full URL of the Twenty App's progress-webhook logic function route, e.g.
    # "https://crm.yourcompany.com/s/crm-sync/job-progress". Optional -- if
    # unset, progress is tracked locally only (still visible via the worker's
    # own /jobs API) and never pushed into Twenty's ResearchJob/EnrichmentJob
    # records.
    progress_webhook_url: str = field(default_factory=lambda: os.getenv("TWENTY_PROGRESS_WEBHOOK_URL", ""))
    # Same shape as progress_webhook_url, but for the Conversation
    # Intelligence result -- points at the Twenty App's
    # conversation-signal-webhook.ts route, e.g.
    # ".../s/crm-sync/conversation-signal". Optional -- if unset, analysis
    # still runs and is returned in the API response, it just never gets
    # written back into Twenty as a ConversationSignal record.
    conversation_signal_webhook_url: str = field(
        default_factory=lambda: os.getenv("TWENTY_CONVERSATION_SIGNAL_WEBHOOK_URL", "")
    )


@dataclass(frozen=True)
class LLMSettings:
    """Config for whichever backend answers Conversation Intelligence
    requests (see conversation/llm_client.py). Built around the
    OpenAI-compatible /chat/completions schema so this is a one-line .env
    swap between providers (Groq, OpenRouter, Together, a local Ollama, etc)
    rather than a code change.
    """

    # e.g. "https://api.groq.com/openai/v1", "https://openrouter.ai/api/v1",
    # or "http://localhost:11434/v1" for a local Ollama.
    base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_SECONDS", "30")))
    temperature: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.2")))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "800")))
    # Most OpenAI-compatible backends (Groq, OpenRouter, a recent Ollama)
    # accept `response_format: {"type": "json_object"}`; a handful of free
    # APIs reject unknown fields outright, so this is escape-hatched off
    # rather than assumed.
    supports_json_mode: bool = field(default_factory=lambda: _env_bool("LLM_SUPPORTS_JSON_MODE", True))

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.model)


@dataclass(frozen=True)
class DigestSettings:
    """Config for the Recommendation Engine's daily digest (see
    `recommendations/`). Every delivery transport is optional -- see
    `recommendations/delivery.py` for the fallback chain -- so leaving all
    of these unset still lets the digest be computed and read via
    `GET /recommendations/daily-digest`, it just doesn't get pushed
    anywhere on its own.
    """

    # When `recommendations_scheduler_main.py` fires the digest each day.
    schedule_hour: int = field(default_factory=lambda: int(os.getenv("DIGEST_SCHEDULE_HOUR", "7")))
    schedule_minute: int = field(default_factory=lambda: int(os.getenv("DIGEST_SCHEDULE_MINUTE", "0")))
    timezone: str = field(default_factory=lambda: os.getenv("DIGEST_TIMEZONE", "UTC"))

    # Optional email delivery via plain SMTP.
    smtp_host: str = field(default_factory=lambda: os.getenv("DIGEST_SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("DIGEST_SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("DIGEST_SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("DIGEST_SMTP_PASSWORD", ""))
    smtp_from: str = field(default_factory=lambda: os.getenv("DIGEST_SMTP_FROM", ""))
    smtp_use_tls: bool = field(default_factory=lambda: _env_bool("DIGEST_SMTP_USE_TLS", True))
    email_to: str = field(default_factory=lambda: os.getenv("DIGEST_EMAIL_TO", ""))

    # Optional Slack delivery via an incoming webhook URL.
    slack_webhook_url: str = field(default_factory=lambda: os.getenv("DIGEST_SLACK_WEBHOOK_URL", ""))

    # Used only when neither email nor Slack is configured, so a fresh
    # deploy still produces a visible artifact instead of a silent no-op.
    fallback_file_path: str = field(
        default_factory=lambda: os.getenv("DIGEST_FALLBACK_FILE_PATH", "./daily_digest.md")
    )


@dataclass(frozen=True)
class EnrichmentScheduleSettings:
    """Config for `enrichment_scheduler_main.py`'s automatic-enrichment
    sweep (Phase 4's "Automatic execution" requirement). Mirrors
    `DigestSettings`' shape -- a schedule time plus a batch-size cap so an
    unattended run can't try to enrich thousands of companies in one pass.
    """

    enabled: bool = field(default_factory=lambda: _env_bool("ENRICHMENT_SCHEDULE_ENABLED", False))
    schedule_hour: int = field(default_factory=lambda: int(os.getenv("ENRICHMENT_SCHEDULE_HOUR", "3")))
    schedule_minute: int = field(default_factory=lambda: int(os.getenv("ENRICHMENT_SCHEDULE_MINUTE", "0")))
    timezone: str = field(default_factory=lambda: os.getenv("ENRICHMENT_TIMEZONE", "UTC"))
    # A company is considered due for (re-)enrichment if it has never been
    # enriched, or its lastEnrichedAt is older than this many days.
    stale_after_days: int = field(default_factory=lambda: int(os.getenv("ENRICHMENT_STALE_AFTER_DAYS", "30")))
    # Cap per scheduled run -- keeps one sweep from crawling the entire
    # workspace's companies in a single pass.
    max_companies_per_run: int = field(default_factory=lambda: int(os.getenv("ENRICHMENT_MAX_PER_RUN", "50")))


@dataclass(frozen=True)
class WorkflowSettings:
    """Config for Phase 7 (Workflow Automation) -- see
    scrapegraph_worker/workflow/. Off by default for the same reason
    ENRICHMENT_SCHEDULE_ENABLED is: chaining a website crawl onto every
    single import is a bigger footprint than this service's other
    defaults, so it's opt-in.
    """

    auto_enrich_on_import: bool = field(default_factory=lambda: _env_bool("AUTO_ENRICH_ON_IMPORT", False))
    # Phase 5: chain Enrichment -> Research automatically too. Only has an
    # effect when auto_enrich_on_import is also on (research requires
    # enrichment as grounding -- see research/engine.py) and when an LLM is
    # configured. Separate flag rather than folded into the one above
    # because research costs LLM tokens per company, which enrichment
    # (crawl + optional LLM summary) largely doesn't.
    auto_research_after_enrichment: bool = field(
        default_factory=lambda: _env_bool("AUTO_RESEARCH_AFTER_ENRICHMENT", False)
    )


@dataclass(frozen=True)
class OutboundSettings:
    """Config for Phase 6 -- AI Outbound Messaging (see outbound/). Drafting
    itself always runs through the same LLMSettings as Conversation
    Intelligence/Research; these are specific to identifying the sender in
    generated copy and to the one channel this package can actually send on
    (email) -- see outbound/send/ for why LinkedIn never gets a "sending"
    config at all.
    """

    sender_name: str = field(default_factory=lambda: os.getenv("OUTBOUND_SENDER_NAME", "our team"))
    sender_company: str = field(default_factory=lambda: os.getenv("OUTBOUND_SENDER_COMPANY", "our company"))
    product_one_liner: str = field(default_factory=lambda: os.getenv("OUTBOUND_PRODUCT_ONE_LINER", ""))

    # SMTP for the one automatable send channel (email). Separate from
    # DigestSettings' SMTP block on purpose -- the daily digest and
    # prospect-facing outbound mail often go through different
    # accounts/domains (e.g. a no-reply digest address vs. a rep's own
    # sending domain with SPF/DKIM set up for deliverability).
    smtp_host: str = field(default_factory=lambda: os.getenv("OUTBOUND_SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("OUTBOUND_SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("OUTBOUND_SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("OUTBOUND_SMTP_PASSWORD", ""))
    smtp_from: str = field(default_factory=lambda: os.getenv("OUTBOUND_SMTP_FROM", ""))
    smtp_use_tls: bool = field(default_factory=lambda: _env_bool("OUTBOUND_SMTP_USE_TLS", True))

    # Off by default -- drafting always happens automatically once a
    # company reaches PENDING_OUTREACH_DRAFT, but actually emailing a
    # prospect is a bigger step than drafting, so it stays opt-in even
    # though (unlike LinkedIn) there's a fully compliant path to automate
    # it. LinkedIn/call steps in a sequence are always
    # QUEUED_FOR_MANUAL_SEND regardless of this flag -- see
    # outbound/send/linkedin_adapter.py.
    auto_send_email: bool = field(default_factory=lambda: _env_bool("OUTBOUND_AUTO_SEND_EMAIL", False))
    dry_run: bool = field(default_factory=lambda: _env_bool("OUTBOUND_DRY_RUN", True))

    # Safety cap mirroring EnrichmentScheduleSettings.max_companies_per_run
    # -- how many due follow-up steps outbound_scheduler_main.py's sweep
    # will process in one run.
    max_sequence_steps_per_run: int = field(
        default_factory=lambda: int(os.getenv("OUTBOUND_MAX_SEQUENCE_STEPS_PER_RUN", "50"))
    )


@dataclass(frozen=True)
class QueueSettings:
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    queue_name: str = field(default_factory=lambda: os.getenv("SCRAPE_QUEUE_NAME", "scrapegraph-jobs"))
    job_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("SCRAPE_JOB_TIMEOUT_SECONDS", "3600")))
    default_retry_limit: int = field(default_factory=lambda: int(os.getenv("SCRAPE_JOB_RETRY_LIMIT", "2")))


@dataclass(frozen=True)
class WorkerSettings:
    twenty: TwentySettings = field(default_factory=TwentySettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    digest: DigestSettings = field(default_factory=DigestSettings)
    enrichment_schedule: EnrichmentScheduleSettings = field(default_factory=EnrichmentScheduleSettings)
    workflow: WorkflowSettings = field(default_factory=WorkflowSettings)
    outbound: OutboundSettings = field(default_factory=OutboundSettings)
    queue: QueueSettings = field(default_factory=QueueSettings)
    # Where job state (progress, logs, counts) is persisted for the /jobs API.
    # SQLite is enough for a single-instance worker; swap for Postgres by
    # changing this URL if the worker is ever scaled horizontally.
    job_store_url: str = field(default_factory=lambda: os.getenv("JOB_STORE_URL", "sqlite:///./scrapegraph_jobs.db"))
    dry_run: bool = field(default_factory=lambda: _env_bool("SCRAPE_DRY_RUN", False))
    # Phase 8 -- optional shared-secret check on the read/action endpoints
    # Twenty's app-side proxy logic-functions call (see
    # ../twenty-app/src/logic-functions/worker-*-proxy.ts). Empty by
    # default -- same "wide open by default, tighten via a settings field"
    # philosophy api.py's CORS comment already documents, since the Phase 9
    # standalone frontend hits these same endpoints directly and shouldn't
    # break for anyone who hasn't set this up. When set, callers must send
    # a matching `X-Api-Key` header. This is defense-in-depth on top of
    # (not a replacement for) the primary access control, which is that
    # the Twenty-side proxy routes require an authenticated Twenty user
    # session (`isAuthRequired: true`) before they ever reach this service.
    worker_api_key: str = field(default_factory=lambda: os.getenv("WORKER_API_KEY", ""))

    # Phase 9 -- in-process rate limiting (see observability.py::
    # RateLimitMiddleware). Defaults generous enough not to interfere with
    # normal use (batch enrichment sweeps, the frontend polling /jobs) while
    # still stopping a runaway client/script from hammering the service.
    # Set RATE_LIMIT_MAX_REQUESTS=0 to disable entirely (e.g. if a fronting
    # proxy/gateway already rate-limits and you don't want double-limiting).
    rate_limit_max_requests: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "120")))
    rate_limit_window_seconds: float = field(
        default_factory=lambda: float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    )


def load_settings() -> WorkerSettings:
    return WorkerSettings()
