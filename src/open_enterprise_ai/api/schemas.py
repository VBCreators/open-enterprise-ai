"""Operational, envelope, and error response schemas."""

from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class ResponseMeta(BaseModel):
    """Metadata envelope accompanying API responses."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: str | None = Field(
        default=None, max_length=64, description="Correlation request ID"
    )
    timestamp: AwareDatetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC response generation timestamp",
    )

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        """Enforce normalization to UTC for all timezone-aware datetimes."""
        return v.astimezone(UTC)


class PaginationMeta(BaseModel):
    """Pagination metadata for paginated collection responses."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    page: int = Field(..., ge=1, description="Current 1-indexed page number")
    per_page: int = Field(
        ...,
        ge=1,
        le=100,
        description="Items per page (max 100 per Invariant #4)",
    )
    total_items: int = Field(
        ..., ge=0, description="Total number of items matching query"
    )
    total_pages: int = Field(..., ge=0, description="Total number of pages")
    has_next: bool = Field(default=False, description="Whether a next page exists")
    has_prev: bool = Field(default=False, description="Whether a previous page exists")

    @model_validator(mode="after")
    def set_pagination_flags(self) -> Self:
        """Derive has_next and has_prev from page and total_pages when omitted."""
        if "has_next" not in self.model_fields_set:
            self.has_next = self.page < self.total_pages
        if "has_prev" not in self.model_fields_set:
            self.has_prev = self.page > 1 and self.total_pages > 0
        return self


class SuccessEnvelope[DataT](BaseModel):
    """Standard generic success response envelope."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status_code: int = Field(
        default=200, ge=100, le=599, description="HTTP status code"
    )
    data: DataT = Field(..., description="Response payload data")
    meta: ResponseMeta | None = Field(
        default=None, description="Optional response metadata"
    )


class PaginatedResponseEnvelope[DataT](BaseModel):
    """Standard generic paginated response envelope."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status_code: int = Field(
        default=200, ge=100, le=599, description="HTTP status code"
    )
    data: list[DataT] = Field(
        ...,
        max_length=100,
        description="List of paginated items (bounded to max 100 per Invariant #4)",
    )
    pagination: PaginationMeta = Field(..., description="Pagination metadata")
    meta: ResponseMeta | None = Field(
        default=None, description="Optional response metadata"
    )


class ErrorDetail(BaseModel):
    """Standardized structured error detail schema."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Machine-readable error code",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Human-readable error description",
    )
    details: list[dict[str, Any]] | None = Field(
        default=None,
        max_length=100,
        description="Optional field-level error details (bounded to max 100 per Invariant #4)",
    )


class ErrorEnvelope(BaseModel):
    """Standardized API failure response envelope."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status_code: int = Field(..., ge=100, le=599, description="HTTP status code")
    error: ErrorDetail = Field(..., description="Standardized error details")
    meta: ResponseMeta | None = Field(
        default=None, description="Optional response metadata"
    )


class HealthResponse(BaseModel):
    """Liveness probe response model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal["ok"] = "ok"


class VersionResponse(BaseModel):
    """Operational release version response model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    app_name: str = Field(..., min_length=1, max_length=100)
    version: str = Field(..., min_length=1, max_length=50)
    environment: str = Field(..., min_length=1, max_length=50)


class ProblemDetail(BaseModel):
    """RFC 7807 problem details specification."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: str = Field(..., min_length=1, max_length=200)
    title: str = Field(..., min_length=1, max_length=100)
    status: int = Field(..., ge=100, le=599)
    detail: str | None = Field(default=None, max_length=1000)
    request_id: str | None = Field(default=None, max_length=64)
    errors: list[dict[str, Any]] | None = None
