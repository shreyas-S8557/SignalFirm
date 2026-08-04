"""Phase 9 -- Production Readiness: observability and request-hardening
primitives shared by `api.py`.

Four independent things live here, each usable on its own:

1. `configure_logging()` -- structured (JSON in prod, human-readable in
   dev) logging with a request-id on every line, so a single request's
   logs can be grepped out of an aggregator (CloudWatch/Datadog/Loki/etc)
   by `X-Request-Id` alone.
2. `RequestIdMiddleware` -- stamps every request/response with a
   correlation id (reuses an inbound `X-Request-Id` if the caller/reverse
   proxy already set one, generates a UUID otherwise).
3. `RateLimitMiddleware` -- a minimal in-memory sliding-window limiter.
   Explicitly NOT a replacement for a real edge rate limiter (Cloudflare,
   an API gateway, nginx's own limit_req) in a multi-instance deployment --
   this is per-process state, so it under-counts across replicas. It's
   here as defense-in-depth for a single-instance deployment and so this
   service isn't defenseless if it's ever exposed without a fronting
   proxy. See SECURITY.md.
4. `/health`, `/health/ready`, `/metrics` -- liveness (always 200 once the
   process is up), readiness (actually checks Twenty + the job store are
   reachable), and Prometheus-format metrics.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time
import uuid
from collections import defaultdict, deque
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

REQUEST_COUNT = Counter(
    "worker_http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
REQUEST_LATENCY = Histogram(
    "worker_http_request_duration_seconds", "HTTP request duration in seconds", ["method", "path"]
)
RATE_LIMITED_COUNT = Counter("worker_rate_limited_total", "Requests rejected by the in-process rate limiter")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging() -> None:
    """Call once at process start (api.py, worker_main.py, every
    *_scheduler_main.py). `LOG_FORMAT=json` (recommended for any real
    deployment, so log lines are directly ingestible by a log aggregator)
    or `LOG_FORMAT=text` (the default -- easier to read in a local
    terminal). `LOG_LEVEL` defaults to INFO.
    """
    log_format = os.getenv("LOG_FORMAT", "text").lower()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    if log_format == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)

    _maybe_init_sentry()


def _maybe_init_sentry() -> None:
    """Optional -- only activates if both the SDK is installed and
    SENTRY_DSN is set, so this never becomes a hard dependency for
    deployments that don't use Sentry. Errors during setup are logged, not
    raised -- observability tooling must never be why the service fails to
    start.
    """
    dsn = os.getenv("SENTRY_DSN", "")
    if not dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=dsn, traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")))
        logging.getLogger(__name__).info("Sentry error reporting enabled.")
    except ImportError:
        logging.getLogger(__name__).warning("SENTRY_DSN is set but sentry-sdk is not installed -- skipping.")
    except Exception:  # noqa: BLE001 - observability setup must never crash the app
        logging.getLogger(__name__).warning("Failed to initialize Sentry.", exc_info=True)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get("X-Request-Id")
        request_id = incoming if incoming else str(uuid.uuid4())
        token = request_id_var.set(request_id)

        start = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        response.headers["X-Request-Id"] = request_id

        # Route template, not the raw path, so /companies/{id}/... doesn't
        # explode Prometheus's label cardinality with one series per id.
        route = request.scope.get("route")
        path_label = route.path if route is not None else request.url.path
        duration = time.monotonic() - start
        REQUEST_COUNT.labels(method=request.method, path=path_label, status=str(response.status_code)).inc()
        REQUEST_LATENCY.labels(method=request.method, path=path_label).observe(duration)

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window limiter keyed by API key (if `X-Api-Key` is present)
    or client IP otherwise. In-memory `deque` of recent timestamps per
    key -- adequate for a single-instance deployment, see this module's
    docstring for the multi-instance caveat.
    """

    def __init__(self, app: FastAPI, *, max_requests: int, window_seconds: float):
        super().__init__(app)
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._max_requests <= 0:
            return await call_next(request)  # 0 or negative disables the limiter entirely

        key = request.headers.get("X-Api-Key") or (request.client.host if request.client else "unknown")
        now = time.monotonic()
        hits = self._hits[key]

        while hits and now - hits[0] > self._window_seconds:
            hits.popleft()

        if len(hits) >= self._max_requests:
            RATE_LIMITED_COUNT.inc()
            return Response(
                content=json.dumps({"detail": "Rate limit exceeded -- try again shortly."}),
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(int(self._window_seconds))},
            )

        hits.append(now)
        return await call_next(request)


def metrics_endpoint() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
