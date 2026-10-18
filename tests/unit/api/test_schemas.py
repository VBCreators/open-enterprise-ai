"""Unit tests for base API envelope schemas, pagination, and error envelopes."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from open_enterprise_ai.api.schemas import (
    ErrorDetail,
    ErrorEnvelope,
    HealthResponse,
    PaginatedResponseEnvelope,
    PaginationMeta,
    ResponseMeta,
    SuccessEnvelope,
)


def test_response_meta_defaults_and_timestamp() -> None:
    """Verify ResponseMeta generates UTC timestamp by default when omitted."""
    before = datetime.now(UTC)
    meta = ResponseMeta()
    after = datetime.now(UTC)

    assert meta.request_id is None
    assert meta.timestamp.tzinfo is not None
    assert before <= meta.timestamp <= after


def test_response_meta_explicit_values() -> None:
    """Verify ResponseMeta accepts custom request_id and timestamp."""
    custom_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    meta = ResponseMeta(request_id="req-123456", timestamp=custom_time)
    assert meta.request_id == "req-123456"
    assert meta.timestamp == custom_time


def test_response_meta_request_id_bounds() -> None:
    """Verify ResponseMeta rejects request_id longer than 64 characters."""
    with pytest.raises(ValidationError) as exc_info:
        ResponseMeta(request_id="a" * 65)
    errors = exc_info.value.errors()
    assert any(err["type"] == "string_too_long" for err in errors)


def test_response_meta_extra_fields_forbidden() -> None:
    """Verify ResponseMeta forbids extra unknown fields."""
    with pytest.raises(ValidationError) as exc_info:
        ResponseMeta.model_validate({"request_id": "req-1", "extra_prop": "bad"})
    assert any(err["type"] == "extra_forbidden" for err in exc_info.value.errors())


def test_response_meta_rejects_naive_timestamp() -> None:
    """Verify ResponseMeta rejects naive datetimes without timezone."""
    with pytest.raises(ValidationError) as exc_info:
        ResponseMeta(timestamp=datetime(2026, 1, 1, 12, 0, 0))
    errors = exc_info.value.errors()
    assert any("timezone" in str(err) for err in errors)


def test_response_meta_normalizes_non_utc_timestamp() -> None:
    """Verify ResponseMeta normalizes non-UTC offsets to UTC."""
    from datetime import timedelta, timezone

    offset = timezone(timedelta(hours=5, minutes=30))
    non_utc_time = datetime(2026, 1, 1, 17, 30, 0, tzinfo=offset)
    meta = ResponseMeta(timestamp=non_utc_time)
    assert meta.timestamp.tzinfo == UTC
    assert meta.timestamp == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_pagination_meta_valid() -> None:
    """Verify PaginationMeta instantiates with valid parameters."""
    meta = PaginationMeta(
        page=1,
        per_page=20,
        total_items=100,
        total_pages=5,
        has_next=True,
        has_prev=False,
    )
    assert meta.page == 1
    assert meta.per_page == 20
    assert meta.total_items == 100
    assert meta.total_pages == 5
    assert meta.has_next is True
    assert meta.has_prev is False


def test_pagination_meta_derives_flags_when_omitted() -> None:
    """Verify has_next and has_prev are computed from page and total_pages when omitted."""
    # First page of multi-page collection
    p1 = PaginationMeta(page=1, per_page=10, total_items=25, total_pages=3)
    assert p1.has_next is True
    assert p1.has_prev is False

    # Middle page
    p2 = PaginationMeta(page=2, per_page=10, total_items=25, total_pages=3)
    assert p2.has_next is True
    assert p2.has_prev is True

    # Last page
    p3 = PaginationMeta(page=3, per_page=10, total_items=25, total_pages=3)
    assert p3.has_next is False
    assert p3.has_prev is True

    # Single page collection
    single = PaginationMeta(page=1, per_page=10, total_items=5, total_pages=1)
    assert single.has_next is False
    assert single.has_prev is False


def test_pagination_meta_preserves_explicit_flags() -> None:
    """Verify explicit has_next/has_prev are preserved without auto-override."""
    custom = PaginationMeta(
        page=1,
        per_page=10,
        total_items=20,
        total_pages=2,
        has_next=False,
        has_prev=True,
    )
    assert custom.has_next is False
    assert custom.has_prev is True


def test_pagination_meta_bounds() -> None:
    """Verify PaginationMeta enforces ge and le constraints."""
    # page < 1
    with pytest.raises(ValidationError):
        PaginationMeta(
            page=0,
            per_page=20,
            total_items=0,
            total_pages=0,
        )

    # per_page < 1
    with pytest.raises(ValidationError):
        PaginationMeta(
            page=1,
            per_page=0,
            total_items=0,
            total_pages=0,
        )

    # per_page > 100 (Invariant #4)
    with pytest.raises(ValidationError):
        PaginationMeta(
            page=1,
            per_page=101,
            total_items=1000,
            total_pages=10,
        )

    # negative total_items
    with pytest.raises(ValidationError):
        PaginationMeta(
            page=1,
            per_page=10,
            total_items=-1,
            total_pages=0,
        )

    # negative total_pages
    with pytest.raises(ValidationError):
        PaginationMeta(
            page=1,
            per_page=10,
            total_items=0,
            total_pages=-1,
        )


def test_pagination_meta_extra_forbidden() -> None:
    """Verify PaginationMeta forbids extra unknown fields."""
    with pytest.raises(ValidationError):
        PaginationMeta.model_validate(
            {
                "page": 1,
                "per_page": 20,
                "total_items": 100,
                "total_pages": 5,
                "extra": "value",
            }
        )


def test_success_envelope_with_pydantic_model() -> None:
    """Verify SuccessEnvelope wraps a typed Pydantic data model."""
    envelope = SuccessEnvelope[HealthResponse](
        status_code=200,
        data=HealthResponse(status="ok"),
        meta=ResponseMeta(request_id="trace-001"),
    )
    assert envelope.status_code == 200
    assert envelope.data.status == "ok"
    assert envelope.meta is not None
    assert envelope.meta.request_id == "trace-001"


def test_success_envelope_with_primitives_and_default_meta() -> None:
    """Verify SuccessEnvelope with string payload and omitted meta."""
    envelope = SuccessEnvelope[str](data="hello world")
    assert envelope.status_code == 200
    assert envelope.data == "hello world"
    assert envelope.meta is None


def test_success_envelope_extra_field_rejected() -> None:
    """Verify SuccessEnvelope rejects unexpected payload fields."""
    with pytest.raises(ValidationError):
        SuccessEnvelope[str].model_validate(
            {"data": "test", "extra_token": "malicious"}
        )


def test_paginated_response_envelope_valid() -> None:
    """Verify PaginatedResponseEnvelope wraps item list with pagination metadata."""
    items = ["item-1", "item-2", "item-3"]
    pagination = PaginationMeta(
        page=1,
        per_page=10,
        total_items=3,
        total_pages=1,
        has_next=False,
        has_prev=False,
    )
    envelope = PaginatedResponseEnvelope[str](
        status_code=200,
        data=items,
        pagination=pagination,
        meta=ResponseMeta(request_id="req-page-1"),
    )
    assert envelope.status_code == 200
    assert envelope.data == items
    assert envelope.pagination.total_items == 3
    assert envelope.meta is not None
    assert envelope.meta.request_id == "req-page-1"


def test_paginated_envelope_max_items_bounds() -> None:
    """Verify PaginatedResponseEnvelope data list is capped at max_length=100 (Invariant #4)."""
    items = [f"item-{i}" for i in range(101)]
    pagination = PaginationMeta(
        page=1,
        per_page=100,
        total_items=101,
        total_pages=2,
        has_next=True,
    )
    with pytest.raises(ValidationError) as exc_info:
        PaginatedResponseEnvelope[str](
            data=items,
            pagination=pagination,
        )
    assert any(err["type"] == "too_long" for err in exc_info.value.errors())


def test_paginated_envelope_extra_forbidden() -> None:
    """Verify PaginatedResponseEnvelope forbids extra fields."""
    pagination = {
        "page": 1,
        "per_page": 10,
        "total_items": 1,
        "total_pages": 1,
        "has_next": False,
        "has_prev": False,
    }
    with pytest.raises(ValidationError):
        PaginatedResponseEnvelope[str].model_validate(
            {
                "data": ["a"],
                "pagination": pagination,
                "extra_key": "injected",
            }
        )


def test_error_detail_valid() -> None:
    """Verify ErrorDetail creates valid structured error with details."""
    detail = ErrorDetail(
        code="INVALID_CREDENTIALS",
        message="The username or password was incorrect.",
        details=[{"field": "password", "reason": "too_short"}],
    )
    assert detail.code == "INVALID_CREDENTIALS"
    assert detail.message == "The username or password was incorrect."
    assert detail.details == [{"field": "password", "reason": "too_short"}]


def test_error_detail_bounded_details() -> None:
    """Verify ErrorDetail details list is capped at max_length=100 (Invariant #4)."""
    many_details = [{"index": i} for i in range(101)]
    with pytest.raises(ValidationError):
        ErrorDetail(
            code="TOO_MANY_ERRORS",
            message="Batch validation failed.",
            details=many_details,
        )


def test_error_detail_extra_forbidden() -> None:
    """Verify ErrorDetail forbids extra fields."""
    with pytest.raises(ValidationError):
        ErrorDetail.model_validate(
            {
                "code": "ERR",
                "message": "msg",
                "unexpected": "blocked",
            }
        )


def test_error_envelope_valid() -> None:
    """Verify ErrorEnvelope instantiates with valid ErrorDetail."""
    err_detail = ErrorDetail(code="NOT_FOUND", message="Resource does not exist.")
    envelope = ErrorEnvelope(
        status_code=404,
        error=err_detail,
        meta=ResponseMeta(request_id="req-err-404"),
    )
    assert envelope.status_code == 404
    assert envelope.error.code == "NOT_FOUND"
    assert envelope.meta is not None
    assert envelope.meta.request_id == "req-err-404"


def test_error_envelope_extra_forbidden() -> None:
    """Verify ErrorEnvelope forbids extra fields."""
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate(
            {
                "status_code": 400,
                "error": {"code": "BAD_REQ", "message": "Bad request"},
                "extra_header": "invalid",
            }
        )
