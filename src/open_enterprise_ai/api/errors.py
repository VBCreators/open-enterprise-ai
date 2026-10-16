"""RFC 7807 problem details exception handlers."""

import http
import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from open_enterprise_ai.api.schemas import ProblemDetail

logger = logging.getLogger(__name__)


def _create_problem_response(
    status_code: int,
    type_uri: str,
    title: str,
    detail: str | None = None,
    request_id: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    problem = ProblemDetail(
        type=type_uri,
        title=title,
        status=status_code,
        detail=detail,
        request_id=request_id,
        errors=errors,
    )
    # Apply exception-specific headers first, filtering reserved security keys case-insensitively
    security_headers = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
        "X-Frame-Options": "DENY",
    }
    reserved = {k.lower() for k in security_headers} | {"x-request-id"}
    response_headers: dict[str, str] = {
        k: v for k, v in (headers or {}).items() if k.lower() not in reserved
    }
    response_headers.update(security_headers)
    if request_id:
        response_headers["X-Request-ID"] = request_id

    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type="application/problem+json",
        headers=response_headers,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    status_code = exc.status_code
    try:
        title = http.HTTPStatus(status_code).phrase
    except ValueError:
        title = "HTTP Error"

    raw_detail = exc.detail
    detail_msg = raw_detail if isinstance(raw_detail, str) else title

    headers = dict(exc.headers or {})
    return _create_problem_response(
        status_code=status_code,
        type_uri=f"urn:problem:http-{status_code}",
        title=title,
        detail=detail_msg,
        request_id=request_id,
        headers=headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    sanitized_errors: list[dict[str, Any]] = []
    for err in exc.errors():
        err_type = str(err.get("type", "value_error"))
        loc_items = [str(loc_item) for loc_item in err.get("loc", ())]
        if err_type == "extra_forbidden" and loc_items:
            # Redact user-supplied unknown key name so secrets in key names are never reflected
            loc_items[-1] = "[extra_field]"

        # Redact raw messages for custom validator errors which could reflect submitted input
        msg = (
            "Invalid input value"
            if err_type == "value_error"
            else str(err.get("msg", "Invalid value"))
        )

        sanitized_errors.append(
            {
                "loc": loc_items,
                "type": err_type,
                "msg": msg,
            }
        )
    return _create_problem_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        type_uri="urn:problem:validation-error",
        title="Unprocessable Entity",
        detail="Request validation failed.",
        request_id=request_id,
        errors=sanitized_errors,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    tb_frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else None
    if tb_frames:
        summary_frames = [f"{f.filename}:{f.lineno} in {f.name}" for f in tb_frames]
        location = " -> ".join(summary_frames)
    else:
        location = "unknown"

    logger.error(
        "Unhandled server error occurred [request_id=%s]: %s [%s]",
        request_id,
        exc.__class__.__name__,
        location,
        extra={"request_id": request_id},
    )
    return _create_problem_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        type_uri="urn:problem:internal-server-error",
        title="Internal Server Error",
        detail="An internal server error occurred.",
        request_id=request_id,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register RFC 7807 problem details handlers on the FastAPI application."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
