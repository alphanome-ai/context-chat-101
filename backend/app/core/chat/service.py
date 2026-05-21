from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.core.llm import get_llm_registry
from app.core.llm.registry import LLMRegistry
from app.core.llm.schemas import ChatCompletionChunk, ChatCompletionResponse, InferenceRequest


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

    async def run(self, request: InferenceRequest) -> ChatRunResult:
        model, resolved_model = self.registry.resolve(request.model)
        resolved_request = request.model_copy(update={"model": resolved_model})

        if resolved_request.stream:
            return ChatStreamResult(chunks=model.stream(resolved_request))

        return await model.complete(resolved_request)
