from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from scrapegraph_worker.observability import RateLimitMiddleware, RequestIdMiddleware


def _make_app(*, max_requests: int, window_seconds: float = 60.0) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    app.add_middleware(RateLimitMiddleware, max_requests=max_requests, window_seconds=window_seconds)
    app.add_middleware(RequestIdMiddleware)
    return app


def test_request_id_is_stamped_on_response():
    client = TestClient(_make_app(max_requests=100))
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id")


def test_request_id_is_echoed_back_when_supplied():
    client = TestClient(_make_app(max_requests=100))
    response = client.get("/ping", headers={"X-Request-Id": "abc-123"})
    assert response.headers["X-Request-Id"] == "abc-123"


def test_rate_limit_blocks_after_threshold():
    client = TestClient(_make_app(max_requests=3))
    for _ in range(3):
        assert client.get("/ping").status_code == 200
    blocked = client.get("/ping")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_rate_limit_disabled_when_zero():
    client = TestClient(_make_app(max_requests=0))
    for _ in range(10):
        assert client.get("/ping").status_code == 200
