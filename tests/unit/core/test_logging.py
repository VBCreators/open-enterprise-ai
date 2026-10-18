"""Unit tests for structured logging configuration and redaction powered by payload-redactor."""

import logging
from typing import Any

import pytest
import structlog

from open_enterprise_ai.core.config import Settings
from open_enterprise_ai.core.logging import (
    configure_logging,
    get_logger,
    scrub_sensitive_data,
)


def test_scrub_sensitive_data_redacts_credentials_and_tokens() -> None:
    """Verify scrub_sensitive_data masks passwords, tokens, API keys, and authorization."""
    event_dict: dict[str, Any] = {
        "event": "user_login",
        "username": "bob",
        "password": "my_password_123",
        "api_key": "raw-api-key-value",
        "authorization": "Bearer secret-token-xyz",
        "cookie": "session=sensitive_cookie_data",
    }

    result = scrub_sensitive_data(None, "info", event_dict)

    assert result["event"] == "user_login"
    assert result["username"] == "bob"
    assert result["password"] == "[REDACTED]"
    assert result["api_key"] == "[REDACTED]"
    assert result["authorization"] == "[REDACTED]"
    assert result["cookie"] == "[REDACTED]"


def test_scrub_sensitive_data_redacts_nested_structures() -> None:
    """Verify scrub_sensitive_data recursively redacts dicts, lists, and tuples."""
    payload: dict[str, Any] = {
        "user": {
            "name": "alice",
            "password": "super-secret-password",
            "token": "bearer-token-value",
        },
        "items_list": ["item1", {"api_key": "raw-api-key"}],
        "metadata": {"db_password": "database_password_999"},
        "safe_field": 42,
    }

    scrubbed = scrub_sensitive_data(None, "info", payload)

    assert scrubbed["user"]["name"] == "alice"
    assert scrubbed["user"]["password"] == "[REDACTED]"
    assert scrubbed["user"]["token"] == "[REDACTED]"
    assert scrubbed["items_list"][0] == "item1"
    assert scrubbed["items_list"][1]["api_key"] == "[REDACTED]"
    assert scrubbed["metadata"]["db_password"] == "[REDACTED]"
    assert scrubbed["safe_field"] == 42


def test_ai_token_metrics_preserved_in_logs() -> None:
    """Verify LLM operational metrics (prompt_tokens, max_tokens, etc.) are never redacted."""
    payload: dict[str, Any] = {
        "event": "llm_completion",
        "prompt_tokens": 150,
        "completion_tokens": 80,
        "total_tokens": 230,
        "max_tokens": 1024,
        "token_count": 230,
        "tokens_per_second": 45.2,
        "cached_tokens": 50,
        "auth_token": "secret-jwt-token",
    }

    scrubbed = scrub_sensitive_data(None, "info", payload)

    assert scrubbed["prompt_tokens"] == 150
    assert scrubbed["completion_tokens"] == 80
    assert scrubbed["total_tokens"] == 230
    assert scrubbed["max_tokens"] == 1024
    assert scrubbed["token_count"] == 230
    assert scrubbed["tokens_per_second"] == 45.2
    assert scrubbed["cached_tokens"] == 50
    assert scrubbed["auth_token"] == "[REDACTED]"


def test_scrub_sensitive_data_masks_traceback_connection_strings() -> None:
    """Verify connection URIs inside formatted exception tracebacks are masked."""
    event_dict: dict[str, Any] = {
        "event": "unhandled_server_error",
        "exception": (
            "Traceback (most recent call last):\n"
            '  File "main.py", line 42, in connect\n'
            "RuntimeError: Failed to connect to postgresql://admin:super_secret_pwd@db.internal:5432/mydb"
        ),
    }

    result = scrub_sensitive_data(None, "error", event_dict)

    assert "super_secret_pwd" not in result["exception"]
    assert "postgresql://admin:[REDACTED]@db.internal:5432/mydb" in result["exception"]


def test_configure_logging_local_console_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify configure_logging configures ConsoleRenderer for local environments."""
    monkeypatch.setenv("APP_ENV", "local")
    settings = Settings(_env_file=())
    configure_logging(settings)

    logger = get_logger("test_local")
    assert logger is not None

    root_handlers = logging.getLogger().handlers
    assert len(root_handlers) > 0
    formatter = root_handlers[0].formatter
    assert isinstance(formatter, structlog.stdlib.ProcessorFormatter)
    assert any(
        isinstance(p, structlog.dev.ConsoleRenderer) for p in formatter.processors
    )


def test_configure_logging_production_json_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify configure_logging configures JSONRenderer for production environments."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "secure-production-secret-12345")
    settings = Settings(_env_file=())
    configure_logging(settings)

    logger = get_logger("test_prod")
    assert logger is not None

    root_handlers = logging.getLogger().handlers
    assert len(root_handlers) > 0
    formatter = root_handlers[0].formatter
    assert isinstance(formatter, structlog.stdlib.ProcessorFormatter)
    assert any(
        isinstance(p, structlog.processors.JSONRenderer) for p in formatter.processors
    )


def test_uvicorn_access_logger_disabled() -> None:
    """Verify uvicorn.access logger is disabled with no handlers and propagate=False."""
    settings = Settings(_env_file=())
    configure_logging(settings)

    uvicorn_logger = logging.getLogger("uvicorn.access")
    assert len(uvicorn_logger.handlers) == 0
    assert uvicorn_logger.propagate is False
