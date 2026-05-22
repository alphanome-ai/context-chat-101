from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.core.agent0 import Agent0Error, Agent0Event, Agent0RunRequest, Agent0Service
from app.core.chat import ChatContextError
from app.core.llm.schemas import ErrorDetail, ErrorMetadata, ErrorResponse

router = APIRouter()


@router.post("/run")
async def run_agent0(request: Agent0RunRequest, current_user: CurrentUser, db: DbSession):
    service = Agent0Service()
    try:
        service.validate_configuration()
        events = service.stream(request, db=db, user_id=current_user.id)
    except ChatContextError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorDetail(message=exc.message, code=exc.error_code)
            ).model_dump(exclude_none=True),
        )
    except Agent0Error as exc:
        return _error_response(exc)

    return StreamingResponse(
        _sse_iterator(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


async def _sse_iterator(events: AsyncIterator[Agent0Event]) -> AsyncIterator[bytes]:
    async for event in events:
        yield f"data: {event.model_dump_json(exclude_none=True)}\n\n".encode()
    yield b"data: [DONE]\n\n"


def _error_response(exc: Agent0Error) -> JSONResponse:
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
