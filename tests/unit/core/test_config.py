"""Unit tests for configuration management."""

import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from open_enterprise_ai.core.config import (
    INSECURE_DEFAULT_SECRET_KEYS,
    MIN_PRODUCTION_SECRET_KEY_LENGTH,
    PROJECT_ROOT,
    Settings,
    get_settings,
)


def test_defaults_load_with_no_env_or_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify default settings load cleanly when no env vars or files exist."""
    # Ensure clean environment
    for key in (
        "APP_ENV",
        "DEBUG",
        "APP_NAME",
        "APP_HOST",
        "APP_PORT",
        "LOG_LEVEL",
        "SECRET_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    # Use empty temporary directory for env files
    non_existent_env = tmp_path / ".env"
    non_existent_env_local = tmp_path / ".env.local"

    settings = Settings(_env_file=(non_existent_env, non_existent_env_local))
    assert settings.APP_ENV == "local"
    assert settings.DEBUG is False
    assert settings.APP_NAME == "open-enterprise-ai"
    assert settings.APP_HOST == "127.0.0.1"
    assert settings.APP_PORT == 8000
    assert settings.LOG_LEVEL == "INFO"
    assert (
        settings.SECRET_KEY.get_secret_value()
        == "insecure-dev-secret-change-in-production"
    )


def test_os_env_var_overrides_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify OS environment variables take precedence over .env file values."""
    env_file = tmp_path / ".env"
    env_file.write_text("APP_PORT=9000\nAPP_NAME=file_app\n", encoding="utf-8")

    monkeypatch.setenv("APP_PORT", "9500")

    settings = Settings(_env_file=(env_file,))
    # OS env overrides .env file
    assert settings.APP_PORT == 9500
    # Values not in OS env are read from .env file
    assert settings.APP_NAME == "file_app"


def test_env_specific_file_overrides_base_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify .env.{APP_ENV} overrides .env."""
    base_env = tmp_path / ".env"
    base_env.write_text("APP_NAME=base_app\nLOG_LEVEL=INFO\n", encoding="utf-8")

    dev_env = tmp_path / ".env.development"
    dev_env.write_text("APP_NAME=dev_app\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "development")

    settings = Settings(_env_file=(base_env, dev_env))
    assert settings.APP_ENV == "development"
    assert settings.APP_NAME == "dev_app"
    assert settings.LOG_LEVEL == "INFO"


def test_missing_env_file_falls_back_silently(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify missing env files fall back to .env without raising errors."""
    base_env = tmp_path / ".env"
    base_env.write_text("APP_NAME=base_app\n", encoding="utf-8")

    absent_env = tmp_path / ".env.test"

    monkeypatch.setenv("APP_ENV", "test")

    settings = Settings(_env_file=(base_env, absent_env))
    assert settings.APP_ENV == "test"
    assert settings.APP_NAME == "base_app"


def test_app_env_read_from_os_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify APP_ENV inside a .env file cannot override the OS bootstrap APP_ENV."""
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=production\nAPP_NAME=env_app\n", encoding="utf-8")

    # OS env is unset, so bootstrap defaults to local
    monkeypatch.delenv("APP_ENV", raising=False)

    settings = Settings(_env_file=(env_file,))
    assert settings.APP_ENV == "local"
    assert settings.APP_NAME == "env_app"


def test_empty_app_env_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify empty or whitespace-only APP_ENV resolves to local default."""
    monkeypatch.setenv("APP_ENV", "   ")
    settings = Settings(_env_file=())
    assert settings.APP_ENV == "local"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("APP_PORT", "abc"),
        ("APP_PORT", 0),
        ("APP_PORT", 70000),
        ("APP_ENV", "invalid_env"),
        ("LOG_LEVEL", "VERBOSE"),
    ],
)
def test_invalid_values_raise_validation_error(field: str, invalid_value: Any) -> None:
    """Verify invalid types or constraints raise ValidationError."""
    with pytest.raises(ValidationError):
        Settings(**{field: invalid_value})


def test_production_debug_guardrail_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify startup fails if APP_ENV is production and DEBUG is True."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")

    with pytest.raises(ValidationError, match="DEBUG must not be True in production"):
        Settings()


