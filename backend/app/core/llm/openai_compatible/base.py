from typing import Any, NoReturn

import openai
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.llm.base import BaseChatModel
from app.core.llm.errors import LLMModelError
from app.core.logging import get_app_logger

logger = get_app_logger()


class OpenAIModelAdapter(BaseChatModel):
    """Shared OpenAI-compatible SDK setup and error handling."""

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

    def _raise_api_status_error(self, exc: openai.APIStatusError) -> NoReturn:
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

    def _raise_model_error(self, exc: Exception, *, model: str, streaming: bool) -> NoReturn:
        prefix = "llm_stream" if streaming else "llm"
        if isinstance(exc, openai.RateLimitError):
            logger.bind(model=model, error=str(exc)).warning(f"{prefix}_rate_limited")
            raise LLMModelError(str(exc), error_code="RATE_LIMITED", status_code=429) from exc
        if isinstance(exc, openai.AuthenticationError):
            logger.bind(model=model, error=str(exc)).error(f"{prefix}_auth_error")
            raise LLMModelError(
                str(exc), error_code="UPSTREAM_AUTH_ERROR", status_code=502
            ) from exc
        if isinstance(exc, openai.APIConnectionError):
            logger.bind(model=model, error=str(exc)).error(f"{prefix}_connection_error")
            raise LLMModelError(
                f"Failed to connect to upstream LLM: {exc}",
                error_code="SERVICE_UNAVAILABLE",
                status_code=503,
            ) from exc
        if isinstance(exc, openai.APIStatusError):
            logger.bind(
                model=model,
                status_code=exc.status_code,
                error=str(exc),
            ).warning(f"{prefix}_api_status_error")
            self._raise_api_status_error(exc)

        logger.bind(model=model).exception(f"{prefix}_unexpected_error")
        raise LLMModelError(str(exc), error_code="UPSTREAM_ERROR", status_code=502) from exc
