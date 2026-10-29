"""Version 1 API router."""

from fastapi import APIRouter, Request

from open_enterprise_ai.api.schemas import HealthResponse, ResponseMeta, SuccessEnvelope

v1_router = APIRouter(prefix="/v1", tags=["v1"])


@v1_router.get(
    "/status",
    response_model=SuccessEnvelope[HealthResponse],
    tags=["Operational"],
    summary="V1 operational status probe",
    description="Operational liveness and status probe for the v1 API namespace, wrapped in the standardized SuccessEnvelope.",
    responses={200: {"model": SuccessEnvelope[HealthResponse]}},
)  # audit: ignore[AUTH001] -- Public operational status endpoint for v1 namespace
async def get_v1_status(request: Request) -> SuccessEnvelope[HealthResponse]:
    """Return v1 operational status wrapped in SuccessEnvelope."""
    request_id = getattr(request.state, "request_id", None)
    return SuccessEnvelope(
        status_code=200,
        data=HealthResponse(status="ok"),
        meta=ResponseMeta(request_id=request_id),
    )
