"""لاگ ساخت‌یافته (structured logging) برای کل بک‌اند."""
from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings

_SENSITIVE = {"password", "token", "secret", "private_key", "authorization", "api_key"}


def _mask_sensitive(_logger, _name, event_dict):
    for key in list(event_dict.keys()):
        if any(s in key.lower() for s in _SENSITIVE):
            event_dict[key] = "***"
    return event_dict


def configure_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    renderer = (
        structlog.dev.ConsoleRenderer()
        if not settings.is_production
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _mask_sensitive,
            structlog.processors.StackInfoRenderer(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "alfa"):
    return structlog.get_logger(name)
