from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.llm import get_llm_registry
from app.core.llm.errors import LLMModelError
from app.core.llm.schemas import (
    ChatCompletionChunk,
    ErrorDetail,
    ErrorMetadata,
    ErrorResponse,
    InferenceRequest,
    ProvidersResponse,
)

router = APIRouter()


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    return get_llm_registry().providers_response()


@router.post("/chat")
async def inference_request(request: InferenceRequest):
    try:
        model, resolved_model = get_llm_registry().resolve(request.model)
    except LLMModelError as exc:
        return _error_response(exc)

    request = request.model_copy(update={"model": resolved_model})

    if request.stream:
        try:
            stream_iter = model.stream(request)
        except LLMModelError as exc:
            return _error_response(exc)

        return StreamingResponse(
            _sse_iterator(stream_iter),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    try:
        response = await model.complete(request)
    except LLMModelError as exc:
        return _error_response(exc)

    return JSONResponse(content=response.model_dump(exclude_none=True))


async def _sse_iterator(chunks: AsyncIterator[ChatCompletionChunk]) -> AsyncIterator[bytes]:
    try:
        async for chunk in chunks:
            yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n".encode()
    except LLMModelError as exc:
        error = ErrorResponse(
            error=ErrorDetail(
                message=exc.message,
                code=exc.error_code,
                metadata=ErrorMetadata(raw=exc.raw) if exc.raw is not None else None,
            )
        )
        yield f"data: {error.model_dump_json(exclude_none=True)}\n\n".encode()
    yield b"data: [DONE]\n\n"


def _error_response(exc: LLMModelError) -> JSONResponse:
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
