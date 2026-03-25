"""Tests for core error management system."""

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
    error_handler,
    get_error_manager,
)
from datetime import UTC, datetime


@pytest.mark.unit
class TestErrorSeverity:
    """Tests for ErrorSeverity enum."""

    def test_critical_value(self) -> None:
        assert ErrorSeverity.CRITICAL == "critical"

    def test_high_value(self) -> None:
        assert ErrorSeverity.HIGH == "high"

    def test_medium_value(self) -> None:
        assert ErrorSeverity.MEDIUM == "medium"

    def test_low_value(self) -> None:
        assert ErrorSeverity.LOW == "low"

    def test_member_count(self) -> None:
        assert len(ErrorSeverity) == 4


@pytest.mark.unit
class TestErrorCategory:
    """Tests for ErrorCategory enum."""

    def test_all_categories_present(self) -> None:
        expected = {
            "sandbox", "agent", "database", "network",
            "authentication", "validation", "resource",
            "external_api", "llm", "tool", "timeout", "rate_limit",
        }
        actual = {c.value for c in ErrorCategory}
        assert actual == expected

    def test_member_count(self) -> None:
        assert len(ErrorCategory) == 12


@pytest.mark.unit
class TestErrorRecoverability:
    """Tests for ErrorRecoverability enum."""

    def test_transient_value(self) -> None:
        assert ErrorRecoverability.TRANSIENT == "transient"

    def test_permanent_value(self) -> None:
        assert ErrorRecoverability.PERMANENT == "permanent"

    def test_degraded_value(self) -> None:
        assert ErrorRecoverability.DEGRADED == "degraded"

    def test_unknown_value(self) -> None:
        assert ErrorRecoverability.UNKNOWN == "unknown"


@pytest.mark.unit
class TestClassifyRecoverability:
    """Tests for classify_recoverability function."""

    def test_timeout_is_transient(self) -> None:
        assert classify_recoverability(TimeoutError("timed out")) == ErrorRecoverability.TRANSIENT

    def test_connection_error_is_transient(self) -> None:
        assert classify_recoverability(ConnectionError("refused")) == ErrorRecoverability.TRANSIENT

    def test_connection_reset_is_transient(self) -> None:
        assert classify_recoverability(ConnectionResetError()) == ErrorRecoverability.TRANSIENT

    def test_value_error_is_permanent(self) -> None:
        assert classify_recoverability(ValueError("bad input")) == ErrorRecoverability.PERMANENT

    def test_type_error_is_permanent(self) -> None:
        assert classify_recoverability(TypeError("wrong type")) == ErrorRecoverability.PERMANENT

    def test_key_error_is_permanent(self) -> None:
        assert classify_recoverability(KeyError("missing")) == ErrorRecoverability.PERMANENT

    def test_permission_error_is_transient(self) -> None:
        # PermissionError inherits from OSError which is in TRANSIENT_EXCEPTIONS,
        # so type-based classification takes precedence over message matching
        assert classify_recoverability(PermissionError("denied")) == ErrorRecoverability.TRANSIENT

    def test_rate_limit_message_is_transient(self) -> None:
        assert classify_recoverability(Exception("rate limit exceeded")) == ErrorRecoverability.TRANSIENT

    def test_429_message_is_transient(self) -> None:
        assert classify_recoverability(Exception("HTTP 429 Too Many Requests")) == ErrorRecoverability.TRANSIENT

    def test_unauthorized_message_is_permanent(self) -> None:
        assert classify_recoverability(Exception("401 Unauthorized")) == ErrorRecoverability.PERMANENT

    def test_forbidden_message_is_permanent(self) -> None:
        assert classify_recoverability(Exception("403 Forbidden access")) == ErrorRecoverability.PERMANENT

    def test_validation_message_is_permanent(self) -> None:
        assert classify_recoverability(Exception("validation failed")) == ErrorRecoverability.PERMANENT

    def test_out_of_memory_is_degraded(self) -> None:
        assert classify_recoverability(Exception("out of memory")) == ErrorRecoverability.DEGRADED

    def test_quota_exceeded_is_degraded(self) -> None:
        assert classify_recoverability(Exception("quota exceeded")) == ErrorRecoverability.DEGRADED

    def test_unknown_exception_is_unknown(self) -> None:
        assert classify_recoverability(Exception("something weird")) == ErrorRecoverability.UNKNOWN

    def test_timeout_message_is_transient(self) -> None:
        assert classify_recoverability(Exception("request timed out")) == ErrorRecoverability.TRANSIENT