def test_production_with_debug_false_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify production environment is valid when DEBUG is False and SECRET_KEY is secure."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("SECRET_KEY", "prod-secure-random-secret-key-12345")

    settings = Settings(_env_file=())
    assert settings.APP_ENV == "production"
    assert settings.DEBUG is False
    assert (
        settings.SECRET_KEY.get_secret_value() == "prod-secure-random-secret-key-12345"
    )


def test_production_insecure_default_secret_key_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify startup fails if APP_ENV is production and default SECRET_KEY is used."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRETS_DIR", raising=False)
    empty_secrets = tmp_path / "empty_secrets"
    empty_secrets.mkdir()
    monkeypatch.setattr(
        "open_enterprise_ai.core.config.DEFAULT_CONTAINER_SECRETS_DIR", empty_secrets
    )

    with pytest.raises(
        ValidationError, match="SECRET_KEY must be set to a secure, non-default value"
    ):
        Settings(_env_file=())


def test_production_placeholder_secret_key_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify startup fails if APP_ENV is production and placeholder SECRET_KEY is used."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv(
        "SECRET_KEY", "change-this-insecure-dev-secret-to-a-secure-random-value"
    )

    with pytest.raises(
        ValidationError, match="SECRET_KEY must be set to a secure, non-default value"
    ):
        Settings(_env_file=())


def test_production_short_secret_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify startup fails if APP_ENV is production and SECRET_KEY is too short."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("SECRET_KEY", "short-secret")

    with pytest.raises(
        ValidationError,
        match=f"SECRET_KEY must be at least {MIN_PRODUCTION_SECRET_KEY_LENGTH} characters",
    ):
        Settings(_env_file=())


def test_production_whitespace_only_secret_key_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify startup fails if APP_ENV is production and SECRET_KEY is whitespace-only."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("SECRET_KEY", " " * MIN_PRODUCTION_SECRET_KEY_LENGTH)

    with pytest.raises(
        ValidationError,
        match=f"SECRET_KEY must be at least {MIN_PRODUCTION_SECRET_KEY_LENGTH} characters",
    ):
        Settings(_env_file=())


def test_production_insecure_default_with_whitespace_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify startup fails if APP_ENV is production and default key has whitespace padding."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("SECRET_KEY", "  insecure-dev-secret-change-in-production \t\n")

    with pytest.raises(
        ValidationError,
        match="SECRET_KEY must be set to a secure, non-default value",
    ):
        Settings(_env_file=())


