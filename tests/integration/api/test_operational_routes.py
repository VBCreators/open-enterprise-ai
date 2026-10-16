"""Integration tests for operational endpoints, middleware, and error handling."""

import re

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, field_validator

from open_enterprise_ai import __version__
from open_enterprise_ai.core.config import get_settings
from open_enterprise_ai.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient instance for the configured application."""
    app = create_app()
    return TestClient(app)


def test_get_health_returns_200_ok(client: TestClient) -> None:
    """Verify GET /health returns 200 OK with expected status payload."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_get_version_returns_metadata(client: TestClient) -> None:
    """Verify GET /version returns application name, version, and environment."""
    response = client.get("/version")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert data["app_name"] == "open-enterprise-ai"
    assert data["version"] == __version__
    assert data["environment"] == "local"


def test_baseline_security_headers_present(client: TestClient) -> None:
    """Verify baseline edge security headers are returned on all responses."""
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in response.headers


def test_production_environment_includes_hsts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Strict-Transport-Security header is present in production mode."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "secure-production-secret-12345")
    get_settings.cache_clear()

    try:
        app = create_app()
        prod_client = TestClient(app)
        response = prod_client.get("/health")
        assert response.headers["strict-transport-security"] == (
            "max-age=31536000; includeSubDomains"
        )
    finally:
        get_settings.cache_clear()


def test_rfc4122_uuid_request_id_preserved(client: TestClient) -> None:
    """Verify inbound standard RFC 4122 UUID with hyphens is preserved."""
    test_uuid = "550e8400-e29b-41d4-a716-446655440000"
    response = client.get("/health", headers={"X-Request-ID": test_uuid})
    assert response.headers["x-request-id"] == test_uuid


def test_correlation_id_with_underscore_preserved(client: TestClient) -> None:
    """Verify inbound correlation ID containing alphanumeric and underscore is preserved."""
    test_id = "req_trace_9876543210"
    response = client.get("/health", headers={"X-Request-ID": test_id})
    assert response.headers["x-request-id"] == test_id


def test_malformed_request_id_replaced_with_clean_uuid(
    client: TestClient,
) -> None:
    """Verify invalid or malicious X-Request-ID is replaced with a generated UUID."""
    malicious_ids = [
        "<script>alert(1)</script>",
        "short",
        "toolong" + "a" * 60,
        "spaces not allowed",
        "injection\r\nX-Bad: true",
    ]
    for bad_id in malicious_ids:
        response = client.get("/health", headers={"X-Request-ID": bad_id})
        assigned_id = response.headers["x-request-id"]
        assert assigned_id != bad_id
        assert re.fullmatch(r"^[0-9a-f]{32}$", assigned_id) is not None


def test_missing_request_id_generates_clean_uuid(client: TestClient) -> None:
    """Verify missing X-Request-ID is populated with a generated UUID."""
    response = client.get("/health")
    assigned_id = response.headers["x-request-id"]
    assert re.fullmatch(r"^[0-9a-f]{32}$", assigned_id) is not None


def test_not_found_returns_rfc7807_problem_detail(client: TestClient) -> None:
    """Verify 404 response follows RFC 7807 format with application/problem+json."""
    response = client.get("/unknown-endpoint-route")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    data = response.json()
    assert data["type"] == "urn:problem:http-404"
    assert data["title"] == "Not Found"
    assert data["status"] == 404
    assert data["request_id"] is not None


def test_validation_error_returns_rfc7807_and_redacts_input() -> None:
    """Verify 422 validation failure returns RFC 7807 format and redacts raw inputs and validator messages."""

    class StrictTestPayload(BaseModel):
        model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
        count: int = Field(..., ge=1, le=100)
        custom_code: str = Field(..., min_length=1)

        @field_validator("custom_code")
        @classmethod
        def validate_code(cls, v: str) -> str:
            if "invalid" in v:
                raise ValueError(f"Secret code rejected: {v}")
            return v

    app = create_app()

    @app.post("/test-validation")
    async def validation_target(payload: StrictTestPayload) -> dict[str, str]:
        return {"status": "ok"}

    validation_client = TestClient(app)
    sensitive_token = "secret-token-must-not-leak"
    sensitive_code = "invalid-secret-key-12345"
    response = validation_client.post(
        "/test-validation",
        json={
            "count": -10,
            "custom_code": sensitive_code,
            "secret_key": sensitive_token,
        },
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    data = response.json()
    assert data["type"] == "urn:problem:validation-error"
    assert data["title"] == "Unprocessable Entity"
    assert data["status"] == 422
    assert data["request_id"] is not None

    # Invariant #8 & Threat Model: Never leak raw input or secrets in body or error messages
    assert sensitive_token not in response.text
    error_types = {e["type"] for e in data.get("errors", [])}
    assert {"value_error", "greater_than_equal", "extra_forbidden"} <= error_types
    for error in data.get("errors", []):
        assert "input" not in error
        assert "ctx" not in error
        if error["type"] == "value_error":
            assert error["msg"] == "Invalid input value"
        elif error["type"] == "greater_than_equal":
            assert "greater than or equal to" in error["msg"]


def test_unhandled_error_returns_sanitized_rfc7807_problem_detail() -> None:
    """Verify 500 unhandled exception returns sanitized RFC 7807 with full edge security headers."""
    app = create_app()

    @app.get("/test-unhandled-error")
    async def failing_target() -> None:
        raise RuntimeError(
            "Sensitive DB failure: postgres://admin:supersecret@db:5432/db"
        )

    error_client = TestClient(app, raise_server_exceptions=False)
    response = error_client.get("/test-unhandled-error")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    # CR-2 & Invariant #13: Ensure unhandled 500 responses still carry edge security headers
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"] is not None

    data = response.json()
    assert data["type"] == "urn:problem:internal-server-error"
    assert data["title"] == "Internal Server Error"
    assert data["status"] == 500
    assert data["detail"] == "An internal server error occurred."
    assert data["request_id"] is not None

    # Invariant #8 & Threat Model: Never leak stack trace, connection strings, or credentials
    assert "Traceback" not in response.text
    assert "supersecret" not in response.text
    assert "postgres://" not in response.text
