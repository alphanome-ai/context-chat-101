from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.services.llm.schemas import ChatCompletionRequest, ChatCompletionResponse


class LLMProviderError(Exception):
    """Structured error raised by an upstream LLM provider."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "UPSTREAM_ERROR",
        status_code: int = 502,
        raw: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.raw = raw


class LLMProvider(Protocol):
    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Return a complete chat completion response."""
        ...

    def stream(self, request: ChatCompletionRequest) -> AsyncIterator[bytes]:
        """Yield OpenAI-compatible SSE chat completion chunks."""
        ...
