"""Tests for browser exception hierarchy (app.domain.exceptions.browser).

Covers BrowserErrorCode enum, BrowserErrorContext, BrowserError base class,
all specialized subclasses, to_dict serialization, and string formatting.
"""

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

# ── BrowserErrorCode ─────────────────────────────────────────────────


class TestBrowserErrorCode:
    """Tests for BrowserErrorCode enum."""

    def test_connection_codes_prefix(self) -> None:
        assert BrowserErrorCode.CONNECTION_TIMEOUT.value == "BROWSER_1001"
        assert BrowserErrorCode.CONNECTION_REFUSED.value == "BROWSER_1002"
        assert BrowserErrorCode.CONNECTION_CLOSED.value == "BROWSER_1003"
        assert BrowserErrorCode.CONNECTION_POOL_EXHAUSTED.value == "BROWSER_1004"
        assert BrowserErrorCode.CONNECTION_UNHEALTHY.value == "BROWSER_1005"

    def test_cdp_codes_prefix(self) -> None:
        assert BrowserErrorCode.CDP_NOT_AVAILABLE.value == "BROWSER_2001"
        assert BrowserErrorCode.CDP_PROTOCOL_ERROR.value == "BROWSER_2002"
        assert BrowserErrorCode.CDP_TARGET_CLOSED.value == "BROWSER_2003"

    def test_browser_state_codes(self) -> None:
        assert BrowserErrorCode.BROWSER_CRASHED.value == "BROWSER_3001"
        assert BrowserErrorCode.BROWSER_UNRESPONSIVE.value == "BROWSER_3002"
        assert BrowserErrorCode.PAGE_LOAD_FAILED.value == "BROWSER_3003"
        assert BrowserErrorCode.NAVIGATION_FAILED.value == "BROWSER_3004"

    def test_sandbox_codes(self) -> None:
        assert BrowserErrorCode.SANDBOX_NOT_READY.value == "BROWSER_4001"
        assert BrowserErrorCode.SANDBOX_INITIALIZATION_FAILED.value == "BROWSER_4002"
        assert BrowserErrorCode.SANDBOX_UNREACHABLE.value == "BROWSER_4003"

    def test_resource_codes(self) -> None:
        assert BrowserErrorCode.RESOURCE_LIMIT_EXCEEDED.value == "BROWSER_5001"
        assert BrowserErrorCode.MEMORY_LIMIT_EXCEEDED.value == "BROWSER_5002"

    def test_is_string_enum(self) -> None:
        assert isinstance(BrowserErrorCode.BROWSER_CRASHED, str)
        assert BrowserErrorCode.BROWSER_CRASHED == "BROWSER_3001"

    def test_all_codes_unique(self) -> None:
        values = [c.value for c in BrowserErrorCode]
        assert len(values) == len(set(values))


# ── BrowserErrorContext ──────────────────────────────────────────────


class TestBrowserErrorContext:
    """Tests for BrowserErrorContext dataclass."""

    def test_default_values(self) -> None:
        ctx = BrowserErrorContext()
        assert ctx.cdp_url is None
        assert ctx.sandbox_id is None
        assert ctx.session_id is None
        assert ctx.operation is None
        assert ctx.retry_count == 0
        assert ctx.max_retries == 3
        assert ctx.pool_stats == {}
        assert ctx.additional_info == {}

    def test_custom_values(self) -> None:
        ctx = BrowserErrorContext(
            cdp_url="http://localhost:9222",
            sandbox_id="sandbox-1",
            session_id="session-1",
            operation="navigate",
            retry_count=2,
            max_retries=5,
            pool_stats={"size": 4},
            additional_info={"page": "https://example.com"},
        )
        assert ctx.cdp_url == "http://localhost:9222"
        assert ctx.sandbox_id == "sandbox-1"
        assert ctx.session_id == "session-1"
        assert ctx.operation == "navigate"
        assert ctx.retry_count == 2
        assert ctx.max_retries == 5
        assert ctx.pool_stats == {"size": 4}
        assert ctx.additional_info == {"page": "https://example.com"}


# ── BrowserError base ────────────────────────────────────────────────


