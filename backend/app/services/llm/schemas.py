from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LLMModel(BaseModel):
    id: str
    name: str | None = None
    is_default: bool = Field(False, alias="isDefault")

    model_config = ConfigDict(populate_by_name=True)


class LLMProviderInfo(BaseModel):
    id: str
    name: str
    type: str
    models: list[LLMModel]


class ProvidersResponse(BaseModel):
    providers: list[LLMProviderInfo]


class FunctionDefinition(BaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, Any] | None = None

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        if value.get("type") != "object":
            raise ValueError('parameters must be a JSON Schema object with type "object"')
        if (properties := value.get("properties")) is not None and not isinstance(
            properties, dict
        ):
            raise ValueError("parameters.properties must be an object when provided")
        required = value.get("required")
        if required is not None and (
            not isinstance(required, list) or any(not isinstance(item, str) for item in required)
        ):
            raise ValueError("parameters.required must be a list of strings when provided")
        return value


class ToolDefinition(BaseModel):
    type: Literal["function"] = "function"
    function: FunctionDefinition


class FunctionCall(BaseModel):
    name: str
    arguments: str


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


class ImageUrl(BaseModel):
    url: str


class ContentPartText(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ContentPartImage(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: ImageUrl


ContentPart = ContentPartText | ContentPartImage


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentPart] | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    @model_validator(mode="after")
    def validate_role_fields(self) -> "ChatMessage":
        if self.role != "assistant" and self.tool_calls is not None:
            raise ValueError("tool_calls are only allowed on assistant messages")
        if self.role != "tool" and self.tool_call_id is not None:
            raise ValueError("tool_call_id is only allowed on tool messages")
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("tool messages require tool_call_id")
        return self


class StreamOptions(BaseModel):
    include_usage: bool = False


class ChatCompletionRequest(BaseModel):
    model: str = "default"
    messages: list[ChatMessage]
    stream: bool = False
    stream_options: StreamOptions | None = None
    temperature: float | None = None
    max_tokens: int | None = Field(None, gt=0)
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: str | list[str] | None = None
    tools: list[ToolDefinition] | None = None
    tool_choice: str | dict[str, Any] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model": "default",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
                "temperature": 0.2,
                "max_tokens": 256,
            }
        }
    )

    @field_validator("tool_choice")
    @classmethod
    def validate_tool_choice(
        cls,
        value: str | dict[str, Any] | None,
    ) -> str | dict[str, Any] | None:
        if value is None:
            return value
        if isinstance(value, str):
            if value not in {"none", "auto", "required"}:
                raise ValueError(
                    'tool_choice must be "none", "auto", "required", or an object naming a tool'
                )
            return value
        if value.get("type") != "function":
            raise ValueError('tool_choice object must include type "function"')
        function = value.get("function")
        if not isinstance(function, dict) or not function.get("name"):
            raise ValueError("tool_choice.function.name is required")
        return value

    @model_validator(mode="after")
    def validate_tools_configuration(self) -> "ChatCompletionRequest":
        if self.tool_choice is None:
            return self
        if not self.tools:
            raise ValueError("tool_choice requires tools to be provided")
        if isinstance(self.tool_choice, dict):
            requested_name = self.tool_choice["function"]["name"]
            available_names = {tool.function.name for tool in self.tools}
            if requested_name not in available_names:
                raise ValueError("tool_choice.function.name must match one of the provided tools")
        return self


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class Choice(BaseModel):
    index: int = 0
    message: AssistantMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage | None = None


class DeltaContent(BaseModel):
    role: str | None = None
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: DeltaContent
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[StreamChoice]
    usage: Usage | None = None


class ErrorMetadata(BaseModel):
    raw: Any | None = None


class ErrorDetail(BaseModel):
    message: str
    code: str | None = None
    metadata: ErrorMetadata | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
