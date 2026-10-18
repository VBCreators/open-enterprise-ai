"""Request context and security response headers middleware."""

import re
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Accepts standard RFC 4122 UUIDs (with hyphens), alphanumeric correlation IDs, and underscores
_REQUEST_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to propagate request ID and apply baseline security headers."""

    def __init__(self, app: ASGIApp, is_production: bool = False) -> None:
        super().__init__(app)
        self._is_production = is_production

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        inbound_id = request.headers.get("x-request-id", "").strip()
        if _REQUEST_ID_REGEX.fullmatch(inbound_id):
            request_id = inbound_id
        else:
            request_id = uuid.uuid4().hex

        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "DENY"

        if self._is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response
