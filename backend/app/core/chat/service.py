from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.chat.context import ChatContextManager
from app.core.chat.schemas import ChatRunRequest
from app.core.logging import get_app_logger
from app.core.llm import get_llm_registry
from app.core.llm.registry import LLMRegistry
from app.core.llm.schemas import ChatCompletionChunk, ChatCompletionResponse, InferenceRequest

logger = get_app_logger()


@dataclass(frozen=True)
class ChatStreamResult:
    chunks: AsyncIterator[ChatCompletionChunk]


ChatRunResult = ChatCompletionResponse | ChatStreamResult


class ChatService:
    def __init__(self, registry: LLMRegistry | None = None) -> None:
        self._registry = registry

    @property
    def registry(self) -> LLMRegistry:
        return self._registry or get_llm_registry()

    async def run(
        self,
        request: ChatRunRequest,
        *,
        db: Session,
        user_id: str,
    ) -> ChatRunResult:
        messages = ChatContextManager(db).build_messages(
            user_id=user_id,
            session_id=request.session_id,
            user_message=request.message,
        )
        return await self.run_inference(request.to_inference_request(messages))

    async def run_inference(self, request: InferenceRequest) -> ChatRunResult:
        model, resolved_model = self.registry.resolve(request.model)
        resolved_request = request.model_copy(update={"model": resolved_model})
        # logger.info(
        #     "llm_prompt %s",
        #     resolved_request.model_dump_json(exclude_none=True),
        # )

        if resolved_request.stream:
            return ChatStreamResult(chunks=model.stream(resolved_request))

        return await model.complete(resolved_request)
