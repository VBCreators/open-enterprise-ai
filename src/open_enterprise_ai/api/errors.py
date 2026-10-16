"""RFC 7807 problem details exception handlers."""

import http
import logging
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
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type="application/problem+json",
        headers=headers,
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
        sanitized_errors.append(
            {
                "loc": [str(loc_item) for loc_item in err.get("loc", ())],
                "type": str(err.get("type", "value_error")),
                "msg": str(err.get("msg", "Invalid value")),
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
    logger.exception(
        "Unhandled server error occurred",
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
