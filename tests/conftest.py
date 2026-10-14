"""Pytest global fixtures and configuration."""

from collections.abc import Generator

import pytest

from open_enterprise_ai.core.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Generator[None]:
    """Ensure get_settings cache is cleared before and after each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
