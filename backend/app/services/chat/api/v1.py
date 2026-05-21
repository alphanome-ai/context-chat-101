from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.core.chat import ChatContextError, ChatRunRequest, ChatService, ChatStreamResult
from app.core.llm.errors import LLMModelError
from app.core.llm.schemas import (
    ChatCompletionChunk,
    ErrorDetail,
    ErrorMetadata,
    ErrorResponse,
)

router = APIRouter()


@router.post("/run")
async def run_chat(request: ChatRunRequest, current_user: CurrentUser, db: DbSession):
    try:
        result = await ChatService().run(request, db=db, user_id=current_user.id)
    except ChatContextError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorDetail(
                    message=exc.message,
                    code=exc.error_code,
                )
            ).model_dump(exclude_none=True),
        )
    except LLMModelError as exc:
        return _error_response(exc)

    if isinstance(result, ChatStreamResult):
        return StreamingResponse(
            _sse_iterator(result.chunks),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return JSONResponse(content=result.model_dump(exclude_none=True))


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
