"""
Structured Logging with structlog

Provides JSON-formatted logging with correlation ID propagation through async operations.
"""

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.core.config import get_settings

# Context variables for correlation IDs
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
agent_id_var: ContextVar[str | None] = ContextVar("agent_id", default=None)


def set_request_id(request_id: str) -> None:
    """Set the current request ID for correlation."""
    request_id_var.set(request_id)


def get_request_id() -> str | None:
    """Get the current request ID."""
    return request_id_var.get()


def set_session_id(session_id: str) -> None:
    """Set the current session ID for correlation."""
    session_id_var.set(session_id)


def get_session_id() -> str | None:
    """Get the current session ID."""
    return session_id_var.get()


def set_user_id(user_id: str) -> None:
    """Set the current user ID for correlation."""
    user_id_var.set(user_id)


def get_user_id() -> str | None:
    """Get the current user ID."""
    return user_id_var.get()


def set_agent_id(agent_id: str) -> None:
    """Set the current agent ID for correlation."""
    agent_id_var.set(agent_id)


def get_agent_id() -> str | None:
    """Get the current agent ID."""
    return agent_id_var.get()


def add_correlation_ids(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Processor to inject correlation IDs into all log entries."""
    request_id = request_id_var.get()
    session_id = session_id_var.get()
    user_id = user_id_var.get()
    agent_id = agent_id_var.get()

    if request_id:
        event_dict["request_id"] = request_id
    if session_id:
        event_dict["session_id"] = session_id
    if user_id:
        event_dict["user_id"] = user_id
    if agent_id:
        event_dict["agent_id"] = agent_id

    # Also try to get from observability context (fallback)
    try:
        from app.infrastructure.observability.context import get_request_context
        ctx = get_request_context()
        if ctx.request_id and "request_id" not in event_dict:
            event_dict["request_id"] = ctx.request_id
        if ctx.session_id and "session_id" not in event_dict:
            event_dict["session_id"] = ctx.session_id
        if ctx.user_id and "user_id" not in event_dict:
            event_dict["user_id"] = ctx.user_id
        if ctx.agent_id and "agent_id" not in event_dict:
            event_dict["agent_id"] = ctx.agent_id
    except Exception:
        pass  # Context not available

    return event_dict


def add_log_level(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add log level to event dict."""
    event_dict["level"] = method_name.upper()
    return event_dict


def setup_structured_logging() -> None:
    """
    Configure the application logging system with structlog.

    Features:
    - JSON output in production, colored console in development
    - Correlation IDs automatically included in all log entries
    - Preserves existing alert webhook functionality
    - Suppresses verbose third-party loggers
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Shared processors for both stdlib and structlog
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        add_correlation_ids,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.is_development:
        # Development: colored console output
        processors: list[Processor] = [
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
        )
    else:
        # Production: JSON output
        processors = [
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler with structlog formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # Add alert webhook handler if configured
    if settings.alert_webhook_url:
        from app.infrastructure.logging import LogAlertHandler

        root_logger.addHandler(
            LogAlertHandler(
                webhook_url=settings.alert_webhook_url,
                timeout_seconds=settings.alert_webhook_timeout_seconds,
                throttle_seconds=settings.alert_throttle_seconds,
            )
        )

    # Suppress verbose third-party loggers
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("sse_starlette.sse").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Log initialization
    logger = get_logger(__name__)
    logger.info("Structured logging initialized", environment=settings.environment)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structlog logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        A bound structlog logger
    """
    return structlog.get_logger(name)


def bind_contextvars(**kwargs: Any) -> None:
    """
    Bind additional context variables to all subsequent log entries.

    Args:
        **kwargs: Key-value pairs to add to log context
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_contextvars() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()