@pytest.mark.unit
class TestErrorContext:
    """Tests for ErrorContext dataclass."""

    def test_minimal_construction(self) -> None:
        ctx = ErrorContext(component="backend", operation="process")
        assert ctx.component == "backend"
        assert ctx.operation == "process"
        assert ctx.user_id is None
        assert ctx.session_id is None
        assert ctx.agent_id is None
        assert ctx.metadata == {}

    def test_full_construction(self) -> None:
        ctx = ErrorContext(
            component="sandbox",
            operation="execute",
            user_id="u1",
            session_id="s1",
            agent_id="a1",
            metadata={"key": "value"},
        )
        assert ctx.user_id == "u1"
        assert ctx.session_id == "s1"
        assert ctx.agent_id == "a1"
        assert ctx.metadata == {"key": "value"}


@pytest.mark.unit
class TestErrorRecord:
    """Tests for ErrorRecord dataclass."""

    def _make_record(self, exc: Exception | None = None, **kwargs) -> ErrorRecord:
        defaults = {
            "id": "test_1",
            "timestamp": datetime.now(UTC),
            "severity": ErrorSeverity.MEDIUM,
            "category": ErrorCategory.AGENT,
            "context": ErrorContext(component="test", operation="test"),
            "exception": exc or ValueError("test error"),
            "traceback_str": "",
        }
        defaults.update(kwargs)
        return ErrorRecord(**defaults)

    def test_auto_classify_recoverability(self) -> None:
        record = self._make_record(exc=TimeoutError("timeout"))
        assert record.recoverability == ErrorRecoverability.TRANSIENT

    def test_auto_classify_permanent(self) -> None:
        record = self._make_record(exc=ValueError("bad"))
        assert record.recoverability == ErrorRecoverability.PERMANENT

    def test_should_retry_transient(self) -> None:
        record = self._make_record(exc=TimeoutError("timeout"))
        assert record.should_retry is True

    def test_should_not_retry_permanent(self) -> None:
        record = self._make_record(exc=ValueError("bad"))
        assert record.should_retry is False

    def test_suggested_action_transient(self) -> None:
        record = self._make_record(exc=TimeoutError("timeout"))
        assert "backoff" in record.suggested_action.lower()

    def test_suggested_action_permanent(self) -> None:
        record = self._make_record(exc=ValueError("bad"))
        assert "root cause" in record.suggested_action.lower()

    def test_explicit_recoverability_preserved(self) -> None:
        record = self._make_record(recoverability=ErrorRecoverability.DEGRADED)
        assert record.recoverability == ErrorRecoverability.DEGRADED