class TestBrowserError:
    """Tests for BrowserError base class."""

    def test_basic_creation(self) -> None:
        err = BrowserError("test error", BrowserErrorCode.BROWSER_CRASHED)
        assert err.message == "test error"
        assert err.code == BrowserErrorCode.BROWSER_CRASHED
        assert err.recoverable is True
        assert isinstance(err, Exception)

    def test_with_context(self) -> None:
        ctx = BrowserErrorContext(cdp_url="http://localhost:9222")
        err = BrowserError("test", BrowserErrorCode.BROWSER_CRASHED, context=ctx)
        assert err.context.cdp_url == "http://localhost:9222"

    def test_default_context(self) -> None:
        err = BrowserError("test", BrowserErrorCode.BROWSER_CRASHED)
        assert err.context is not None
        assert isinstance(err.context, BrowserErrorContext)

    def test_with_cause(self) -> None:
        cause = RuntimeError("underlying error")
        err = BrowserError("test", BrowserErrorCode.BROWSER_CRASHED, cause=cause)
        assert err.cause is cause

    def test_non_recoverable(self) -> None:
        err = BrowserError("fatal", BrowserErrorCode.BROWSER_CRASHED, recoverable=False)
        assert err.recoverable is False

    def test_custom_recovery_hint(self) -> None:
        err = BrowserError(
            "test",
            BrowserErrorCode.BROWSER_CRASHED,
            recovery_hint="Custom hint",
        )
        assert err.recovery_hint == "Custom hint"

    def test_default_recovery_hints(self) -> None:
        for code in BrowserErrorCode:
            err = BrowserError("test", code)
            assert err.recovery_hint is not None
            assert len(err.recovery_hint) > 0

    def test_to_dict(self) -> None:
        ctx = BrowserErrorContext(
            cdp_url="http://localhost:9222",
            sandbox_id="sb-1",
            session_id="sess-1",
            operation="navigate",
            retry_count=1,
        )
        err = BrowserError("test error", BrowserErrorCode.NAVIGATION_FAILED, context=ctx)
        d = err.to_dict()
        assert d["error_code"] == "BROWSER_3004"
        assert d["message"] == "test error"
        assert d["recoverable"] is True
        assert d["recovery_hint"] is not None
        assert d["context"]["cdp_url"] == "http://localhost:9222"
        assert d["context"]["sandbox_id"] == "sb-1"
        assert d["context"]["session_id"] == "sess-1"
        assert d["context"]["operation"] == "navigate"
        assert d["context"]["retry_count"] == 1

    def test_str_basic(self) -> None:
        err = BrowserError("test error", BrowserErrorCode.BROWSER_CRASHED)
        s = str(err)
        assert "[BROWSER_3001]" in s
        assert "test error" in s

    def test_str_with_cdp_url(self) -> None:
        ctx = BrowserErrorContext(cdp_url="http://localhost:9222")
        err = BrowserError("test", BrowserErrorCode.BROWSER_CRASHED, context=ctx)
        s = str(err)
        assert "http://localhost:9222" in s

    def test_str_with_sandbox(self) -> None:
        ctx = BrowserErrorContext(sandbox_id="sb-1")
        err = BrowserError("test", BrowserErrorCode.BROWSER_CRASHED, context=ctx)
        assert "sb-1" in str(err)

    def test_str_with_retries(self) -> None:
        ctx = BrowserErrorContext(retry_count=2, max_retries=5)
        err = BrowserError("test", BrowserErrorCode.BROWSER_CRASHED, context=ctx)
        assert "2/5" in str(err)


# ── ConnectionPoolExhaustedError ─────────────────────────────────────


class TestConnectionPoolExhaustedError:
    """Tests for ConnectionPoolExhaustedError."""

    def test_creation(self) -> None:
        err = ConnectionPoolExhaustedError(
            cdp_url="http://localhost:9222",
            timeout=30.0,
            pool_size=4,
            in_use_count=4,
        )
        assert err.timeout == 30.0
        assert err.pool_size == 4
        assert err.in_use_count == 4
        assert err.code == BrowserErrorCode.CONNECTION_POOL_EXHAUSTED
        assert err.recoverable is True
        assert isinstance(err, BrowserError)

    def test_message_content(self) -> None:
        err = ConnectionPoolExhaustedError(
            cdp_url="http://localhost:9222",
            timeout=30.0,
            pool_size=4,
            in_use_count=4,
        )
        assert "http://localhost:9222" in err.message
        assert "4" in err.message
        assert "30" in err.message

    def test_pool_stats(self) -> None:
        err = ConnectionPoolExhaustedError(
            cdp_url="http://localhost:9222",
            timeout=30.0,
            pool_size=6,
            in_use_count=5,
        )
        stats = err.context.pool_stats
        assert stats["pool_size"] == 6
        assert stats["in_use_count"] == 5
        assert stats["available_count"] == 1
        assert stats["timeout_seconds"] == 30.0

    def test_recovery_hint(self) -> None:
        err = ConnectionPoolExhaustedError(
            cdp_url="http://localhost:9222",
            timeout=30.0,
            pool_size=4,
            in_use_count=4,
        )
        assert "retry" in err.recovery_hint.lower()


