"""Tests for app.core.error_manager — centralized error management system.

Covers: ErrorSeverity, ErrorCategory, ErrorRecoverability, classify_recoverability,
ErrorContext, ErrorRecord, ErrorManager, CircuitBreaker, error_handler decorator,
error_context context manager.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.core.error_manager import (
    CircuitBreaker,
    ErrorCategory,
    ErrorContext,
    ErrorManager,
    ErrorRecord,
    ErrorRecoverability,
    ErrorSeverity,
    classify_recoverability,
    error_context,
    error_handler,
)


# ---------------------------------------------------------------------------
# classify_recoverability
# ---------------------------------------------------------------------------
class TestClassifyRecoverability:
    """Tests for the classify_recoverability helper."""

    def test_timeout_error_is_transient(self):
        assert classify_recoverability(TimeoutError("timed out")) == ErrorRecoverability.TRANSIENT

    def test_connection_error_is_transient(self):
        assert classify_recoverability(ConnectionError("refused")) == ErrorRecoverability.TRANSIENT

    def test_connection_reset_is_transient(self):
        assert classify_recoverability(ConnectionResetError()) == ErrorRecoverability.TRANSIENT

    def test_connection_refused_is_transient(self):
        assert classify_recoverability(ConnectionRefusedError()) == ErrorRecoverability.TRANSIENT

    def test_broken_pipe_is_transient(self):
        assert classify_recoverability(BrokenPipeError()) == ErrorRecoverability.TRANSIENT

    def test_os_error_is_transient(self):
        assert classify_recoverability(OSError("network")) == ErrorRecoverability.TRANSIENT

    def test_value_error_is_permanent(self):
        assert classify_recoverability(ValueError("bad value")) == ErrorRecoverability.PERMANENT

    def test_type_error_is_permanent(self):
        assert classify_recoverability(TypeError("wrong type")) == ErrorRecoverability.PERMANENT

    def test_key_error_is_permanent(self):
        assert classify_recoverability(KeyError("missing key")) == ErrorRecoverability.PERMANENT

    def test_attribute_error_is_permanent(self):
        assert classify_recoverability(AttributeError("no attr")) == ErrorRecoverability.PERMANENT

    def test_permission_error_is_transient_via_oserror(self):
        # PermissionError is a subclass of OSError, so it matches TRANSIENT first
        assert classify_recoverability(PermissionError("denied")) == ErrorRecoverability.TRANSIENT

    def test_file_not_found_is_transient_via_oserror(self):
        # FileNotFoundError is a subclass of OSError, so it matches TRANSIENT first
        assert classify_recoverability(FileNotFoundError("gone")) == ErrorRecoverability.TRANSIENT

    def test_rate_limit_message_is_transient(self):
        assert classify_recoverability(RuntimeError("rate limit exceeded")) == ErrorRecoverability.TRANSIENT

    def test_429_message_is_transient(self):
        assert classify_recoverability(RuntimeError("HTTP 429 error")) == ErrorRecoverability.TRANSIENT

    def test_too_many_requests_is_transient(self):
        assert classify_recoverability(RuntimeError("too many requests")) == ErrorRecoverability.TRANSIENT

    def test_throttle_message_is_transient(self):
        assert classify_recoverability(RuntimeError("throttle applied")) == ErrorRecoverability.TRANSIENT

    def test_timeout_in_message_is_transient(self):
        assert classify_recoverability(RuntimeError("request timed out")) == ErrorRecoverability.TRANSIENT

    def test_unauthorized_message_is_permanent(self):
        assert classify_recoverability(RuntimeError("unauthorized access")) == ErrorRecoverability.PERMANENT

    def test_forbidden_message_is_permanent(self):
        assert classify_recoverability(RuntimeError("forbidden")) == ErrorRecoverability.PERMANENT

    def test_401_message_is_permanent(self):
        assert classify_recoverability(RuntimeError("HTTP 401")) == ErrorRecoverability.PERMANENT

    def test_invalid_message_is_permanent(self):
        assert classify_recoverability(RuntimeError("invalid parameter")) == ErrorRecoverability.PERMANENT

    def test_validation_message_is_permanent(self):
        assert classify_recoverability(RuntimeError("validation error")) == ErrorRecoverability.PERMANENT

    def test_out_of_memory_is_degraded(self):
        assert classify_recoverability(RuntimeError("out of memory")) == ErrorRecoverability.DEGRADED

    def test_quota_message_is_degraded(self):
        assert classify_recoverability(RuntimeError("quota exceeded")) == ErrorRecoverability.DEGRADED

    def test_limit_exceeded_is_degraded(self):
        assert classify_recoverability(RuntimeError("limit exceeded")) == ErrorRecoverability.DEGRADED

    def test_unknown_error_is_unknown(self):
        assert classify_recoverability(RuntimeError("something else entirely")) == ErrorRecoverability.UNKNOWN

    def test_empty_message_is_unknown(self):
        assert classify_recoverability(RuntimeError("")) == ErrorRecoverability.UNKNOWN


# ---------------------------------------------------------------------------
# ErrorRecord
# ---------------------------------------------------------------------------
class TestErrorRecord:
    """Tests for ErrorRecord dataclass."""

    def _make_context(self) -> ErrorContext:
        return ErrorContext(component="test", operation="test_op")

    def _make_record(self, exception: Exception, **kwargs) -> ErrorRecord:
        defaults = {
            "id": "test-001",
            "timestamp": datetime.now(UTC),
            "severity": ErrorSeverity.MEDIUM,
            "category": ErrorCategory.AGENT,
            "context": self._make_context(),
            "exception": exception,
            "traceback_str": "test traceback",
        }
        defaults.update(kwargs)
        return ErrorRecord(**defaults)

    def test_auto_classifies_recoverability(self):
        record = self._make_record(TimeoutError("timed out"))
        assert record.recoverability == ErrorRecoverability.TRANSIENT

    def test_auto_classifies_permanent(self):
        record = self._make_record(ValueError("bad"))
        assert record.recoverability == ErrorRecoverability.PERMANENT

    def test_preserves_explicit_recoverability(self):
        record = self._make_record(
            RuntimeError("something"),
            recoverability=ErrorRecoverability.DEGRADED,
        )
        assert record.recoverability == ErrorRecoverability.DEGRADED

    def test_suggested_action_for_transient(self):
        record = self._make_record(TimeoutError("timed out"))
        assert "retry" in record.suggested_action.lower() or "backoff" in record.suggested_action.lower()

    def test_suggested_action_for_permanent(self):
        record = self._make_record(ValueError("bad"))
        assert "not retry" in record.suggested_action.lower() or "root cause" in record.suggested_action.lower()

    def test_suggested_action_for_degraded(self):
        record = self._make_record(RuntimeError("out of memory"))
        assert "fallback" in record.suggested_action.lower()

    def test_suggested_action_for_unknown(self):
        record = self._make_record(RuntimeError("what happened"))
        assert "investigate" in record.suggested_action.lower()

    def test_should_retry_true_for_transient(self):
        record = self._make_record(TimeoutError("timed out"))
        assert record.should_retry is True

    def test_should_retry_false_for_permanent(self):
        record = self._make_record(ValueError("bad"))
        assert record.should_retry is False

    def test_should_retry_false_for_unknown(self):
        record = self._make_record(RuntimeError("odd"))
        assert record.should_retry is False


# ---------------------------------------------------------------------------
# ErrorManager
# ---------------------------------------------------------------------------
class TestErrorManager:
    """Tests for ErrorManager class."""

    def _make_context(self, **kwargs) -> ErrorContext:
        defaults = {"component": "test_component", "operation": "test_op"}
        defaults.update(kwargs)
        return ErrorContext(**defaults)

    @pytest.mark.asyncio
    async def test_handle_error_records_in_history(self):
        manager = ErrorManager()
        ctx = self._make_context()
        await manager.handle_error(RuntimeError("boom"), ctx, auto_recover=False)
        stats = manager.get_error_stats(hours=1)
        assert stats["total_errors"] == 1

    @pytest.mark.asyncio
    async def test_handle_error_with_recovery_strategy(self):
        manager = ErrorManager()
        strategy = AsyncMock(return_value=True)
        manager.register_recovery_strategy(ErrorCategory.AGENT, strategy)
        ctx = self._make_context()
        result = await manager.handle_error(
            RuntimeError("boom"),
            ctx,
            category=ErrorCategory.AGENT,
            auto_recover=True,
        )
        assert result is True
        strategy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_error_failed_recovery(self):
        manager = ErrorManager()
        strategy = AsyncMock(return_value=False)
        manager.register_recovery_strategy(ErrorCategory.AGENT, strategy)
        ctx = self._make_context()
        result = await manager.handle_error(
            RuntimeError("boom"),
            ctx,
            category=ErrorCategory.AGENT,
            auto_recover=True,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_error_recovery_strategy_raises(self):
        manager = ErrorManager()
        strategy = AsyncMock(side_effect=RuntimeError("recovery failed"))
        manager.register_recovery_strategy(ErrorCategory.AGENT, strategy)
        ctx = self._make_context()
        result = await manager.handle_error(
            RuntimeError("boom"),
            ctx,
            category=ErrorCategory.AGENT,
            auto_recover=True,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_error_history_size_limit(self):
        manager = ErrorManager()
        manager._max_history = 5
        ctx = self._make_context()
        for i in range(10):
            await manager.handle_error(RuntimeError(f"error {i}"), ctx, auto_recover=False)
        assert len(manager._error_history) == 5

    @pytest.mark.asyncio
    async def test_get_error_stats_by_severity(self):
        manager = ErrorManager()
        ctx = self._make_context()
        await manager.handle_error(
            RuntimeError("crit"),
            ctx,
            severity=ErrorSeverity.CRITICAL,
            auto_recover=False,
        )
        await manager.handle_error(
            RuntimeError("low"),
            ctx,
            severity=ErrorSeverity.LOW,
            auto_recover=False,
        )
        stats = manager.get_error_stats(hours=1)
        assert stats["by_severity"]["critical"] == 1
        assert stats["by_severity"]["low"] == 1

    @pytest.mark.asyncio
    async def test_get_error_stats_by_category(self):
        manager = ErrorManager()
        ctx = self._make_context()
        await manager.handle_error(
            RuntimeError("db"),
            ctx,
            category=ErrorCategory.DATABASE,
            auto_recover=False,
        )
        await manager.handle_error(
            RuntimeError("net"),
            ctx,
            category=ErrorCategory.NETWORK,
            auto_recover=False,
        )
        stats = manager.get_error_stats(hours=1)
        assert stats["by_category"]["database"] == 1
        assert stats["by_category"]["network"] == 1

    @pytest.mark.asyncio
    async def test_get_error_stats_filters_by_time(self):
        manager = ErrorManager()
        ctx = self._make_context()
        # Add an error manually with old timestamp
        old_record = ErrorRecord(
            id="old-1",
            timestamp=datetime.now(UTC) - timedelta(hours=48),
            severity=ErrorSeverity.LOW,
            category=ErrorCategory.AGENT,
            context=ctx,
            exception=RuntimeError("old"),
            traceback_str="",
        )
        manager._error_history.append(old_record)
        await manager.handle_error(RuntimeError("recent"), ctx, auto_recover=False)
        stats = manager.get_error_stats(hours=1)
        assert stats["total_errors"] == 1  # Only recent

    @pytest.mark.asyncio
    async def test_recovery_rate_calculation(self):
        manager = ErrorManager()
        strategy = AsyncMock(side_effect=[True, False])
        manager.register_recovery_strategy(ErrorCategory.AGENT, strategy)
        ctx = self._make_context()
        await manager.handle_error(
            RuntimeError("recoverable"),
            ctx,
            category=ErrorCategory.AGENT,
            auto_recover=True,
        )
        await manager.handle_error(
            RuntimeError("not recoverable"),
            ctx,
            category=ErrorCategory.AGENT,
            auto_recover=True,
        )
        stats = manager.get_error_stats(hours=1)
        assert stats["recovery_rate"] == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_multiple_recovery_strategies(self):
        manager = ErrorManager()
        strat1 = AsyncMock(return_value=False)
        strat2 = AsyncMock(return_value=True)
        manager.register_recovery_strategy(ErrorCategory.SANDBOX, strat1)
        manager.register_recovery_strategy(ErrorCategory.SANDBOX, strat2)
        ctx = self._make_context()
        result = await manager.handle_error(
            RuntimeError("sand"),
            ctx,
            category=ErrorCategory.SANDBOX,
            auto_recover=True,
        )
        assert result is True
        strat1.assert_awaited_once()
        strat2.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_recovery_when_disabled(self):
        manager = ErrorManager()
        strategy = AsyncMock(return_value=True)
        manager.register_recovery_strategy(ErrorCategory.AGENT, strategy)
        ctx = self._make_context()
        result = await manager.handle_error(
            RuntimeError("no auto"),
            ctx,
            category=ErrorCategory.AGENT,
            auto_recover=False,
        )
        assert result is False
        strategy.assert_not_awaited()


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------
class TestCircuitBreaker:
    """Tests for CircuitBreaker state machine."""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker()
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == "closed"

    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        assert cb.state == "open"
        # With 0 timeout, any time > 0 should trigger half-open
        cb.last_failure_time = datetime.now(UTC) - timedelta(seconds=1)
        assert cb.can_execute() is True
        assert cb.state == "half-open"

    def test_half_open_allows_execution(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        cb.last_failure_time = datetime.now(UTC) - timedelta(seconds=1)
        cb.can_execute()  # Transitions to half-open
        assert cb.state == "half-open"
        assert cb.can_execute() is True

    def test_success_in_half_open_closes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        cb.last_failure_time = datetime.now(UTC) - timedelta(seconds=1)
        cb.can_execute()  # half-open
        cb.record_success()
        assert cb.state == "closed"

    def test_open_blocks_until_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=3600)
        cb.record_failure()
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_custom_thresholds(self):
        cb = CircuitBreaker(failure_threshold=10, recovery_timeout=120)
        for _ in range(9):
            cb.record_failure()
        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "open"


# ---------------------------------------------------------------------------
# error_handler decorator
# ---------------------------------------------------------------------------
class TestErrorHandlerDecorator:
    """Tests for the error_handler decorator."""

    @pytest.mark.asyncio
    async def test_decorated_async_function_returns_normally(self):
        @error_handler(reraise=False)
        async def good_func():
            return 42

        result = await good_func()
        assert result == 42

    @pytest.mark.asyncio
    async def test_decorated_async_function_catches_error(self):
        @error_handler(reraise=False)
        async def bad_func():
            raise RuntimeError("boom")

        result = await bad_func()
        assert result is None  # Error swallowed

    @pytest.mark.asyncio
    async def test_decorated_async_function_reraises(self):
        @error_handler(reraise=True)
        async def bad_func():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await bad_func()

    def test_decorated_sync_function_returns_normally(self):
        @error_handler(reraise=False)
        def good_func():
            return 42

        result = good_func()
        assert result == 42

    def test_decorated_sync_function_catches_error(self):
        @error_handler(reraise=False)
        def bad_func():
            raise RuntimeError("boom")

        result = bad_func()
        assert result is None

    def test_decorated_sync_function_reraises(self):
        @error_handler(reraise=True)
        def bad_func():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            bad_func()


# ---------------------------------------------------------------------------
# error_context context manager
# ---------------------------------------------------------------------------
class TestErrorContextManager:
    """Tests for the error_context async context manager."""

    @pytest.mark.asyncio
    async def test_passes_through_on_success(self):
        async with error_context("comp", "op"):
            result = 1 + 1
        assert result == 2

    @pytest.mark.asyncio
    async def test_reraises_when_recovery_fails(self):
        with pytest.raises(RuntimeError, match="ctx boom"):
            async with error_context("comp", "op", auto_recover=False):
                raise RuntimeError("ctx boom")


# ---------------------------------------------------------------------------
# ErrorContext
# ---------------------------------------------------------------------------
class TestErrorContext:
    """Tests for ErrorContext dataclass."""

    def test_defaults(self):
        ctx = ErrorContext(component="c", operation="o")
        assert ctx.user_id is None
        assert ctx.session_id is None
        assert ctx.agent_id is None
        assert ctx.metadata == {}

    def test_full_construction(self):
        ctx = ErrorContext(
            component="backend",
            operation="chat",
            user_id="u1",
            session_id="s1",
            agent_id="a1",
            metadata={"key": "val"},
        )
        assert ctx.component == "backend"
        assert ctx.metadata["key"] == "val"


# ---------------------------------------------------------------------------
# Enums coverage
# ---------------------------------------------------------------------------
class TestEnums:
    """Test enum values exist and are correct."""

    def test_error_severity_values(self):
        assert ErrorSeverity.CRITICAL.value == "critical"
        assert ErrorSeverity.HIGH.value == "high"
        assert ErrorSeverity.MEDIUM.value == "medium"
        assert ErrorSeverity.LOW.value == "low"

    def test_error_category_values(self):
        assert ErrorCategory.SANDBOX.value == "sandbox"
        assert ErrorCategory.LLM.value == "llm"
        assert ErrorCategory.TIMEOUT.value == "timeout"
        assert ErrorCategory.RATE_LIMIT.value == "rate_limit"

    def test_error_recoverability_values(self):
        assert ErrorRecoverability.TRANSIENT.value == "transient"
        assert ErrorRecoverability.PERMANENT.value == "permanent"
        assert ErrorRecoverability.DEGRADED.value == "degraded"
        assert ErrorRecoverability.UNKNOWN.value == "unknown"
