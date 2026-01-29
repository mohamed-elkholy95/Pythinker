"""Logging Configuration for Pythinker.

Provides structured JSON logging with request context correlation,
configurable log levels, and webhook alerting for critical errors.

Features:
- JSON structured logging for production (parseable by log aggregators)
- Request ID correlation across all log entries
- Session/User/Agent ID attribution
- Webhook alerts for errors with throttling
"""

import json
import logging
import sys
import threading
import time
from datetime import datetime
from typing import Any

try:
    import httpx
except Exception:
    httpx = None

from app.core.config import get_settings


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter with request context.

    Produces JSON log lines suitable for log aggregation systems
    (ELK, Datadog, CloudWatch, etc.) with request correlation fields.

    Output format:
    {
        "timestamp": "2024-01-15T10:30:00.123Z",
        "level": "INFO",
        "logger": "app.module",
        "message": "Log message",
        "request_id": "abc123",
        "session_id": "sess-456",
        "user_id": "user-789",
        "agent_id": "agent-001",
        "path": "/api/v1/sessions",
        "duration_ms": 150.5,
        "extra": {...}
    }
    """

    # Fields that should be at the top level of the JSON
    STANDARD_FIELDS = {
        'request_id', 'session_id', 'user_id', 'agent_id',
        'trace_id', 'span_id', 'path', 'method', 'duration_ms',
        'status_code', 'error_type', 'error_code'
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Get request context if available
        request_id = None
        session_id = None
        user_id = None
        agent_id = None

        try:
            from app.infrastructure.observability.context import get_request_context
            ctx = get_request_context()
            request_id = ctx.request_id
            session_id = ctx.session_id
            user_id = ctx.user_id
            agent_id = ctx.agent_id
        except Exception:
            # Context not available, use record extras
            request_id = getattr(record, 'request_id', None)
            session_id = getattr(record, 'session_id', None)
            user_id = getattr(record, 'user_id', None)
            agent_id = getattr(record, 'agent_id', None)

        # Build base log entry
        log_entry: dict[str, Any] = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation IDs
        if request_id:
            log_entry["request_id"] = request_id
        if session_id:
            log_entry["session_id"] = session_id
        if user_id:
            log_entry["user_id"] = user_id
        if agent_id:
            log_entry["agent_id"] = agent_id

        # Add standard fields from record
        for field in self.STANDARD_FIELDS:
            value = getattr(record, field, None)
            if value is not None and field not in log_entry:
                log_entry[field] = value

        # Add source location for errors
        if record.levelno >= logging.WARNING:
            log_entry["source"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Collect any extra fields not in STANDARD_FIELDS
        extra_fields = {}
        for key, value in record.__dict__.items():
            if (key not in logging.LogRecord.__dict__ and
                key not in self.STANDARD_FIELDS and
                key not in {'message', 'msg', 'args', 'exc_info', 'exc_text',
                            'stack_info', 'created', 'msecs', 'relativeCreated',
                            'levelno', 'levelname', 'pathname', 'filename',
                            'module', 'funcName', 'lineno', 'name', 'thread',
                            'threadName', 'processName', 'process'}):
                try:
                    # Ensure value is JSON serializable
                    json.dumps(value)
                    extra_fields[key] = value
                except (TypeError, ValueError):
                    extra_fields[key] = str(value)

        if extra_fields:
            log_entry["extra"] = extra_fields

        return json.dumps(log_entry, default=str)


class RequestContextFilter(logging.Filter):
    """Logging filter that adds request context to all records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add request context fields to the log record."""
        try:
            from app.infrastructure.observability.context import get_request_context
            ctx = get_request_context()
            record.request_id = ctx.request_id
            record.session_id = ctx.session_id
            record.user_id = ctx.user_id
            record.agent_id = ctx.agent_id
        except Exception:
            # Context not available
            if not hasattr(record, 'request_id'):
                record.request_id = None
            if not hasattr(record, 'session_id'):
                record.session_id = None
            if not hasattr(record, 'user_id'):
                record.user_id = None
            if not hasattr(record, 'agent_id'):
                record.agent_id = None

        return True


class LogAlertHandler(logging.Handler):
    def __init__(self, webhook_url: str, timeout_seconds: float, throttle_seconds: int):
        super().__init__(level=logging.WARNING)
        self._webhook_url = webhook_url
        self._timeout_seconds = timeout_seconds
        self._throttle_seconds = throttle_seconds
        self._last_sent_by_key: dict[str, float] = {}
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        if not self._webhook_url or httpx is None:
            return

        try:
            message = record.getMessage()
            should_alert = record.levelno >= logging.ERROR
            if not should_alert and record.levelno == logging.WARNING:
                if "Stuck pattern detected" in message or "shutdown timed out" in message or "Failed to create task" in message:
                    should_alert = True

            if not should_alert:
                return

            now = time.time()
            key = f"{record.levelname}:{record.name}:{message[:200]}"
            with self._lock:
                last = self._last_sent_by_key.get(key)
                if last is not None and (now - last) < self._throttle_seconds:
                    return
                self._last_sent_by_key[key] = now

            payload = {
                "timestamp": int(now),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
                "path": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
                "process": record.process,
                "thread": record.thread,
            }

            def _send() -> None:
                try:
                    with httpx.Client(timeout=self._timeout_seconds) as client:
                        client.post(self._webhook_url, content=json.dumps(payload), headers={"Content-Type": "application/json"})
                except Exception:
                    return

            threading.Thread(target=_send, daemon=True).start()
        except Exception:
            return

def setup_logging(use_json: bool | None = None):
    """Configure the application logging system.

    Sets up log levels, formatters, and handlers for console output.
    Supports both human-readable and JSON structured formats.

    Args:
        use_json: Force JSON format (None = auto-detect from environment)
    """
    # Get configuration
    settings = get_settings()

    # Determine if we should use JSON format
    if use_json is None:
        # Use JSON in production, human-readable in development
        use_json = settings.is_production

    # Get root logger
    root_logger = logging.getLogger()

    # Clear existing handlers to avoid duplicates on reload
    root_logger.handlers.clear()

    # Set root log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Create formatter based on environment
    if use_json:
        formatter = StructuredFormatter()
    else:
        # Human-readable format with request ID
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            defaults={'request_id': '-'}
        )

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # Add request context filter
    context_filter = RequestContextFilter()
    console_handler.addFilter(context_filter)

    # Add handlers to root logger
    root_logger.addHandler(console_handler)

    # Add webhook alert handler if configured
    if settings.alert_webhook_url:
        alert_handler = LogAlertHandler(
            webhook_url=settings.alert_webhook_url,
            timeout_seconds=settings.alert_webhook_timeout_seconds,
            throttle_seconds=settings.alert_throttle_seconds,
        )
        alert_handler.addFilter(context_filter)
        root_logger.addHandler(alert_handler)

    # Reduce noise from verbose libraries
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("sse_starlette.sse").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Log initialization
    format_type = "JSON structured" if use_json else "human-readable"
    root_logger.info(
        f"Logging system initialized - {format_type} format, level={settings.log_level}"
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the request context filter attached.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    # Filter is added at handler level, not logger level
    return logger
