from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.agent import AgentNotImplementedError, AgentService
from app.core.llm.schemas import ErrorDetail, ErrorResponse, InferenceRequest

router = APIRouter()


@router.post("/run")
async def run_agent(request: InferenceRequest) -> JSONResponse:
    try:
        await AgentService().run(request)
    except AgentNotImplementedError as exc:
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content=ErrorResponse(
                error=ErrorDetail(
                    message=str(exc),
                    code="AGENT_NOT_IMPLEMENTED",
                )
            ).model_dump(exclude_none=True),
        )

    return JSONResponse(status_code=status.HTTP_501_NOT_IMPLEMENTED, content={})
