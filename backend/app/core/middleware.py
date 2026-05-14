import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_app_logger
from app.core.request_context import (
    build_trace_context,
    request_id_ctx_var,
    trace_id_ctx_var,
    traceparent_ctx_var,
)

logger = get_app_logger()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        trace_context = build_trace_context(request.headers.get("traceparent"))

        request_id_token = request_id_ctx_var.set(request_id)
        trace_id_token = trace_id_ctx_var.set(trace_context.trace_id)
        traceparent_token = traceparent_ctx_var.set(trace_context.traceparent)
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
            process_time_ms = (time.perf_counter() - started_at) * 1000
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
            logger.info(
                "%s %s -> %s %.2fms",
                request.method,
                request.url.path,
                response.status_code,
                process_time_ms,
            )
            return response
        finally:
            traceparent_ctx_var.reset(traceparent_token)
            trace_id_ctx_var.reset(trace_id_token)
            request_id_ctx_var.reset(request_id_token)