def test_secrets_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify secret fields use SecretStr and are masked in repr."""
    secret_value = "super-secret-token-12345"
    monkeypatch.setenv("SECRET_KEY", secret_value)

    settings = Settings()
    settings_repr = repr(settings)

    assert secret_value not in settings_repr
    assert "**********" in settings_repr
    assert secret_value not in repr(settings.SECRET_KEY)
    assert "**********" in repr(settings.SECRET_KEY)
    # The actual secret value is accessible via method
    assert settings.SECRET_KEY.get_secret_value() == secret_value


def test_get_settings_cached_singleton() -> None:
    """Verify get_settings returns a cached singleton and can be reset via cache_clear."""
    instance_one = get_settings()
    instance_two = get_settings()

    assert instance_one is instance_two

    get_settings.cache_clear()
    instance_three = get_settings()

    assert instance_three is not instance_one


def test_env_example_matches_all_settings_fields() -> None:
    """Assert every field in Settings has a matching key in .env.example (prevents template drift)."""
    env_example_path = PROJECT_ROOT / ".env.example"
    assert env_example_path.is_file(), ".env.example file must exist in project root"

    content = env_example_path.read_text(encoding="utf-8")
    example_keys: set[str] = set()

    for line in content.splitlines():
        line = line.strip()
        # Match lines like "KEY=value" or "# KEY=value"
        match = re.match(r"^(?:#\s*)?([A-Za-z0-9_]+)\s*=", line)
        if match:
            example_keys.add(match.group(1))

    settings_fields = set(Settings.model_fields.keys())
    missing_keys = settings_fields - example_keys

    assert not missing_keys, (
        f"Fields in Settings model missing from .env.example: {missing_keys}. "
        "Update .env.example to prevent template drift."
    )


def test_env_example_secret_key_in_insecure_defaults() -> None:
    """Verify the SECRET_KEY placeholder in .env.example is tracked in INSECURE_DEFAULT_SECRET_KEYS."""
    env_example_path = PROJECT_ROOT / ".env.example"
    content = env_example_path.read_text(encoding="utf-8")
    match = re.search(r"^(?:#\s*)?SECRET_KEY=(.+)$", content, re.MULTILINE)
    assert match, "SECRET_KEY must be defined in .env.example"
    placeholder = match.group(1).strip()
    assert placeholder in INSECURE_DEFAULT_SECRET_KEYS, (
        f"Placeholder '{placeholder}' in .env.example must be registered in INSECURE_DEFAULT_SECRET_KEYS"
    )


def test_secrets_dir_support(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify secrets_dir is loaded when SECRETS_DIR is configured."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    secret_file = secrets_dir / "secret_key"
    secret_file.write_text("mounted-k8s-secret-value", encoding="utf-8")

    monkeypatch.setenv("SECRETS_DIR", str(secrets_dir))
    monkeypatch.delenv("SECRET_KEY", raising=False)

    settings = Settings(_env_file=())
    assert settings.SECRET_KEY.get_secret_value() == "mounted-k8s-secret-value"


def test_secrets_dir_run_secrets_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify fallback to /run/secrets loads mounted secret when directory exists."""
    fake_run_secrets = tmp_path / "run_secrets"
    fake_run_secrets.mkdir()
    secret_file = fake_run_secrets / "secret_key"
    secret_file.write_text("run-secrets-mounted-value", encoding="utf-8")

    monkeypatch.setattr(
        "open_enterprise_ai.core.config.DEFAULT_CONTAINER_SECRETS_DIR", fake_run_secrets
    )
    monkeypatch.delenv("SECRETS_DIR", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    settings = Settings(_env_file=())
    assert settings.SECRET_KEY.get_secret_value() == "run-secrets-mounted-value"


def test_dotenv_overrides_mounted_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify dotenv (.env) values take precedence over mounted secrets in secrets_dir."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    secret_file = secrets_dir / "secret_key"
    secret_file.write_text("mounted-secret-value", encoding="utf-8")

    monkeypatch.setenv("SECRETS_DIR", str(secrets_dir))
    monkeypatch.delenv("SECRET_KEY", raising=False)

    # Case 1: .env provides SECRET_KEY -> dotenv overrides secrets_dir
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SECRET_KEY=dotenv-override-secret-key-12345\n", encoding="utf-8"
    )

    settings_with_env_secret = Settings(_env_file=(env_file,))
    assert (
        settings_with_env_secret.SECRET_KEY.get_secret_value()
        == "dotenv-override-secret-key-12345"
    )

    # Case 2: .env omits SECRET_KEY -> secrets_dir mounted value is loaded
    env_file_no_secret = tmp_path / ".env.no_secret"
    env_file_no_secret.write_text("APP_PORT=8080\n", encoding="utf-8")

    settings_fallback_to_mounted = Settings(_env_file=(env_file_no_secret,))
    assert (
        settings_fallback_to_mounted.SECRET_KEY.get_secret_value()
        == "mounted-secret-value"
    )


def test_invalid_secrets_dir_falls_back_to_run_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify non-existent SECRETS_DIR path falls back to /run/secrets when available."""
    fake_run_secrets = tmp_path / "run_secrets"
    fake_run_secrets.mkdir()
    secret_file = fake_run_secrets / "secret_key"
    secret_file.write_text("run-secrets-fallback-value", encoding="utf-8")

    monkeypatch.setattr(
        "open_enterprise_ai.core.config.DEFAULT_CONTAINER_SECRETS_DIR", fake_run_secrets
    )
    # Point SECRETS_DIR to a missing directory path
    missing_dir = tmp_path / "does_not_exist"
    monkeypatch.setenv("SECRETS_DIR", str(missing_dir))
    monkeypatch.delenv("SECRET_KEY", raising=False)

    settings = Settings(_env_file=())
    assert settings.SECRET_KEY.get_secret_value() == "run-secrets-fallback-value"
