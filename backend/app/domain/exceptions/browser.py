"""Browser and connection pool domain exceptions.

These exceptions provide structured error handling for browser operations,
enabling proper error recovery, logging, and user-friendly error messages.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BrowserErrorCode(str, Enum):
    """Error codes for browser-related failures."""

    # Connection errors (1xxx)
    CONNECTION_TIMEOUT = "BROWSER_1001"
    CONNECTION_REFUSED = "BROWSER_1002"
    CONNECTION_CLOSED = "BROWSER_1003"
    CONNECTION_POOL_EXHAUSTED = "BROWSER_1004"
    CONNECTION_UNHEALTHY = "BROWSER_1005"

    # CDP errors (2xxx)
    CDP_NOT_AVAILABLE = "BROWSER_2001"
    CDP_PROTOCOL_ERROR = "BROWSER_2002"
    CDP_TARGET_CLOSED = "BROWSER_2003"

    # Browser state errors (3xxx)
    BROWSER_CRASHED = "BROWSER_3001"
    BROWSER_UNRESPONSIVE = "BROWSER_3002"
    PAGE_LOAD_FAILED = "BROWSER_3003"
    NAVIGATION_FAILED = "BROWSER_3004"

    # Sandbox errors (4xxx)
    SANDBOX_NOT_READY = "BROWSER_4001"
    SANDBOX_INITIALIZATION_FAILED = "BROWSER_4002"
    SANDBOX_UNREACHABLE = "BROWSER_4003"

    # Resource errors (5xxx)
    RESOURCE_LIMIT_EXCEEDED = "BROWSER_5001"
    MEMORY_LIMIT_EXCEEDED = "BROWSER_5002"


@dataclass
class BrowserErrorContext:
    """Context information for browser errors."""

    cdp_url: str | None = None
    sandbox_id: str | None = None
    session_id: str | None = None
    operation: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    pool_stats: dict[str, Any] = field(default_factory=dict)
    additional_info: dict[str, Any] = field(default_factory=dict)


class BrowserError(Exception):
    """Base exception for all browser-related errors.

    Provides structured error information including:
    - Error code for programmatic handling
    - User-friendly message
    - Technical details for debugging
    - Recovery suggestions
    """

    def __init__(
        self,
        message: str,
        code: BrowserErrorCode,
        context: BrowserErrorContext | None = None,
        cause: Exception | None = None,
        recoverable: bool = True,
        recovery_hint: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.context = context or BrowserErrorContext()
        self.cause = cause
        self.recoverable = recoverable
        self.recovery_hint = recovery_hint or self._default_recovery_hint()

    def _default_recovery_hint(self) -> str:
        """Generate default recovery hint based on error code."""
        hints = {
            BrowserErrorCode.CONNECTION_TIMEOUT: "The browser connection timed out. This may resolve by retrying or restarting the sandbox.",
            BrowserErrorCode.CONNECTION_REFUSED: "The browser refused the connection. Ensure the sandbox is running and Chrome is started.",
            BrowserErrorCode.CONNECTION_CLOSED: "The browser connection was closed unexpectedly. A new connection will be attempted.",
            BrowserErrorCode.CONNECTION_POOL_EXHAUSTED: "All browser connections are in use. Please wait for a connection to become available or try again later.",
            BrowserErrorCode.CONNECTION_UNHEALTHY: "The browser connection is unhealthy. It will be replaced with a fresh connection.",
            BrowserErrorCode.CDP_NOT_AVAILABLE: "Chrome DevTools Protocol is not available. Ensure Chrome is running with remote debugging enabled.",
            BrowserErrorCode.CDP_PROTOCOL_ERROR: "A protocol error occurred. The operation will be retried.",
            BrowserErrorCode.CDP_TARGET_CLOSED: "The browser target was closed. A new page will be created.",
            BrowserErrorCode.BROWSER_CRASHED: "The browser crashed. A new browser instance will be started.",
            BrowserErrorCode.BROWSER_UNRESPONSIVE: "The browser is not responding. It may need to be restarted.",
            BrowserErrorCode.PAGE_LOAD_FAILED: "Failed to load the page. Check if the URL is accessible.",
            BrowserErrorCode.NAVIGATION_FAILED: "Navigation failed. The page may be unavailable or blocking automated access.",
            BrowserErrorCode.SANDBOX_NOT_READY: "The sandbox is not ready yet. Please wait for initialization to complete.",
            BrowserErrorCode.SANDBOX_INITIALIZATION_FAILED: "Failed to initialize the sandbox. Check Docker and resource availability.",
            BrowserErrorCode.SANDBOX_UNREACHABLE: "Cannot reach the sandbox. Network connectivity issues or sandbox may have stopped.",
            BrowserErrorCode.RESOURCE_LIMIT_EXCEEDED: "Resource limits exceeded. Consider reducing concurrent operations.",
            BrowserErrorCode.MEMORY_LIMIT_EXCEEDED: "Memory limit exceeded. The browser may need to be restarted.",
        }
        return hints.get(self.code, "An unexpected browser error occurred. Please try again.")

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for API responses."""
        return {
            "error_code": self.code.value,
            "message": self.message,
            "recoverable": self.recoverable,
            "recovery_hint": self.recovery_hint,
            "context": {
                "cdp_url": self.context.cdp_url,
                "sandbox_id": self.context.sandbox_id,
                "session_id": self.context.session_id,
                "operation": self.context.operation,
                "retry_count": self.context.retry_count,
            },
        }

    def __str__(self) -> str:
        parts = [f"[{self.code.value}] {self.message}"]
        if self.context.cdp_url:
            parts.append(f"CDP URL: {self.context.cdp_url}")
        if self.context.sandbox_id:
            parts.append(f"Sandbox: {self.context.sandbox_id}")
        if self.context.retry_count > 0:
            parts.append(f"Retries: {self.context.retry_count}/{self.context.max_retries}")
        return " | ".join(parts)


