"""Unit tests for domain-agnostic application exceptions."""

import pytest

from open_enterprise_ai.core.exceptions import (
    AppException,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationAppError,
)


def test_app_exception_base_defaults() -> None:
    """Verify AppException default attributes and message string representation."""
    exc = AppException()
    assert exc.status_code == 500
    assert exc.error_code == "INTERNAL_SERVER_ERROR"
    assert exc.message == "An internal application error occurred."
    assert exc.detail == "An internal application error occurred."
    assert exc.context == {}
    assert str(exc) == "An internal application error occurred."

    custom_exc = AppException(
        message="Custom internal error message",
        status_code=503,
        error_code="SERVICE_UNAVAILABLE",
        detail="Backend service timed out",
        context={"service": "auth"},
    )
    assert custom_exc.status_code == 503
    assert custom_exc.error_code == "SERVICE_UNAVAILABLE"
    assert custom_exc.detail == "Backend service timed out"
    assert custom_exc.context == {"service": "auth"}
    assert str(custom_exc) == "Custom internal error message"


@pytest.mark.parametrize(
    ("exc_cls", "expected_status", "expected_code", "default_message"),
    [
        (NotFoundError, 404, "RESOURCE_NOT_FOUND", "Resource not found."),
        (ConflictError, 409, "RESOURCE_CONFLICT", "Resource conflict occurred."),
        (UnauthorizedError, 401, "UNAUTHORIZED", "Authentication required."),
        (ForbiddenError, 403, "FORBIDDEN", "Access forbidden."),
        (BadRequestError, 400, "BAD_REQUEST", "Bad request."),
        (ValidationAppError, 422, "VALIDATION_ERROR", "Validation failed."),
    ],
)
def test_app_exception_subclasses(
    exc_cls: type[AppException],
    expected_status: int,
    expected_code: str,
    default_message: str,
) -> None:
    """Verify each AppException subclass carries correct status, code, and default message."""
    exc = exc_cls()
    assert issubclass(exc_cls, AppException)
    assert exc.status_code == expected_status
    assert exc.error_code == expected_code
    assert exc.message == default_message
    assert exc.detail == default_message
    assert str(exc) == default_message

    custom = exc_cls("Custom failure detail", context={"item": "123"})
    assert custom.message == "Custom failure detail"
    assert custom.context == {"item": "123"}
    assert str(custom) == "Custom failure detail"
