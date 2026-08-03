"""Thin client for whichever LLM backend answers /conversation/analyze.

Deliberately built against the OpenAI-compatible `/chat/completions` schema
rather than any one vendor's SDK, because that schema is what nearly every
free-tier-friendly provider speaks -- Groq, OpenRouter (including its free
model tier), Together, Cerebras, and a locally-run Ollama (via its
`/v1/chat/completions` shim) all accept the same request shape. Point
`LLM_BASE_URL` at whichever one you've got a key for; nothing else in this
module needs to change.

Kept as small and dependency-free as possible (just httpx, already a
dependency via twenty_client.py) so swapping providers is a one-line .env
edit, not a code change.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from ..config import LLMSettings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised for any failure to get a usable completion (network, auth,
    rate limit, empty response, etc). Callers treat this as "analysis
    unavailable right now" rather than a programming error.
    """


class LLMClient:
    def __init__(self, settings: LLMSettings, http_client: Optional[httpx.Client] = None):
        self._settings = settings
        self._http = http_client or httpx.Client(
            base_url=settings.base_url.rstrip("/"),
            timeout=settings.timeout_seconds,
            headers=(
                {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
            ),
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        """Requests a chat completion and returns the raw text content.

        Uses the provider's JSON response-format hint when available
        (`response_format: {"type": "json_object"}` -- supported by Groq,
        OpenRouter, and most OpenAI-compatible backends); providers that
        reject the field can disable it via `LLM_SUPPORTS_JSON_MODE=false`,
        in which case the prompt's own instruction to emit JSON-only is all
        that's enforced (see analyzer.py's markdown-fence stripping for the
        fallback path).
        """
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
        }
        if self._settings.supports_json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = self._http.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"Request to LLM backend failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMError(f"LLM backend returned {response.status_code}: {response.text[:500]}")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {exc}") from exc

        if not content or not content.strip():
            raise LLMError("LLM backend returned an empty completion")

        return content
