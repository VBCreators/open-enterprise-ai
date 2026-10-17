"""Structured access logging middleware."""

import time
from typing import Any

import structlog
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger(__name__)


class AccessLogMiddleware:
    """Pure ASGI middleware to emit structured access logs for completed HTTP requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            request = Request(scope)
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            request_id = getattr(request.state, "request_id", None)

            fastapi_scope: dict[str, Any] = scope.get("fastapi") or {}
            effective_ctx = (
                fastapi_scope.get("effective_route_context")
                if isinstance(fastapi_scope, dict)
                else None
            )
            route_path = getattr(effective_ctx, "path", None) or getattr(
                scope.get("route"), "path", None
            )
            path = route_path if isinstance(route_path, str) else "[unmatched]"

            logger.info(
                "http_request_finished",
                http_method=request.method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                user_agent=user_agent,
                request_id=request_id,
            )
