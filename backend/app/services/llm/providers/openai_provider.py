from collections.abc import AsyncIterator
from typing import Any

import openai
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_app_logger
from app.core.request_context import get_correlation_headers
from app.services.llm.providers.base import LLMProviderError
from app.services.llm.schemas import (
    AssistantMessage,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    DeltaContent,
    FunctionCall,
    StreamChoice,
    ToolCall,
    Usage,
)

logger = get_app_logger()


class OpenAICompatibleProvider:
    """OpenAI SDK adapter for OpenAI-compatible chat completion APIs."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.llm_api_key:
            raise LLMProviderError(
                "LLM_API_KEY is not configured",
                error_code="CONFIGURATION_ERROR",
                status_code=503,
            )

        client_options: dict[str, Any] = {"api_key": settings.llm_api_key}
        if settings.llm_base_url:
            client_options["base_url"] = settings.llm_base_url

        self.client = AsyncOpenAI(**client_options)
        self.default_model = settings.llm_default_model
        self.available_models = set(settings.llm_available_models)

    def _resolve_model(self, requested_model: str) -> str:
        model = self.default_model if requested_model == "default" else requested_model
        if self.available_models and model not in self.available_models:
            raise LLMProviderError(
                f"Unsupported model: {requested_model}",
                error_code="UNSUPPORTED_MODEL",
                status_code=400,
            )
        return model

    def _build_payload(self, request: ChatCompletionRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._resolve_model(request.model),
            "messages": [message.model_dump(exclude_none=True) for message in request.messages],
            "stream": stream,
            "extra_headers": get_correlation_headers() or None,
        }

        optional_fields = {
            "temperature": request.temperature,
            "max_completion_tokens": request.max_tokens,
            "top_p": request.top_p,
            "frequency_penalty": request.frequency_penalty,
            "presence_penalty": request.presence_penalty,
            "stop": request.stop,
            "tool_choice": request.tool_choice,
        }
        payload.update(
            {field: value for field, value in optional_fields.items() if value is not None}
        )

        if request.tools:
            payload["tools"] = [tool.model_dump() for tool in request.tools]
        if stream and request.stream_options:
            payload["stream_options"] = {
                "include_usage": request.stream_options.include_usage,
            }

        return payload

    def _raise_api_status_error(self, exc: openai.APIStatusError) -> None:
        raw = getattr(exc, "body", None)
        if exc.status_code == 400:
            code, status_code = "INVALID_REQUEST", 400
        elif exc.status_code == 404:
            code, status_code = "NOT_FOUND", 404
        elif exc.status_code == 408:
            code, status_code = "TIMEOUT", 408
        elif exc.status_code == 429:
            code, status_code = "RATE_LIMITED", 429
        elif exc.status_code == 503:
            code, status_code = "SERVICE_UNAVAILABLE", 503
        else:
            code, status_code = "UPSTREAM_ERROR", 502

        raise LLMProviderError(
            str(exc),
            error_code=code,
            status_code=status_code,
            raw=raw,
        ) from exc

    def _raise_provider_error(self, exc: Exception, *, model: str, streaming: bool) -> None:
        prefix = "llm_stream" if streaming else "llm"
        if isinstance(exc, openai.RateLimitError):
            logger.warning(f"{prefix}_rate_limited", extra={"model": model, "error": str(exc)})
            raise LLMProviderError(
                str(exc), error_code="RATE_LIMITED", status_code=429
            ) from exc
        if isinstance(exc, openai.AuthenticationError):
            logger.error(f"{prefix}_auth_error", extra={"model": model, "error": str(exc)})
            raise LLMProviderError(
                str(exc), error_code="UPSTREAM_AUTH_ERROR", status_code=502
            ) from exc
        if isinstance(exc, openai.APIConnectionError):
            logger.error(f"{prefix}_connection_error", extra={"model": model, "error": str(exc)})
            raise LLMProviderError(
                f"Failed to connect to upstream LLM: {exc}",
                error_code="SERVICE_UNAVAILABLE",
                status_code=503,
            ) from exc
        if isinstance(exc, openai.APIStatusError):
            logger.warning(
                f"{prefix}_api_status_error",
                extra={
                    "model": model,
                    "status_code": exc.status_code,
                    "error": str(exc),
                },
            )
            self._raise_api_status_error(exc)

        logger.exception(f"{prefix}_unexpected_error", extra={"model": model})
        raise LLMProviderError(str(exc), error_code="UPSTREAM_ERROR", status_code=502) from exc

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        payload = self._build_payload(request, stream=False)
        try:
            response = await self.client.chat.completions.create(**payload)
        except Exception as exc:
            self._raise_provider_error(exc, model=payload["model"], streaming=False)

        choices: list[Choice] = []
        for choice in response.choices:
            tool_calls = None
            if choice.message.tool_calls:
                tool_calls = [
                    ToolCall(
                        id=tool_call.id,
                        type="function",
                        function=FunctionCall(
                            name=tool_call.function.name,
                            arguments=tool_call.function.arguments,
                        ),
                    )
                    for tool_call in choice.message.tool_calls
                ]

            choices.append(
                Choice(
                    index=choice.index,
                    message=AssistantMessage(
                        content=choice.message.content,
                        tool_calls=tool_calls,
                    ),
                    finish_reason=choice.finish_reason,
                )
            )

        usage = None
        if response.usage:
            usage = Usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

        return ChatCompletionResponse(
            id=response.id,
            created=response.created,
            model=response.model,
            choices=choices,
            usage=usage,
        )

    def stream(self, request: ChatCompletionRequest) -> AsyncIterator[bytes]:
        payload = self._build_payload(request, stream=True)

        async def _iterator() -> AsyncIterator[bytes]:
            try:
                response_stream = await self.client.chat.completions.create(**payload)
            except Exception as exc:
                self._raise_provider_error(exc, model=payload["model"], streaming=True)

            async for chunk in response_stream:
                stream_choices: list[StreamChoice] = []
                for choice in chunk.choices:
                    delta_tool_calls = None
                    if choice.delta.tool_calls:
                        delta_tool_calls = [
                            {
                                key: value
                                for key, value in {
                                    "index": tool_call.index,
                                    "id": tool_call.id,
                                    "type": tool_call.type,
                                    "function": {
                                        inner_key: inner_value
                                        for inner_key, inner_value in {
                                            "name": (
                                                tool_call.function.name
                                                if tool_call.function
                                                else None
                                            ),
                                            "arguments": (
                                                tool_call.function.arguments
                                                if tool_call.function
                                                else None
                                            ),
                                        }.items()
                                        if inner_value is not None
                                    }
                                    if tool_call.function
                                    else None,
                                }.items()
                                if value is not None
                            }
                            for tool_call in choice.delta.tool_calls
                        ]

                    stream_choices.append(
                        StreamChoice(
                            index=choice.index,
                            delta=DeltaContent(
                                role=choice.delta.role,
                                content=choice.delta.content,
                                tool_calls=delta_tool_calls,
                            ),
                            finish_reason=choice.finish_reason,
                        )
                    )

                usage = None
                if chunk.usage:
                    usage = Usage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                    )

                sse_chunk = ChatCompletionChunk(
                    id=chunk.id,
                    created=chunk.created,
                    model=chunk.model,
                    choices=stream_choices,
                    usage=usage,
                )
                yield f"data: {sse_chunk.model_dump_json(exclude_none=True)}\n\n".encode()

            yield b"data: [DONE]\n\n"

        return _iterator()
