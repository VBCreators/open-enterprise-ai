"""ASGI application entrypoint and application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware import Middleware

from open_enterprise_ai.api import api_router
from open_enterprise_ai.api.errors import register_exception_handlers
from open_enterprise_ai.api.middleware import (
    AccessLogMiddleware,
    RequestContextMiddleware,
)
from open_enterprise_ai.core.config import get_settings
from open_enterprise_ai.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan resources."""
    settings = get_settings()
    app.state.settings = settings
    yield


def create_app() -> FastAPI:
    """FastAPI application factory.

    Configures settings, middleware, exception handlers, and API routers.
    Never call this at module level.
    """
    settings = get_settings()
    is_production = settings.APP_ENV == "production"

    configure_logging(settings)

    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url=None if is_production else "/docs",
        redoc_url=None,
        openapi_url=None if is_production else "/openapi.json",
        middleware=[
            Middleware(RequestContextMiddleware, is_production=is_production),
            Middleware(AccessLogMiddleware),
        ],
    )

    register_exception_handlers(app)

    app.include_router(api_router)

    return app
