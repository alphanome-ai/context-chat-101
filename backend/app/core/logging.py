from __future__ import annotations

import logging
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger as loguru_logger

from app.core.config import get_settings

if TYPE_CHECKING:
    from loguru import Record

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SUPPRESSED_STDLIB_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "fastapi",
    "starlette",
    "sqlalchemy",
)
_LOGGING_CONFIGURED = False


def _format_utc_timestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _format_extra(extra: dict[str, Any]) -> str:
    internal_keys = {"serialized_extra", "source_location"}
    visible_extra = {key: value for key, value in extra.items() if key not in internal_keys}
    if not visible_extra:
        return ""
    return " | " + " ".join(f"{key}={value!r}" for key, value in visible_extra.items())


def _source_location(record: Record) -> str:
    source_path = record["file"].path
    if source_path.startswith("<"):
        relative_path = source_path
    else:
        try:
            relative_path = str(Path(source_path).resolve().relative_to(BACKEND_ROOT))
        except ValueError:
            relative_path = str(source_path)
    return f"{relative_path}:{record['line']}"


def _format_record(record: Record) -> str:
    record["extra"]["serialized_extra"] = _format_extra(record["extra"])
    record["extra"]["source_location"] = _source_location(record)
    timestamp = _format_utc_timestamp(record["time"])
    return (
        f"<level>{timestamp} | "
        "{level: <8} | "
        "{extra[source_location]} | "
        "{message}{extra[serialized_extra]}</level>\n{exception}"
    )


def _suppress_stdlib_loggers() -> None:
    for logger_name in SUPPRESSED_STDLIB_LOGGERS:
        stdlib_logger = logging.getLogger(logger_name)
        stdlib_logger.handlers.clear()
        stdlib_logger.propagate = False
        stdlib_logger.disabled = True


def _suppress_dependency_warnings() -> None:
    warnings.filterwarnings(
        "ignore",
        message=r"'asyncio\.iscoroutinefunction' is deprecated and slated for removal in Python 3\.16.*",
        category=DeprecationWarning,
    )


def setup_logging() -> None:
    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED:
        return

    settings = get_settings()
    _suppress_stdlib_loggers()
    _suppress_dependency_warnings()
    loguru_logger.remove()
    loguru_logger.add(
        sys.stdout,
        level=settings.log_level.upper(),
        colorize=True,
        format=_format_record,
        backtrace=settings.debug,
        diagnose=settings.debug,
    )
    _LOGGING_CONFIGURED = True


def get_app_logger():
    return loguru_logger
