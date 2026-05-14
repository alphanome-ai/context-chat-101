from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.v1 import router as v1_router
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/api/health", tags=["health"])
async def health_probe() -> dict[str, str]:
    return {"status": "up", "timestamp": datetime.now(UTC).isoformat()}


@router.get("/api/meta", tags=["meta"])
async def api_meta() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "api_prefix": settings.api_v_prefix,
    }


router.include_router(v1_router, prefix=settings.api_v_prefix)

