from collections.abc import AsyncIterator
from time import time
from typing import Any

import openai
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.llm.base import BaseChatModel
from app.core.llm.errors import LLMModelError
from app.core.llm.schemas import (
    AssistantMessage,
    ChatCompletionChunk,
    ChatCompletionResponse,
    Choice,
    DeltaContent,
    FunctionCall,
    InferenceRequest,
    StreamChoice,
    ToolCall,
    Usage,
)
from app.core.logging import get_app_logger
from app.core.request_context import get_correlation_headers

logger = get_app_logger()


class OpenAIModelAdapter(BaseChatModel):
    """Shared OpenAI SDK setup and error handling for async model adapters."""

    unsupported_payload_fields: frozenset[str] = frozenset()

    def __init__(
        self,
        *,
        provider_id: str,
        provider_name: str,
        provider_type: str,
        model_id: str,
        model_name: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        super().__init__(
            provider_id=provider_id,
            provider_name=provider_name,
            provider_type=provider_type,
            model_id=model_id,
            model_name=model_name,
        )
        if client is not None:
            self.client = client
            return

        settings = get_settings()
        if not settings.llm_api_key:
            raise LLMModelError(
                "LLM_API_KEY is not configured",
                error_code="CONFIGURATION_ERROR",
                status_code=503,
            )

        client_options: dict[str, Any] = {"api_key": settings.llm_api_key}
        if settings.llm_base_url:
            client_options["base_url"] = settings.llm_base_url

        self.client = AsyncOpenAI(**client_options)

    def _filter_optional_fields(self, fields: dict[str, Any]) -> dict[str, Any]:
        for field in self.unsupported_payload_fields:
            fields.pop(field, None)
        return {field: value for field, value in fields.items() if value is not None}

    def _get_extra_text(self, value: Any, field_names: tuple[str, ...]) -> str | None:
        for field_name in field_names:
            field_value = getattr(value, field_name, None)
            if isinstance(field_value, str) and field_value.strip():
                return field_value

        if hasattr(value, "model_dump"):
            dumped = value.model_dump()
            for field_name in field_names:
                field_value = dumped.get(field_name)
                if isinstance(field_value, str) and field_value.strip():
                    return field_value

        model_extra = getattr(value, "model_extra", None)
        if isinstance(model_extra, dict):
            for field_name in field_names:
                field_value = model_extra.get(field_name)
                if isinstance(field_value, str) and field_value.strip():
                    return field_value

        return None

    def _get_reasoning(self, value: Any) -> str | None:
        return self._get_extra_text(
            value,
            (
                "reasoning",
                "reasoning_content",
                "reasoningContent",
                "thinking",
            ),
        )

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

        raise LLMModelError(
            str(exc),
            error_code=code,
            status_code=status_code,
            raw=raw,
        ) from exc

    def _raise_model_error(self, exc: Exception, *, model: str, streaming: bool) -> None:
        prefix = "llm_stream" if streaming else "llm"
        if isinstance(exc, openai.RateLimitError):
            logger.warning(f"{prefix}_rate_limited", extra={"model": model, "error": str(exc)})
            raise LLMModelError(str(exc), error_code="RATE_LIMITED", status_code=429) from exc
        if isinstance(exc, openai.AuthenticationError):
            logger.error(f"{prefix}_auth_error", extra={"model": model, "error": str(exc)})
            raise LLMModelError(
                str(exc), error_code="UPSTREAM_AUTH_ERROR", status_code=502
            ) from exc
        if isinstance(exc, openai.APIConnectionError):
            logger.error(f"{prefix}_connection_error", extra={"model": model, "error": str(exc)})
            raise LLMModelError(
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
        raise LLMModelError(str(exc), error_code="UPSTREAM_ERROR", status_code=502) from exc


class OpenAIChatCompletionsModel(OpenAIModelAdapter):
    """OpenAI SDK adapter for models that use Chat Completions."""

    def _build_payload(self, request: InferenceRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.resolve_model(request.model),
            "messages": [message.model_dump(exclude_none=True) for message in request.messages],
            "stream": stream,
            "extra_headers": get_correlation_headers() or None,
        }

        payload.update(
            self._filter_optional_fields(
                {
                    "temperature": request.temperature,
                    "max_completion_tokens": request.max_tokens,
                    "top_p": request.top_p,
                    "frequency_penalty": request.frequency_penalty,
                    "presence_penalty": request.presence_penalty,
                    "stop": request.stop,
                    "tool_choice": request.tool_choice,
                }
            )
        )

        if request.tools:
            payload["tools"] = [tool.model_dump() for tool in request.tools]
        if stream and request.stream_options:
            payload["stream_options"] = {
                "include_usage": request.stream_options.include_usage,
            }

        return payload

    async def complete(self, request: InferenceRequest) -> ChatCompletionResponse:
        payload = self._build_payload(request, stream=False)
        try:
            response = await self.client.chat.completions.create(**payload)
        except Exception as exc:
            self._raise_model_error(exc, model=payload["model"], streaming=False)

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
                        reasoning=self._get_reasoning(choice.message),
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

    def stream(self, request: InferenceRequest) -> AsyncIterator[ChatCompletionChunk]:
        payload = self._build_payload(request, stream=True)

        async def _iterator() -> AsyncIterator[ChatCompletionChunk]:
            try:
                response_stream = await self.client.chat.completions.create(**payload)
            except Exception as exc:
                self._raise_model_error(exc, model=payload["model"], streaming=True)

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
                                reasoning=self._get_reasoning(choice.delta),
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

                yield ChatCompletionChunk(
                    id=chunk.id,
                    created=chunk.created,
                    model=chunk.model,
                    choices=stream_choices,
                    usage=usage,
                )

        return _iterator()


class OpenAIResponsesModel(OpenAIModelAdapter):
    """OpenAI SDK adapter for Responses API models."""

    def _build_payload(self, request: InferenceRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.resolve_model(request.model),
            "input": self._build_input(request),
            "stream": stream,
            "extra_headers": get_correlation_headers() or None,
        }

        payload.update(
            self._filter_optional_fields(
                {
                    "temperature": request.temperature,
                    "max_output_tokens": request.max_tokens,
                    "top_p": request.top_p,
                    "tool_choice": self._build_tool_choice(request.tool_choice),
                }
            )
        )

        if request.tools:
            payload["tools"] = [self._build_tool(tool) for tool in request.tools]
        if stream and request.stream_options:
            payload["stream_options"] = {
                "include_usage": request.stream_options.include_usage,
            }

        return payload

    def _build_input(self, request: InferenceRequest) -> list[dict[str, Any]]:
        input_items: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "tool":
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": message.content or "",
                    }
                )
                continue

            input_items.append(
                {
                    "role": message.role,
                    "content": self._build_message_content(message.content),
                }
            )
        return input_items

    def _build_message_content(self, content: Any) -> str | list[dict[str, Any]]:
        if not isinstance(content, list):
            return content or ""

        content_parts: list[dict[str, Any]] = []
        for part in content:
            if part.type == "text":
                content_parts.append({"type": "input_text", "text": part.text})
            elif part.type == "image_url":
                content_parts.append(
                    {
                        "type": "input_image",
                        "image_url": part.image_url.url,
                        "detail": "auto",
                    }
                )
        return content_parts

    def _build_tool(self, tool: Any) -> dict[str, Any]:
        return {
            "type": "function",
            "name": tool.function.name,
            "description": tool.function.description,
            "parameters": tool.function.parameters,
            "strict": False,
        }

    def _build_tool_choice(self, tool_choice: str | dict[str, Any] | None) -> Any:
        if not isinstance(tool_choice, dict):
            return tool_choice

        return {
            "type": "function",
            "name": tool_choice["function"]["name"],
        }

    async def complete(self, request: InferenceRequest) -> ChatCompletionResponse:
        payload = self._build_payload(request, stream=False)
        try:
            response = await self.client.responses.create(**payload)
        except Exception as exc:
            self._raise_model_error(exc, model=payload["model"], streaming=False)

        error = getattr(response, "error", None)
        if error is not None:
            raise LLMModelError(
                getattr(error, "message", str(error)),
                error_code=getattr(error, "code", "UPSTREAM_ERROR"),
                status_code=502,
                raw=error,
            )

        return self._response_to_chat_completion(response)

    def _response_to_chat_completion(self, response: Any) -> ChatCompletionResponse:
        return ChatCompletionResponse(
            id=response.id,
            created=int(response.created_at),
            model=response.model,
            choices=[
                Choice(
                    message=AssistantMessage(content=self._get_output_text(response)),
                    finish_reason=self._get_finish_reason(response),
                )
            ],
            usage=self._get_usage(response),
        )

    def stream(self, request: InferenceRequest) -> AsyncIterator[ChatCompletionChunk]:
        payload = self._build_payload(request, stream=True)

        async def _iterator() -> AsyncIterator[ChatCompletionChunk]:
            try:
                response_stream = await self.client.responses.create(**payload)
            except Exception as exc:
                self._raise_model_error(exc, model=payload["model"], streaming=True)

            response_id = f"resp_{int(time())}"
            created = int(time())
            async for event in response_stream:
                event_type = getattr(event, "type", None)
                if event_type == "response.created":
                    response = getattr(event, "response", None)
                    response_id = getattr(response, "id", response_id)
                    created = int(getattr(response, "created_at", created))
                    continue

                if event_type == "response.output_text.delta":
                    yield ChatCompletionChunk(
                        id=response_id,
                        created=created,
                        model=payload["model"],
                        choices=[
                            StreamChoice(
                                delta=DeltaContent(
                                    role="assistant",
                                    content=getattr(event, "delta", ""),
                                ),
                                finish_reason=None,
                            )
                        ],
                    )
                    continue

                if event_type == "response.completed":
                    response = getattr(event, "response", None)
                    if response is not None:
                        yield ChatCompletionChunk(
                            id=getattr(response, "id", response_id),
                            created=int(getattr(response, "created_at", created)),
                            model=getattr(response, "model", payload["model"]),
                            choices=[
                                StreamChoice(
                                    delta=DeltaContent(),
                                    finish_reason=self._get_finish_reason(response),
                                )
                            ],
                            usage=self._get_usage(response),
                        )
                    continue

                if event_type in {"response.failed", "response.incomplete"}:
                    response = getattr(event, "response", None)
                    error = getattr(response, "error", None)
                    raise LLMModelError(
                        getattr(error, "message", "Responses API request failed"),
                        error_code=getattr(error, "code", "UPSTREAM_ERROR"),
                        status_code=502,
                        raw=error,
                    )

        return _iterator()

    def _get_output_text(self, response: Any) -> str | None:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            return output_text

        text_parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if isinstance(text, str):
                    text_parts.append(text)
        return "".join(text_parts) or None

    def _get_finish_reason(self, response: Any) -> str | None:
        status = getattr(response, "status", None)
        if status == "completed":
            return "stop"
        return status

    def _get_usage(self, response: Any) -> Usage | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        return Usage(
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )


class GPT52ChatModel(OpenAIChatCompletionsModel):
    unsupported_payload_fields = frozenset({"temperature"})


class GPT53CodexModel(OpenAIResponsesModel):
    unsupported_payload_fields = frozenset({"temperature", "top_p"})


class GPT52Model(OpenAIChatCompletionsModel):
    pass
