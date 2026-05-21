from fastapi import APIRouter

from app.core.llm import get_llm_registry
from app.core.llm.schemas import ProvidersResponse

router = APIRouter()


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    return get_llm_registry().providers_response()
