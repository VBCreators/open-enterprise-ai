"""Global application API router."""

from typing import Annotated

from fastapi import APIRouter, Depends

from open_enterprise_ai import __version__
from open_enterprise_ai.api.schemas import HealthResponse, VersionResponse
from open_enterprise_ai.core.config import Settings, get_settings

api_router = APIRouter()


@api_router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service liveness probe",
    description="Operational liveness probe returning ok status for orchestrators and load balancers.",
    responses={200: {"model": HealthResponse}},
)
async def get_health() -> HealthResponse:
    """Return health status of the application."""
    return HealthResponse(status="ok")


@api_router.get(
    "/version",
    response_model=VersionResponse,
    summary="Application version and runtime metadata",
    description="Returns the application name, semantic release version, and environment.",
    responses={200: {"model": VersionResponse}},
)  # audit: ignore[AUTH001] -- Public operational endpoint returning application version
async def get_version(
    settings: Annotated[Settings, Depends(get_settings)],
) -> VersionResponse:
    """Return application version and runtime metadata."""
    return VersionResponse(
        app_name=settings.APP_NAME,
        version=__version__,
        environment=settings.APP_ENV,
    )
