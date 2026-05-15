from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Protocol

from app.core.llm.errors import LLMModelError
from app.core.llm.schemas import (
    ChatCompletionChunk,
    ChatCompletionResponse,
    InferenceRequest,
)


class ChatModelProtocol(Protocol):
    async def complete(self, request: InferenceRequest) -> ChatCompletionResponse:
        """Return a complete chat completion response."""
        ...

    def stream(self, request: InferenceRequest) -> AsyncIterator[ChatCompletionChunk]:
        """Yield chat completion chunks."""
        ...


class BaseChatModel(ABC):
    def __init__(
        self,
        *,
        provider_id: str,
        provider_name: str,
        provider_type: str,
        model_id: str,
        model_name: str | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.provider_type = provider_type
        self.model_id = model_id
        self.model_name = model_name

    def resolve_model(self, requested_model: str) -> str:
        if requested_model not in {"default", self.model_id}:
            raise LLMModelError(
                f"Unsupported model: {requested_model}",
                error_code="UNSUPPORTED_MODEL",
                status_code=400,
            )
        return self.model_id

    @abstractmethod
    async def complete(self, request: InferenceRequest) -> ChatCompletionResponse:
        """Return a complete chat completion response."""

    @abstractmethod
    def stream(self, request: InferenceRequest) -> AsyncIterator[ChatCompletionChunk]:
        """Yield chat completion chunks."""
