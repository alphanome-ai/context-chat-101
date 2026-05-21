from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.llm.schemas import ChatMessage, InferenceRequest, StreamOptions


class ChatRunRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    model: str = "default"
    stream: bool = False
    stream_options: StreamOptions | None = None
    temperature: float | None = None
    max_tokens: int | None = Field(None, gt=0)
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: str | list[str] | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message cannot be empty")
        return stripped

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            UUID(value)
        except ValueError as exc:
            raise ValueError("session_id must be a UUID") from exc
        return value

    def to_inference_request(self, messages: list[ChatMessage]) -> InferenceRequest:
        return InferenceRequest(
            model=self.model,
            messages=messages,
            stream=self.stream,
            stream_options=self.stream_options,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            stop=self.stop,
        )
