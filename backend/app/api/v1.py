from fastapi import APIRouter

from app.services.llm.api.v1 import router as llm_router

router = APIRouter()


@router.get("/status", tags=["status"])
async def api_status() -> dict[str, str]:
    return {"status": "ready"}


router.include_router(llm_router, prefix="/llm-provider", tags=["llm"])
router.include_router(llm_router, prefix="/llm", tags=["llm"])
