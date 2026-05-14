import secrets
from contextvars import ContextVar
from dataclasses import dataclass

REQUEST_CONTEXT_DEFAULT = "-"
_TRACEPARENT_VERSION = "00"
_TRACEPARENT_FLAGS = "01"

request_id_ctx_var: ContextVar[str] = ContextVar(
    "request_id", default=REQUEST_CONTEXT_DEFAULT
)
trace_id_ctx_var: ContextVar[str] = ContextVar("trace_id", default=REQUEST_CONTEXT_DEFAULT)
traceparent_ctx_var: ContextVar[str] = ContextVar(
    "traceparent", default=REQUEST_CONTEXT_DEFAULT
)


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str = REQUEST_CONTEXT_DEFAULT
    trace_flags: str = _TRACEPARENT_FLAGS

    @property
    def traceparent(self) -> str:
        return build_traceparent(self.trace_id, self.span_id, self.trace_flags)


def _is_valid_hex(value: str, expected_length: int) -> bool:
    return len(value) == expected_length and all(
        char in "0123456789abcdef" for char in value
    )


def _parse_traceparent(traceparent: str | None) -> tuple[str, str, str] | None:
    if not traceparent:
        return None

    parts = traceparent.strip().lower().split("-")
    if len(parts) != 4:
        return None

    version, trace_id, parent_span_id, trace_flags = parts
    if version != _TRACEPARENT_VERSION:
        return None
    if not _is_valid_hex(trace_id, 32) or trace_id == "0" * 32:
        return None
    if not _is_valid_hex(parent_span_id, 16) or parent_span_id == "0" * 16:
        return None
    if not _is_valid_hex(trace_flags, 2):
        return None
    return trace_id, parent_span_id, trace_flags


def build_traceparent(
    trace_id: str, span_id: str, trace_flags: str = _TRACEPARENT_FLAGS
) -> str:
    return f"{_TRACEPARENT_VERSION}-{trace_id}-{span_id}-{trace_flags}"


def build_trace_context(traceparent: str | None) -> TraceContext:
    parsed = _parse_traceparent(traceparent)
    if parsed:
        trace_id, parent_span_id, trace_flags = parsed
    else:
        trace_id = secrets.token_hex(16)
        parent_span_id = REQUEST_CONTEXT_DEFAULT
        trace_flags = _TRACEPARENT_FLAGS

    return TraceContext(
        trace_id=trace_id,
        span_id=secrets.token_hex(8),
        parent_span_id=parent_span_id,
        trace_flags=trace_flags,
    )


def get_correlation_headers() -> dict[str, str]:
    headers: dict[str, str] = {}

    request_id = request_id_ctx_var.get()
    if request_id != REQUEST_CONTEXT_DEFAULT:
        headers["X-Request-ID"] = request_id

    traceparent = traceparent_ctx_var.get()
    if traceparent != REQUEST_CONTEXT_DEFAULT:
        headers["traceparent"] = traceparent

    return headers

