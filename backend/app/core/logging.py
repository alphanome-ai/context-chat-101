import logging
import sys
from datetime import UTC, datetime
from logging.config import dictConfig

from app.core.config import get_settings
from app.core.request_context import request_id_ctx_var, trace_id_ctx_var

APP_LOGGER_NAME = "context_chat_api"
_LOGGING_CONFIGURED = False


def _format_utc_timestamp(created: float) -> str:
    return (
        datetime.fromtimestamp(created, tz=UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_ctx_var.get()
        if not hasattr(record, "trace_id"):
            record.trace_id = trace_id_ctx_var.get()
        return True


class AppFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return _format_utc_timestamp(record.created)


def setup_logging() -> None:
    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED:
        return

    settings = get_settings()
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_context": {
                    "()": "app.core.logging.RequestContextFilter",
                }
            },
            "formatters": {
                "default": {
                    "()": "app.core.logging.AppFormatter",
                    "format": (
                        "%(asctime)s | %(levelname)s | request_id=%(request_id)s "
                        "| trace_id=%(trace_id)s | %(name)s | %(message)s"
                    ),
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "default",
                    "filters": ["request_context"],
                }
            },
            "root": {"handlers": ["default"], "level": "WARNING"},
            "loggers": {
                APP_LOGGER_NAME: {
                    "handlers": ["default"],
                    "level": settings.log_level,
                    "propagate": False,
                },
                "uvicorn.error": {"level": "INFO"},
                "uvicorn.access": {"handlers": [], "propagate": False},
            },
        }
    )
    _LOGGING_CONFIGURED = True


def get_app_logger() -> logging.Logger:
    return logging.getLogger(APP_LOGGER_NAME)

