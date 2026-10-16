"""ASGI application entrypoint and application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from open_enterprise_ai.api import api_router
from open_enterprise_ai.api.errors import register_exception_handlers
from open_enterprise_ai.api.middleware import RequestContextMiddleware
from open_enterprise_ai.core.config import get_settings


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

    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url=None if is_production else "/docs",
        redoc_url=None,
        openapi_url=None if is_production else "/openapi.json",
    )

    app.add_middleware(
        RequestContextMiddleware,
        is_production=is_production,
    )

    register_exception_handlers(app)

    app.include_router(api_router)

    return app
