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
class QueueSettings:
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    queue_name: str = field(default_factory=lambda: os.getenv("SCRAPE_QUEUE_NAME", "scrapegraph-jobs"))
    job_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("SCRAPE_JOB_TIMEOUT_SECONDS", "3600")))
    default_retry_limit: int = field(default_factory=lambda: int(os.getenv("SCRAPE_JOB_RETRY_LIMIT", "2")))


@dataclass(frozen=True)
class WorkerSettings:
    twenty: TwentySettings = field(default_factory=TwentySettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    queue: QueueSettings = field(default_factory=QueueSettings)
    # Where job state (progress, logs, counts) is persisted for the /jobs API.
    # SQLite is enough for a single-instance worker; swap for Postgres by
    # changing this URL if the worker is ever scaled horizontally.
    job_store_url: str = field(default_factory=lambda: os.getenv("JOB_STORE_URL", "sqlite:///./scrapegraph_jobs.db"))
    dry_run: bool = field(default_factory=lambda: _env_bool("SCRAPE_DRY_RUN", False))


def load_settings() -> WorkerSettings:
    return WorkerSettings()
