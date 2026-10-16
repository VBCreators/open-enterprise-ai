"""Operational and error response schemas."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