class ConnectionPoolExhaustedError(BrowserError):
    """Raised when all connections in the pool are in use and timeout is reached."""

    def __init__(
        self,
        cdp_url: str,
        timeout: float,
        pool_size: int,
        in_use_count: int,
        context: BrowserErrorContext | None = None,
    ):
        ctx = context or BrowserErrorContext()
        ctx.cdp_url = cdp_url
        ctx.pool_stats = {
            "timeout_seconds": timeout,
            "pool_size": pool_size,
            "in_use_count": in_use_count,
            "available_count": pool_size - in_use_count,
        }

        message = (
            f"Connection pool exhausted for {cdp_url}. "
            f"All {pool_size} connections in use after waiting {timeout}s. "
            f"Consider increasing pool size or reducing concurrent operations."
        )

        super().__init__(
            message=message,
            code=BrowserErrorCode.CONNECTION_POOL_EXHAUSTED,
            context=ctx,
            recoverable=True,
            recovery_hint=(
                "All browser connections are currently in use. "
                "This can happen during high concurrency. Options:\n"
                "1. Wait a moment and retry - connections may free up\n"
                "2. Start a new session - it will get its own connection\n"
                "3. Contact support if this persists"
            ),
        )
        self.timeout = timeout
        self.pool_size = pool_size
        self.in_use_count = in_use_count


class ConnectionTimeoutError(BrowserError):
    """Raised when a connection attempt times out."""

    def __init__(
        self,
        cdp_url: str,
        timeout: float,
        context: BrowserErrorContext | None = None,
        cause: Exception | None = None,
    ):
        ctx = context or BrowserErrorContext()
        ctx.cdp_url = cdp_url

        message = f"Connection to {cdp_url} timed out after {timeout}s"

        super().__init__(
            message=message,
            code=BrowserErrorCode.CONNECTION_TIMEOUT,
            context=ctx,
            cause=cause,
            recoverable=True,
        )
        self.timeout = timeout


class ConnectionRefusedError(BrowserError):
    """Raised when the browser refuses the connection."""

    def __init__(
        self,
        cdp_url: str,
        context: BrowserErrorContext | None = None,
        cause: Exception | None = None,
    ):
        ctx = context or BrowserErrorContext()
        ctx.cdp_url = cdp_url

        message = f"Connection refused by {cdp_url}. Chrome may not be running or CDP is not enabled."

        super().__init__(
            message=message,
            code=BrowserErrorCode.CONNECTION_REFUSED,
            context=ctx,
            cause=cause,
            recoverable=True,
        )


class BrowserCrashedError(BrowserError):
    """Raised when the browser crashes or becomes unresponsive."""

    def __init__(
        self,
        cdp_url: str,
        context: BrowserErrorContext | None = None,
        cause: Exception | None = None,
    ):
        ctx = context or BrowserErrorContext()
        ctx.cdp_url = cdp_url

        message = f"Browser at {cdp_url} crashed or became unresponsive"

        super().__init__(
            message=message,
            code=BrowserErrorCode.BROWSER_CRASHED,
            context=ctx,
            cause=cause,
            recoverable=True,
            recovery_hint="The browser crashed. A new browser instance will be started automatically.",
        )


class SandboxNotReadyError(BrowserError):
    """Raised when the sandbox is not ready for browser operations."""

    def __init__(
        self,
        sandbox_id: str,
        reason: str = "Sandbox initialization in progress",
        context: BrowserErrorContext | None = None,
    ):
        ctx = context or BrowserErrorContext()
        ctx.sandbox_id = sandbox_id

        message = f"Sandbox {sandbox_id} is not ready: {reason}"

        super().__init__(
            message=message,
            code=BrowserErrorCode.SANDBOX_NOT_READY,
            context=ctx,
            recoverable=True,
        )
        self.reason = reason


class CDPProtocolError(BrowserError):
    """Raised when a CDP protocol error occurs."""

    def __init__(
        self,
        cdp_url: str,
        protocol_error: str,
        context: BrowserErrorContext | None = None,
        cause: Exception | None = None,
    ):
        ctx = context or BrowserErrorContext()
        ctx.cdp_url = cdp_url
        ctx.additional_info["protocol_error"] = protocol_error

        message = f"CDP protocol error at {cdp_url}: {protocol_error}"

        super().__init__(
            message=message,
            code=BrowserErrorCode.CDP_PROTOCOL_ERROR,
            context=ctx,
            cause=cause,
            recoverable=True,
        )
        self.protocol_error = protocol_error
