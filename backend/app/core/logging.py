import logging
import sys
from datetime import UTC, datetime
from logging.config import dictConfig

from app.core.config import get_settings

APP_LOGGER_NAME = "context_chat_api"
_LOGGING_CONFIGURED = False


def _format_utc_timestamp(created: float) -> str:
    return (
        datetime.fromtimestamp(created, tz=UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


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
            "formatters": {
                "default": {
                    "()": "app.core.logging.AppFormatter",
                    "format": "%(asctime)s | %(levelname)s | %(message)s",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "default",
                }
            },
            "root": {"handlers": [], "level": "CRITICAL"},
            "loggers": {
                APP_LOGGER_NAME: {
                    "handlers": ["default"],
                    "level": settings.log_level,
                    "propagate": False,
                },
                "uvicorn": {"handlers": [], "level": "CRITICAL", "propagate": False},
                "uvicorn.error": {"handlers": [], "level": "CRITICAL", "propagate": False},
                "uvicorn.access": {"handlers": [], "level": "CRITICAL", "propagate": False},
                "fastapi": {"handlers": [], "level": "CRITICAL", "propagate": False},
                "starlette": {"handlers": [], "level": "CRITICAL", "propagate": False},
                "sqlalchemy": {"handlers": [], "level": "CRITICAL", "propagate": False},
            },
        }
    )
    logging.getLogger(APP_LOGGER_NAME).disabled = False
    _LOGGING_CONFIGURED = True


def get_app_logger() -> logging.Logger:
    return logging.getLogger(APP_LOGGER_NAME)
