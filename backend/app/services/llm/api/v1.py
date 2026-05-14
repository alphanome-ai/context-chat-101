from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.llm.providers import LLMProviderError, get_provider
from app.services.llm.schemas import (
    ChatCompletionRequest,
    ErrorDetail,
    ErrorMetadata,
    ErrorResponse,
    ProvidersResponse,
)
from app.services.llm.service import LLMService

router = APIRouter()


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    return LLMService().list_providers()


@router.post("/chat/completion")
async def chat_completion(request: ChatCompletionRequest):
    try:
        provider = get_provider("openai")
    except LLMProviderError as exc:
        return _error_response(exc)

    if request.stream:
        try:
            stream_iter = provider.stream(request)
        except LLMProviderError as exc:
            return _error_response(exc)

        return StreamingResponse(
            stream_iter,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    try:
        response = await provider.complete(request)
    except LLMProviderError as exc:
        return _error_response(exc)

    return JSONResponse(content=response.model_dump(exclude_none=True))


def _error_response(exc: LLMProviderError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                message=exc.message,
                code=exc.error_code,
                metadata=ErrorMetadata(raw=exc.raw) if exc.raw is not None else None,
            )
        ).model_dump(exclude_none=True),
    )
