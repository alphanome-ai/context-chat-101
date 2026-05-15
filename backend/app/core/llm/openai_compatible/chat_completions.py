from collections.abc import AsyncIterator
from typing import Any

from app.core.llm.openai_compatible.base import OpenAIModelAdapter
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
from app.core.request_context import get_correlation_headers


def _usage_to_schema(usage: Any | None) -> Usage | None:
    if not usage:
        return None
    return Usage(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )


def _message_tool_calls_to_schema(tool_calls: Any | None) -> list[ToolCall] | None:
    if not tool_calls:
        return None
    return [
        ToolCall(
            id=tool_call.id,
            type="function",
            function=FunctionCall(
                name=tool_call.function.name,
                arguments=tool_call.function.arguments,
            ),
        )
        for tool_call in tool_calls
    ]


def _delta_tool_calls_to_payload(tool_calls: Any | None) -> list[dict[str, Any]] | None:
    if not tool_calls:
        return None

    delta_tool_calls: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        function = None
        if tool_call.function:
            function = {
                key: value
                for key, value in {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                }.items()
                if value is not None
            }

        delta_tool_calls.append(
            {
                key: value
                for key, value in {
                    "index": tool_call.index,
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": function,
                }.items()
                if value is not None
            }
        )

    return delta_tool_calls


class OpenAIChatCompletionsModel(OpenAIModelAdapter):
    """OpenAI-compatible adapter for models that use Chat Completions."""

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

        choices = [
            Choice(
                index=choice.index,
                message=AssistantMessage(
                    content=choice.message.content,
                    reasoning=self._get_reasoning(choice.message),
                    tool_calls=_message_tool_calls_to_schema(choice.message.tool_calls),
                ),
                finish_reason=choice.finish_reason,
            )
            for choice in response.choices
        ]

        return ChatCompletionResponse(
            id=response.id,
            created=response.created,
            model=response.model,
            choices=choices,
            usage=_usage_to_schema(response.usage),
        )

    def stream(self, request: InferenceRequest) -> AsyncIterator[ChatCompletionChunk]:
        payload = self._build_payload(request, stream=True)

        async def _iterator() -> AsyncIterator[ChatCompletionChunk]:
            try:
                response_stream = await self.client.chat.completions.create(**payload)
            except Exception as exc:
                self._raise_model_error(exc, model=payload["model"], streaming=True)

            async for chunk in response_stream:
                stream_choices = [
                    StreamChoice(
                        index=choice.index,
                        delta=DeltaContent(
                            role=choice.delta.role,
                            content=choice.delta.content,
                            reasoning=self._get_reasoning(choice.delta),
                            tool_calls=_delta_tool_calls_to_payload(choice.delta.tool_calls),
                        ),
                        finish_reason=choice.finish_reason,
                    )
                    for choice in chunk.choices
                ]

                yield ChatCompletionChunk(
                    id=chunk.id,
                    created=chunk.created,
                    model=chunk.model,
                    choices=stream_choices,
                    usage=_usage_to_schema(chunk.usage),
                )

        return _iterator()
