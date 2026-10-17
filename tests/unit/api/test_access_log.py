"""Unit tests for structured access log middleware."""

import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.testclient import TestClient
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

from open_enterprise_ai.api.middleware.access_log import AccessLogMiddleware
from open_enterprise_ai.api.middleware.request_context import (
    RequestContextMiddleware,
)
from open_enterprise_ai.core.config import Settings
from open_enterprise_ai.core.logging import configure_logging


@pytest.fixture(autouse=True)
def setup_logging() -> None:
    """Ensure logging pipeline is configured for tests."""
    configure_logging(Settings(_env_file=()))


def test_access_log_emits_finished_event(caplog: pytest.LogCaptureFixture) -> None:
    """Verify AccessLogMiddleware emits http_request_finished structured log."""
    app = FastAPI(
        middleware=[
            Middleware(RequestContextMiddleware),
            Middleware(AccessLogMiddleware),
        ],
    )

    @app.get("/test-access-log")
    async def sample_endpoint() -> Response:
        return JSONResponse({"status": "ok"})

    client = TestClient(app)

    with caplog.at_level("INFO"):
        response = client.get(
            "/test-access-log",
            headers={
                "User-Agent": "TestClientAgent/1.0",
                "X-Request-ID": "req_test_access_12345",
            },
        )
        assert response.status_code == 200

    record = next(
        (
            r
            for r in caplog.records
            if isinstance(r.msg, dict) and r.msg.get("event") == "http_request_finished"
        ),
        None,
    )
    assert record is not None
    msg = record.msg
    assert isinstance(msg, dict)
    assert msg["http_method"] == "GET"
    assert msg["path"] == "/test-access-log"
    assert msg["status_code"] == 200
    assert isinstance(msg["duration_ms"], float)
    assert msg["duration_ms"] >= 0.0
    assert msg["user_agent"] == "TestClientAgent/1.0"
    assert msg["request_id"] == "req_test_access_12345"


def test_access_log_captures_unhandled_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify AccessLogMiddleware records status_code=500 and bubbles on exception."""
    app = FastAPI(
        middleware=[
            Middleware(RequestContextMiddleware),
            Middleware(AccessLogMiddleware),
        ],
    )

    @app.get("/test-failing-route")
    async def failing_endpoint() -> Response:
        raise RuntimeError("Crash inside endpoint")

    client = TestClient(app, raise_server_exceptions=False)

    with caplog.at_level("INFO"):
        response = client.get(
            "/test-failing-route",
            headers={"X-Request-ID": "req_fail_trace_12345"},
        )
        assert response.status_code == 500

    record = next(
        (
            r
            for r in caplog.records
            if isinstance(r.msg, dict) and r.msg.get("event") == "http_request_finished"
        ),
        None,
    )
    assert record is not None
    msg = record.msg
    assert isinstance(msg, dict)
    assert msg["http_method"] == "GET"
    assert msg["path"] == "/test-failing-route"
    assert msg["status_code"] == 500
    assert msg["request_id"] == "req_fail_trace_12345"


def test_access_log_defensive_client_ip_when_client_is_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify AccessLogMiddleware falls back to 'unknown' when request.client is None."""

    class StripClientMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope.get("type") == "http":
                scope["client"] = None
            await self.app(scope, receive, send)

    app = FastAPI(
        middleware=[
            Middleware(StripClientMiddleware),
            Middleware(AccessLogMiddleware),
        ],
    )

    @app.get("/test-no-client")
    async def no_client_endpoint() -> Response:
        return JSONResponse({"status": "ok"})

    client = TestClient(app)

    with caplog.at_level("INFO"):
        response = client.get("/test-no-client")
        assert response.status_code == 200

    record = next(
        (
            r
            for r in caplog.records
            if isinstance(r.msg, dict) and r.msg.get("event") == "http_request_finished"
        ),
        None,
    )
    assert record is not None
    assert isinstance(record.msg, dict)
    assert record.msg["client_ip"] == "unknown"


def test_access_log_records_parameterized_route_template(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify AccessLogMiddleware records route template rather than raw path with params."""
    app = FastAPI(
        middleware=[
            Middleware(RequestContextMiddleware),
            Middleware(AccessLogMiddleware),
        ],
    )

    @app.get("/users/{user_id}")
    async def user_endpoint(user_id: str) -> Response:
        return JSONResponse({"user_id": user_id})

    client = TestClient(app)

    with caplog.at_level("INFO"):
        response = client.get("/users/sensitive-user-id-999")
        assert response.status_code == 200

    record = next(
        (
            r
            for r in caplog.records
            if isinstance(r.msg, dict) and r.msg.get("event") == "http_request_finished"
        ),
        None,
    )
    assert record is not None
    assert isinstance(record.msg, dict)
    assert record.msg["path"] == "/users/{user_id}"


def test_access_log_records_unmatched_for_non_existent_route(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify AccessLogMiddleware records '[unmatched]' when route does not match."""
    app = FastAPI(
        middleware=[
            Middleware(RequestContextMiddleware),
            Middleware(AccessLogMiddleware),
        ],
    )

    client = TestClient(app)

    with caplog.at_level("INFO"):
        response = client.get("/unmatched/probe/with-secret-tokens")
        assert response.status_code == 404

    record = next(
        (
            r
            for r in caplog.records
            if isinstance(r.msg, dict) and r.msg.get("event") == "http_request_finished"
        ),
        None,
    )
    assert record is not None
    assert isinstance(record.msg, dict)
    assert record.msg["path"] == "[unmatched]"
    assert record.msg["status_code"] == 404


def test_access_log_captures_streaming_response_duration(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify AccessLogMiddleware records duration after full streaming response body is sent."""
    app = FastAPI(
        middleware=[
            Middleware(RequestContextMiddleware),
            Middleware(AccessLogMiddleware),
        ],
    )

    @app.get("/test-streaming")
    async def streaming_endpoint() -> StreamingResponse:
        async def stream_generator() -> AsyncIterator[str]:
            yield "chunk1 "
            await asyncio.sleep(0.02)
            yield "chunk2"

        return StreamingResponse(stream_generator(), media_type="text/plain")

    client = TestClient(app)

    with caplog.at_level("INFO"):
        response = client.get("/test-streaming")
        assert response.status_code == 200
        assert response.text == "chunk1 chunk2"

    record = next(
        (
            r
            for r in caplog.records
            if isinstance(r.msg, dict) and r.msg.get("event") == "http_request_finished"
        ),
        None,
    )
    assert record is not None
    assert isinstance(record.msg, dict)
    assert record.msg["path"] == "/test-streaming"
    assert record.msg["status_code"] == 200
    # Proves logging waited for the stream to complete (> 20ms)
    assert record.msg["duration_ms"] >= 15.0
