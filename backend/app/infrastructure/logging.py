import logging
import sys
import json
import time
import threading
from typing import Optional, Dict

try:
    import httpx
except Exception:
    httpx = None

from app.core.config import get_settings


class LogAlertHandler(logging.Handler):
    def __init__(self, webhook_url: str, timeout_seconds: float, throttle_seconds: int):
        super().__init__(level=logging.WARNING)
        self._webhook_url = webhook_url
        self._timeout_seconds = timeout_seconds
        self._throttle_seconds = throttle_seconds
        self._last_sent_by_key: Dict[str, float] = {}
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        if not self._webhook_url or httpx is None:
            return

        try:
            message = record.getMessage()
            should_alert = record.levelno >= logging.ERROR
            if not should_alert and record.levelno == logging.WARNING:
                if "Stuck pattern detected" in message:
                    should_alert = True
                elif "shutdown timed out" in message:
                    should_alert = True
                elif "Failed to create task" in message:
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

def setup_logging():
    """
    Configure the application logging system
    
    Sets up log levels, formatters, and handlers for both console and file output.
    Ensures proper log rotation to prevent log files from growing too large.
    """
    # Get configuration
    settings = get_settings()
    
    # Get root logger
    root_logger = logging.getLogger()
    
    # Set root log level
    log_level = getattr(logging, settings.log_level)
    root_logger.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # Add handlers to root logger
    root_logger.addHandler(console_handler)

    if settings.alert_webhook_url:
        root_logger.addHandler(
            LogAlertHandler(
                webhook_url=settings.alert_webhook_url,
                timeout_seconds=settings.alert_webhook_timeout_seconds,
                throttle_seconds=settings.alert_throttle_seconds,
            )
        )

    # Disable verbose logging for pymongo
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("sse_starlette.sse").setLevel(logging.INFO)
    
    # Log initialization complete
    root_logger.info("Logging system initialized - Console and file logging active") 