@pytest.mark.unit
class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_initial_state_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_stays_closed_below_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_success_resets_count(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == "closed"

    def test_success_closes_half_open(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        assert cb.state == "open"
        # With 0 timeout, should transition to half-open
        assert cb.can_execute() is True
        assert cb.state == "half-open"
        cb.record_success()
        assert cb.state == "closed"

    def test_default_failure_threshold(self) -> None:
        cb = CircuitBreaker()
        assert cb.failure_threshold == 5

    def test_default_recovery_timeout(self) -> None:
        cb = CircuitBreaker()
        assert cb.recovery_timeout == 60


@pytest.mark.unit
class TestErrorManager:
    """Tests for ErrorManager."""

    def test_initial_state(self) -> None:
        em = ErrorManager()
        stats = em.get_error_stats()
        assert stats["total_errors"] == 0

    @pytest.mark.asyncio
    async def test_handle_error_records(self) -> None:
        em = ErrorManager()
        ctx = ErrorContext(component="test", operation="test_op")
        await em.handle_error(
            ValueError("test"),
            ctx,
            severity=ErrorSeverity.LOW,
            category=ErrorCategory.VALIDATION,
            auto_recover=False,
        )
        stats = em.get_error_stats()
        assert stats["total_errors"] == 1
        assert stats["by_severity"]["low"] == 1
        assert stats["by_category"]["validation"] == 1

    @pytest.mark.asyncio
    async def test_recovery_strategy_called(self) -> None:
        em = ErrorManager()
        recovered = False

        async def mock_strategy(record: ErrorRecord) -> bool:
            nonlocal recovered
            recovered = True
            return True

        em.register_recovery_strategy(ErrorCategory.DATABASE, mock_strategy)

        ctx = ErrorContext(component="db", operation="query")
        result = await em.handle_error(
            ConnectionError("lost"),
            ctx,
            category=ErrorCategory.DATABASE,
            auto_recover=True,
        )
        assert result is True
        assert recovered is True

    @pytest.mark.asyncio
    async def test_failed_recovery(self) -> None:
        em = ErrorManager()

        async def failing_strategy(record: ErrorRecord) -> bool:
            return False

        em.register_recovery_strategy(ErrorCategory.NETWORK, failing_strategy)

        ctx = ErrorContext(component="net", operation="fetch")
        result = await em.handle_error(
            ConnectionError("down"),
            ctx,
            category=ErrorCategory.NETWORK,
            auto_recover=True,
        )
        assert result is False

    def test_history_limit(self) -> None:
        em = ErrorManager()
        em._max_history = 5
        for i in range(10):
            record = ErrorRecord(
                id=f"err_{i}",
                timestamp=datetime.now(UTC),
                severity=ErrorSeverity.LOW,
                category=ErrorCategory.AGENT,
                context=ErrorContext(component="test", operation="test"),
                exception=ValueError(f"error {i}"),
                traceback_str="",
            )
            em._add_error_record(record)
        assert len(em._error_history) == 5

    def test_get_error_stats_recovery_rate(self) -> None:
        em = ErrorManager()
        for i in range(4):
            record = ErrorRecord(
                id=f"err_{i}",
                timestamp=datetime.now(UTC),
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.AGENT,
                context=ErrorContext(component="test", operation="test"),
                exception=ValueError("test"),
                traceback_str="",
                recovery_successful=(i < 2),
            )
            em._add_error_record(record)
        stats = em.get_error_stats()
        assert stats["recovery_rate"] == 0.5


@pytest.mark.unit
class TestGetErrorManager:
    """Tests for the global error manager getter."""

    def test_returns_error_manager(self) -> None:
        em = get_error_manager()
        assert isinstance(em, ErrorManager)

    def test_returns_same_instance(self) -> None:
        em1 = get_error_manager()
        em2 = get_error_manager()
        assert em1 is em2


@pytest.mark.unit
class TestErrorHandler:
    """Tests for the error_handler decorator."""

    @pytest.mark.asyncio
    async def test_async_function_returns_none_on_error(self) -> None:
        @error_handler(severity=ErrorSeverity.LOW, auto_recover=False)
        async def failing_func():
            raise ValueError("boom")

        result = await failing_func()
        assert result is None

    @pytest.mark.asyncio
    async def test_async_function_passes_through_on_success(self) -> None:
        @error_handler()
        async def success_func():
            return 42

        result = await success_func()
        assert result == 42

    def test_sync_function_returns_none_on_error(self) -> None:
        @error_handler(severity=ErrorSeverity.LOW, reraise=False)
        def failing_func():
            raise ValueError("boom")

        result = failing_func()
        assert result is None

    def test_sync_function_reraises_when_configured(self) -> None:
        @error_handler(severity=ErrorSeverity.LOW, reraise=True)
        def failing_func():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            failing_func()
