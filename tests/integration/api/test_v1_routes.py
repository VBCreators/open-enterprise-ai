"""Integration tests for /v1 versioned endpoints and OpenAPI metadata."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from open_enterprise_ai import __version__
from open_enterprise_ai.core.config import get_settings
from open_enterprise_ai.main import create_app


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolate OpenAPI contact settings and reset settings cache for every test."""
    monkeypatch.setenv("OPENAPI_CONTACT_NAME", "")
    monkeypatch.setenv("OPENAPI_CONTACT_EMAIL", "")
    monkeypatch.setenv("OPENAPI_CONTACT_URL", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_v1_status_returns_200_with_success_envelope() -> None:
    """Verify GET /v1/status returns 200 OK wrapped in SuccessEnvelope[HealthResponse]."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/status")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    assert data["status_code"] == 200
    assert data["data"] == {"status": "ok"}
    assert data["meta"] is not None
    assert data["meta"]["request_id"] == response.headers["x-request-id"]
    assert "timestamp" in data["meta"]


def test_v1_status_preserves_inbound_request_id_in_envelope() -> None:
    """Verify inbound x-request-id header propagates into response meta."""
    app = create_app()
    client = TestClient(app)

    custom_id = "test-request-id-12345"
    response = client.get("/v1/status", headers={"x-request-id": custom_id})
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["request_id"] == custom_id


def test_v1_status_edge_security_headers() -> None:
    """Verify GET /v1/status includes standard edge security headers."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/status")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "x-request-id" in response.headers


def test_openapi_schema_contains_metadata_and_v1_tags() -> None:
    """Verify GET /openapi.json contains expected project metadata, tags, and routes."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()

    # Verify info block
    assert schema["info"]["title"] == "open-enterprise-ai"
    assert schema["info"]["version"] == __version__
    assert (
        schema["info"]["summary"]
        == "Enterprise AI Governance, Security, and LLM Orchestration Platform"
    )
    assert "Open-source enterprise AI harness" in schema["info"]["description"]
    assert "contact" not in schema["info"]

    # Verify tags defined at top level
    tag_names = {tag["name"] for tag in schema.get("tags", [])}
    assert "Operational" in tag_names
    assert "v1" in tag_names

    # Verify paths exist
    paths = schema["paths"]
    assert "/health" in paths
    assert "/version" in paths
    assert "/v1/status" in paths

    # Verify /v1/status operation metadata
    v1_status_op = paths["/v1/status"]["get"]
    assert "Operational" in v1_status_op["tags"]
    assert "v1" in v1_status_op["tags"]
    assert v1_status_op["summary"] == "V1 operational status probe"

    # Verify /health operation metadata
    health_op = paths["/health"]["get"]
    assert "Operational" in health_op["tags"]

    # Verify /version operation metadata
    version_op = paths["/version"]["get"]
    assert "Operational" in version_op["tags"]


def test_openapi_schema_includes_configured_contact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify GET /openapi.json contains contact block when configured via settings."""
    monkeypatch.setenv("OPENAPI_CONTACT_NAME", "Enterprise Support")
    monkeypatch.setenv("OPENAPI_CONTACT_EMAIL", "support@enterprise.ai")
    monkeypatch.setenv("OPENAPI_CONTACT_URL", "")
    get_settings.cache_clear()
    try:
        app = create_app()
        client = TestClient(app)
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["contact"] == {
            "name": "Enterprise Support",
            "email": "support@enterprise.ai",
        }
    finally:
        get_settings.cache_clear()
