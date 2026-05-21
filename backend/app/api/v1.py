from fastapi import APIRouter

from app.services.agent.api.v1 import router as agent_router
from app.services.auth.api import router as auth_router
from app.services.chat.api.v1 import router as chat_router
from app.services.chat_history.api import router as chat_history_router
from app.services.llm.api.v1 import router as llm_router

router = APIRouter()


@router.get("/status", tags=["status"])
async def api_status() -> dict[str, str]:
    return {"status": "ready"}


router.include_router(llm_router, prefix="/llm", tags=["llm"])
router.include_router(chat_router, prefix="/chat", tags=["chat"])
router.include_router(agent_router, prefix="/agent", tags=["agent"])
router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(chat_history_router, prefix="/chat-sessions", tags=["chat-history"])