# ── ConnectionTimeoutError ───────────────────────────────────────────


class TestConnectionTimeoutError:
    """Tests for ConnectionTimeoutError."""

    def test_creation(self) -> None:
        err = ConnectionTimeoutError(cdp_url="http://localhost:9222", timeout=10.0)
        assert err.timeout == 10.0
        assert err.code == BrowserErrorCode.CONNECTION_TIMEOUT
        assert err.recoverable is True
        assert "http://localhost:9222" in err.message
        assert "10" in err.message

    def test_with_cause(self) -> None:
        cause = TimeoutError("original timeout")
        err = ConnectionTimeoutError(
            cdp_url="http://localhost:9222",
            timeout=10.0,
            cause=cause,
        )
        assert err.cause is cause


# ── ConnectionRefusedError ───────────────────────────────────────────


class TestConnectionRefusedError:
    """Tests for ConnectionRefusedError (browser-domain version)."""

    def test_creation(self) -> None:
        err = ConnectionRefusedError(cdp_url="http://localhost:9222")
        assert err.code == BrowserErrorCode.CONNECTION_REFUSED
        assert err.recoverable is True
        assert "http://localhost:9222" in err.message
        assert "Chrome" in err.message or "CDP" in err.message

    def test_isinstance_browser_error(self) -> None:
        err = ConnectionRefusedError(cdp_url="http://localhost:9222")
        assert isinstance(err, BrowserError)


# ── BrowserCrashedError ──────────────────────────────────────────────


class TestBrowserCrashedError:
    """Tests for BrowserCrashedError."""

    def test_creation(self) -> None:
        err = BrowserCrashedError(cdp_url="http://localhost:9222")
        assert err.code == BrowserErrorCode.BROWSER_CRASHED
        assert err.recoverable is True
        assert "http://localhost:9222" in err.message
        assert "crashed" in err.message.lower()

    def test_recovery_hint(self) -> None:
        err = BrowserCrashedError(cdp_url="http://localhost:9222")
        assert "new browser instance" in err.recovery_hint.lower()


# ── SandboxNotReadyError ─────────────────────────────────────────────


class TestSandboxNotReadyError:
    """Tests for SandboxNotReadyError."""

    def test_creation(self) -> None:
        err = SandboxNotReadyError(sandbox_id="sb-123")
        assert err.code == BrowserErrorCode.SANDBOX_NOT_READY
        assert err.recoverable is True
        assert "sb-123" in err.message
        assert err.reason == "Sandbox initialization in progress"

    def test_custom_reason(self) -> None:
        err = SandboxNotReadyError(sandbox_id="sb-123", reason="Docker pull in progress")
        assert "Docker pull" in err.message
        assert err.reason == "Docker pull in progress"

    def test_context_sandbox_id(self) -> None:
        err = SandboxNotReadyError(sandbox_id="sb-123")
        assert err.context.sandbox_id == "sb-123"


# ── CDPProtocolError ─────────────────────────────────────────────────


class TestCDPProtocolError:
    """Tests for CDPProtocolError."""

    def test_creation(self) -> None:
        err = CDPProtocolError(
            cdp_url="http://localhost:9222",
            protocol_error="Target.detachedFromTarget",
        )
        assert err.code == BrowserErrorCode.CDP_PROTOCOL_ERROR
        assert err.protocol_error == "Target.detachedFromTarget"
        assert "Target.detachedFromTarget" in err.message
        assert err.recoverable is True

    def test_additional_info(self) -> None:
        err = CDPProtocolError(
            cdp_url="http://localhost:9222",
            protocol_error="Session closed",
        )
        assert err.context.additional_info["protocol_error"] == "Session closed"

    def test_isinstance_chain(self) -> None:
        err = CDPProtocolError(
            cdp_url="http://localhost:9222",
            protocol_error="test",
        )
        assert isinstance(err, CDPProtocolError)
        assert isinstance(err, BrowserError)
        assert isinstance(err, Exception)
