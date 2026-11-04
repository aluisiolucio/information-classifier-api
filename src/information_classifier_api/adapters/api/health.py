from fastapi import APIRouter, HTTPException, status

from ...infrastructure.health import ReadinessChecker
from .deps import ReadinessCheckerDep, SessionDep
from .schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"], include_in_schema=False)


@router.get("/health", response_model=HealthResponse, include_in_schema=False)
@router.get("/health/live", response_model=HealthResponse)
async def health_live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=ReadinessResponse)
async def health_ready(
    session: SessionDep, checker: ReadinessCheckerDep
) -> ReadinessResponse:
    failures = await checker.check(session)
    if failures:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "failed": failures,
            },
        )
    return ReadinessResponse(status="ready", failed=[])


__all__ = ["ReadinessChecker", "router"]
