"""Unit tests for the FastAPI application factory and ASGI entrypoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_enterprise_ai import __version__
from open_enterprise_ai.core.config import get_settings
from open_enterprise_ai.main import create_app


def test_create_app_returns_fastapi_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify create_app produces a valid FastAPI instance with enriched OpenAPI metadata."""
    monkeypatch.setenv("OPENAPI_CONTACT_NAME", "")
    monkeypatch.setenv("OPENAPI_CONTACT_EMAIL", "")
    monkeypatch.setenv("OPENAPI_CONTACT_URL", "")
    get_settings.cache_clear()
    try:
        app = create_app()
        assert isinstance(app, FastAPI)
        assert app.title == "open-enterprise-ai"
        assert app.version == __version__
        assert (
            app.summary
            == "Enterprise AI Governance, Security, and LLM Orchestration Platform"
        )
        assert "Open-source enterprise AI harness" in (app.description or "")
        assert app.contact is None
        assert app.openapi_tags == [
            {
                "name": "Operational",
                "description": "Liveness probes, operational telemetry, and application status.",
            },
            {
                "name": "v1",
                "description": "Version 1 API routes and contracts.",
            },
        ]
        assert app.debug is False
        assert app.docs_url == "/docs"
        assert app.openapi_url == "/openapi.json"
        assert app.redoc_url is None
    finally:
        get_settings.cache_clear()


def test_create_app_configures_custom_contact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify create_app configures contact from Settings when environment variables are set."""
    monkeypatch.setenv("OPENAPI_CONTACT_NAME", "Enterprise Support")
    monkeypatch.setenv("OPENAPI_CONTACT_EMAIL", "support@enterprise.ai")
    monkeypatch.setenv("OPENAPI_CONTACT_URL", "https://enterprise.ai/support")
    get_settings.cache_clear()
    try:
        app = create_app()
        assert app.contact == {
            "name": "Enterprise Support",
            "email": "support@enterprise.ai",
            "url": "https://enterprise.ai/support",
        }
    finally:
        get_settings.cache_clear()


def test_lifespan_initializes_state() -> None:
    """Verify lifespan context populates app.state.settings."""
    app = create_app()
    with TestClient(app):
        assert hasattr(app.state, "settings")
        assert app.state.settings.APP_NAME == "open-enterprise-ai"


def test_production_environment_disables_docs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify /docs and /openapi.json are disabled in production environment."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "secure-production-secret-12345")
    get_settings.cache_clear()

    try:
        app = create_app()
        assert app.docs_url is None
        assert app.openapi_url is None

        client = TestClient(app)
        docs_resp = client.get("/docs")
        assert docs_resp.status_code == 404
        assert docs_resp.headers["content-type"] == "application/problem+json"

        openapi_resp = client.get("/openapi.json")
        assert openapi_resp.status_code == 404
        assert openapi_resp.headers["content-type"] == "application/problem+json"
    finally:
        get_settings.cache_clear()


def test_production_environment_rejects_debug_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify production environment rejects DEBUG=True at startup."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("SECRET_KEY", "secure-production-secret-12345")
    get_settings.cache_clear()

    try:
        with pytest.raises(
            ValueError, match="DEBUG must not be True in production environment"
        ):
            create_app()
    finally:
        get_settings.cache_clear()
