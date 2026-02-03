"""Domain exceptions package."""

from app.domain.exceptions.browser import (
    BrowserCrashedError,
    BrowserError,
    BrowserErrorCode,
    BrowserErrorContext,
    CDPProtocolError,
    ConnectionPoolExhaustedError,
    ConnectionRefusedError,
    ConnectionTimeoutError,
    SandboxNotReadyError,
)

__all__ = [
    "BrowserCrashedError",
    "BrowserError",
    "BrowserErrorCode",
    "BrowserErrorContext",
    "CDPProtocolError",
    "ConnectionPoolExhaustedError",
    "ConnectionRefusedError",
    "ConnectionTimeoutError",
    "SandboxNotReadyError",
]
