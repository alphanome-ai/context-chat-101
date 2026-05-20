from collections.abc import AsyncIterator
from time import time
from typing import Any

from app.core.llm.errors import LLMModelError
from app.core.llm.openai_compatible.base import OpenAIModelAdapter
from app.core.llm.schemas import (
    AssistantMessage,
    ChatCompletionChunk,
    ChatCompletionResponse,
    Choice,
    DeltaContent,
    InferenceRequest,
    StreamChoice,
    Usage,
)
from app.core.request_context import get_correlation_headers


def _output_text(response: Any) -> str | None:
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


def _item_type(item: Any) -> str | None:
    if isinstance(item, dict):
        value = item.get("type")
    else:
        value = getattr(item, "type", None)
    return value if isinstance(value, str) else None


def _field_value(value: Any, field_name: str) -> Any:
    if isinstance(value, dict):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _reasoning_summary(response: Any) -> str | None:
    text_parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        if _item_type(item) != "reasoning":
            continue

        for summary_part in _field_value(item, "summary") or []:
            text = _field_value(summary_part, "text")
            if isinstance(text, str):
                text_parts.append(text)

    return "\n\n".join(text_parts) or None


def _finish_reason(response: Any) -> str | None:
    status = getattr(response, "status", None)
    if status == "completed":
        return "stop"
    return status


def _usage_to_schema(response: Any) -> Usage | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return Usage(
        prompt_tokens=usage.input_tokens,
        completion_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )


class OpenAIResponsesModel(OpenAIModelAdapter):
    """OpenAI-compatible adapter for models that use the Responses API."""

    reasoning_effort: str | None = None
    reasoning_summary: str | None = None

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
        reasoning = self._build_reasoning()
        if reasoning:
            payload["reasoning"] = reasoning

        return payload

    def _build_reasoning(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "effort": self.reasoning_effort,
                "summary": self.reasoning_summary,
            }.items()
            if value is not None
        }

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
                    message=AssistantMessage(
                        content=_output_text(response),
                        reasoning=_reasoning_summary(response),
                    ),
                    finish_reason=_finish_reason(response),
                )
            ],
            usage=_usage_to_schema(response),
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
            streamed_reasoning = False
            streamed_summary_indexes: set[int] = set()
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

                if event_type == "response.reasoning_summary_text.delta":
                    streamed_reasoning = True
                    streamed_summary_indexes.add(getattr(event, "summary_index", 0))
                    yield ChatCompletionChunk(
                        id=response_id,
                        created=created,
                        model=payload["model"],
                        choices=[
                            StreamChoice(
                                delta=DeltaContent(
                                    role="assistant",
                                    reasoning=getattr(event, "delta", ""),
                                ),
                                finish_reason=None,
                            )
                        ],
                    )
                    continue

                if event_type == "response.reasoning_summary_text.done":
                    summary_index = getattr(event, "summary_index", 0)
                    if summary_index in streamed_summary_indexes:
                        continue

                    streamed_reasoning = True
                    streamed_summary_indexes.add(summary_index)
                    yield ChatCompletionChunk(
                        id=response_id,
                        created=created,
                        model=payload["model"],
                        choices=[
                            StreamChoice(
                                delta=DeltaContent(
                                    role="assistant",
                                    reasoning=getattr(event, "text", ""),
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
                                    delta=DeltaContent(
                                        reasoning=(
                                            None
                                            if streamed_reasoning
                                            else _reasoning_summary(response)
                                        )
                                    ),
                                    finish_reason=_finish_reason(response),
                                )
                            ],
                            usage=_usage_to_schema(response),
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
