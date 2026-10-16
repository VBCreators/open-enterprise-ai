"""Unit tests for the FastAPI application factory and ASGI entrypoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_enterprise_ai.core.config import get_settings
from open_enterprise_ai.main import create_app


def test_create_app_returns_fastapi_instance() -> None:
    """Verify create_app produces a valid FastAPI instance."""
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "open-enterprise-ai"
    assert app.debug is False
    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"
    assert app.redoc_url is None


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
