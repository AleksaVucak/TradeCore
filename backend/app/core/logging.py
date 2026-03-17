"""
Structured logging configuration using structlog (Phase 12.1).

Provides JSON logging for production and pretty console output for development.
All logs include automatic context: timestamp, level, logger name, and any
additional bound context.

Usage:
    from app.core.logging import get_logger
    
    logger = get_logger(__name__)
    logger.info("user_registered", user_id=123, email="user@example.com")
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from app.config import settings


def _add_log_level(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add the log level to the event dict."""
    event_dict["level"] = method_name.upper()
    return event_dict


def _add_logger_name(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add the logger name to the event dict."""
    record = event_dict.get("_record")
    if record:
        event_dict["logger"] = record.name
    elif hasattr(logger, "name"):
        event_dict["logger"] = logger.name
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog and standard logging.
    
    Call this once at application startup (e.g., in main.py or celery_app.py).
    
    When LOG_JSON=true (production), outputs JSON lines.
    When LOG_JSON=false (development), outputs colored console output.
    """
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    if settings.log_json:
        shared_processors.append(structlog.processors.format_exc_info)
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)
    
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    
    for logger_name in ["celery", "celery.task", "celery.worker"]:
        celery_logger = logging.getLogger(logger_name)
        celery_logger.handlers.clear()
        celery_logger.propagate = True
    
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__). If None, returns root logger.
    
    Returns:
        A structlog BoundLogger that supports binding context.
        
    Example:
        logger = get_logger(__name__)
        logger.info("event_name", key1="value1", key2=123)
        
        # Bind context for multiple log calls
        logger = logger.bind(user_id=123)
        logger.info("action_one")
        logger.info("action_two")  # Both have user_id=123
    """
    return structlog.get_logger(name)


def bind_contextvars(**kwargs: Any) -> None:
    """
    Bind context variables that will be included in all subsequent log messages
    within the current context (e.g., a request).
    
    Useful for adding request_id, user_id, etc. at the start of a request.
    
    Example:
        @app.middleware("http")
        async def add_request_context(request, call_next):
            bind_contextvars(request_id=str(uuid.uuid4()))
            response = await call_next(request)
            clear_contextvars()
            return response
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_contextvars() -> None:
    """Clear all context variables (call at end of request)."""
    structlog.contextvars.clear_contextvars()
