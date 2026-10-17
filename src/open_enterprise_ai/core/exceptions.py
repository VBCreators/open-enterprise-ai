"""Core domain-agnostic application exceptions.

These exceptions are pure Python classes without web framework dependencies.
Exception handlers in the API layer translate them into RFC 7807 problem details.
"""

from typing import Any


class AppException(Exception):
    """Base application exception for all domain and core errors."""

    def __init__(
        self,
        message: str = "An internal application error occurred.",
        status_code: int = 500,
        error_code: str = "INTERNAL_SERVER_ERROR",
        detail: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail or message
        self.context = context or {}


class NotFoundError(AppException):
    """Raised when a requested resource does not exist."""

    def __init__(
        self,
        message: str = "Resource not found.",
        detail: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=404,
            error_code="RESOURCE_NOT_FOUND",
            detail=detail or message,
            context=context,
        )


class ConflictError(AppException):
    """Raised when a resource state conflict or unique constraint violation occurs."""

    def __init__(
        self,
        message: str = "Resource conflict occurred.",
        detail: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=409,
            error_code="RESOURCE_CONFLICT",
            detail=detail or message,
            context=context,
        )


class UnauthorizedError(AppException):
    """Raised when authentication credentials are missing or invalid."""

    def __init__(
        self,
        message: str = "Authentication required.",
        detail: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=401,
            error_code="UNAUTHORIZED",
            detail=detail or message,
            context=context,
        )


class ForbiddenError(AppException):
    """Raised when the authenticated principal lacks authorization."""

    def __init__(
        self,
        message: str = "Access forbidden.",
        detail: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=403,
            error_code="FORBIDDEN",
            detail=detail or message,
            context=context,
        )


class BadRequestError(AppException):
    """Raised when an operation cannot be processed due to client error."""

    def __init__(
        self,
        message: str = "Bad request.",
        detail: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=400,
            error_code="BAD_REQUEST",
            detail=detail or message,
            context=context,
        )


class ValidationAppError(AppException):
    """Raised when domain validation logic fails."""

    def __init__(
        self,
        message: str = "Validation failed.",
        detail: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=422,
            error_code="VALIDATION_ERROR",
            detail=detail or message,
            context=context,
        )
