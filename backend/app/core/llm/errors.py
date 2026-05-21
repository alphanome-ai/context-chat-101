from typing import Any


class LLMModelError(Exception):
    """Structured error raised by the core LLM model layer."""

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
