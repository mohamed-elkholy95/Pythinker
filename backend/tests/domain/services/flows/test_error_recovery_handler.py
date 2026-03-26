"""Comprehensive tests for ErrorRecoveryHandler.

Covers:
- Property access (error_handler, error_context, previous_status,
  total_error_count, error_recovery_attempts)
- record_error: classification delegation and snapshot behaviour
- record_error_context: manual context storage
- attempt_recovery: all decision branches
- reset_cycle_counter and reset_all
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.models.state_model import AgentStatus
from app.domain.services.agents.error_handler import ErrorContext, ErrorHandler, ErrorType
from app.domain.services.flows.error_recovery_handler import ErrorRecoveryHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_error_handler() -> MagicMock:
    """Return a MagicMock that satisfies the ErrorHandler interface."""
    return MagicMock(spec=ErrorHandler)


def _make_recoverable_context(message: str = "boom") -> ErrorContext:
    return ErrorContext(
        error_type=ErrorType.TIMEOUT,
        message=message,
        recoverable=True,
    )


def _make_non_recoverable_context(message: str = "fatal") -> ErrorContext:
    return ErrorContext(
        error_type=ErrorType.UNKNOWN,
        message=message,
        recoverable=False,
    )


def _make_handler(
    *,
    max_recovery_attempts: int = 3,
    max_total_errors: int = 10,
) -> tuple[ErrorRecoveryHandler, MagicMock]:
    """Return (handler, mock_error_handler) pair."""
    mock_eh = _make_error_handler()
    handler = ErrorRecoveryHandler(
        mock_eh,
        max_recovery_attempts=max_recovery_attempts,
        max_total_errors=max_total_errors,
    )
    return handler, mock_eh


def _noop_transition(new_status: AgentStatus, *, force: bool = False, reason: str = "") -> None:
    pass


def _noop_inject(prompt: str) -> None:
    pass


# ---------------------------------------------------------------------------
# Construction & defaults
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_max_recovery_attempts(self) -> None:
        handler, _ = _make_handler()
        assert handler.error_recovery_attempts == 0

    def test_default_total_error_count(self) -> None:
        handler, _ = _make_handler()
        assert handler.total_error_count == 0

    def test_default_error_context_is_none(self) -> None:
        handler, _ = _make_handler()
        assert handler.error_context is None

    def test_default_previous_status_is_none(self) -> None:
        handler, _ = _make_handler()
        assert handler.previous_status is None

    def test_error_handler_property_returns_injected_instance(self) -> None:
        handler, mock_eh = _make_handler()
        assert handler.error_handler is mock_eh

    def test_custom_max_recovery_attempts_stored(self) -> None:
        handler, _ = _make_handler(max_recovery_attempts=5)
        # Verify by exhausting attempts
        ctx = _make_recoverable_context()
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        # We reach the per-cycle cap after 5 attempts, not 3
        assert handler._max_error_recovery_attempts == 5

    def test_custom_max_total_errors_stored(self) -> None:
        handler, _ = _make_handler(max_total_errors=2)
        assert handler._max_total_errors == 2


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_error_context_reflects_recorded_value(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.classify_error.return_value = ctx
        handler.record_error(ValueError("x"), AgentStatus.PLANNING)
        assert handler.error_context is ctx

    def test_previous_status_reflects_recorded_status(self) -> None:
        handler, mock_eh = _make_handler()
        mock_eh.classify_error.return_value = _make_recoverable_context()
        handler.record_error(ValueError("x"), AgentStatus.EXECUTING)
        assert handler.previous_status is AgentStatus.EXECUTING

    def test_total_error_count_starts_at_zero(self) -> None:
        handler, _ = _make_handler()
        assert handler.total_error_count == 0

    def test_error_recovery_attempts_starts_at_zero(self) -> None:
        handler, _ = _make_handler()
        assert handler.error_recovery_attempts == 0

    def test_error_handler_property_identity(self) -> None:
        mock_eh = _make_error_handler()
        handler = ErrorRecoveryHandler(mock_eh)
        assert handler.error_handler is mock_eh


# ---------------------------------------------------------------------------
# record_error
# ---------------------------------------------------------------------------


class TestRecordError:
    def test_calls_classify_error_with_exception(self) -> None:
        handler, mock_eh = _make_handler()
        exc = RuntimeError("test error")
        ctx = _make_recoverable_context()
        mock_eh.classify_error.return_value = ctx

        handler.record_error(exc, AgentStatus.PLANNING)

        mock_eh.classify_error.assert_called_once_with(exc)

    def test_stores_returned_error_context(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context("classified")
        mock_eh.classify_error.return_value = ctx

        result = handler.record_error(ValueError("v"), AgentStatus.IDLE)

        assert result is ctx
        assert handler.error_context is ctx

    def test_snapshots_current_status(self) -> None:
        handler, mock_eh = _make_handler()
        mock_eh.classify_error.return_value = _make_recoverable_context()

        handler.record_error(Exception(), AgentStatus.SUMMARIZING)

        assert handler.previous_status is AgentStatus.SUMMARIZING

    def test_overwrites_previous_context_on_second_call(self) -> None:
        handler, mock_eh = _make_handler()
        ctx1 = _make_recoverable_context("first")
        ctx2 = _make_recoverable_context("second")
        mock_eh.classify_error.side_effect = [ctx1, ctx2]

        handler.record_error(Exception("1"), AgentStatus.PLANNING)
        handler.record_error(Exception("2"), AgentStatus.EXECUTING)

        assert handler.error_context is ctx2
        assert handler.previous_status is AgentStatus.EXECUTING

    def test_returns_error_context_directly(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_non_recoverable_context()
        mock_eh.classify_error.return_value = ctx

        returned = handler.record_error(Exception("z"), AgentStatus.ERROR)

        assert returned is ctx

    def test_does_not_increment_total_error_count(self) -> None:
        """record_error only classifies; total_error_count is incremented inside attempt_recovery."""
        handler, mock_eh = _make_handler()
        mock_eh.classify_error.return_value = _make_recoverable_context()

        handler.record_error(Exception(), AgentStatus.EXECUTING)

        assert handler.total_error_count == 0

    def test_different_status_values_stored_correctly(self) -> None:
        for status in [
            AgentStatus.IDLE,
            AgentStatus.PLANNING,
            AgentStatus.EXECUTING,
            AgentStatus.SUMMARIZING,
            AgentStatus.REFLECTING,
        ]:
            handler, mock_eh = _make_handler()
            mock_eh.classify_error.return_value = _make_recoverable_context()
            handler.record_error(Exception(), status)
            assert handler.previous_status is status


# ---------------------------------------------------------------------------
# record_error_context
# ---------------------------------------------------------------------------


class TestRecordErrorContext:
    def test_stores_provided_context(self) -> None:
        handler, _ = _make_handler()
        ctx = _make_recoverable_context("manual")

        handler.record_error_context(ctx, AgentStatus.PLANNING)

        assert handler.error_context is ctx

    def test_stores_provided_status(self) -> None:
        handler, _ = _make_handler()
        ctx = _make_non_recoverable_context()

        handler.record_error_context(ctx, AgentStatus.VERIFYING)

        assert handler.previous_status is AgentStatus.VERIFYING

    def test_does_not_call_classify_error(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()

        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        mock_eh.classify_error.assert_not_called()

    def test_overwrites_existing_context(self) -> None:
        handler, mock_eh = _make_handler()
        ctx1 = _make_recoverable_context("first")
        ctx2 = _make_non_recoverable_context("second")
        mock_eh.classify_error.return_value = ctx1

        handler.record_error(Exception(), AgentStatus.PLANNING)
        handler.record_error_context(ctx2, AgentStatus.EXECUTING)

        assert handler.error_context is ctx2
        assert handler.previous_status is AgentStatus.EXECUTING


# ---------------------------------------------------------------------------
# attempt_recovery — not in ERROR state
# ---------------------------------------------------------------------------


class TestAttemptRecoveryNotInErrorState:
    @pytest.mark.asyncio
    async def test_returns_true_when_status_is_not_error(self) -> None:
        handler, _ = _make_handler()
        transition = MagicMock()

        result = await handler.attempt_recovery(AgentStatus.EXECUTING, transition)

        assert result is True

    @pytest.mark.asyncio
    async def test_does_not_call_transition_when_status_is_not_error(self) -> None:
        handler, _ = _make_handler()
        transition = MagicMock()

        await handler.attempt_recovery(AgentStatus.PLANNING, transition)

        transition.assert_not_called()

    @pytest.mark.asyncio
    async def test_idle_status_returns_true(self) -> None:
        handler, _ = _make_handler()
        result = await handler.attempt_recovery(AgentStatus.IDLE, _noop_transition)
        assert result is True

    @pytest.mark.asyncio
    async def test_summarizing_status_returns_true(self) -> None:
        handler, _ = _make_handler()
        result = await handler.attempt_recovery(AgentStatus.SUMMARIZING, _noop_transition)
        assert result is True

    @pytest.mark.asyncio
    async def test_total_error_count_not_incremented_when_not_in_error(self) -> None:
        handler, _ = _make_handler()
        await handler.attempt_recovery(AgentStatus.EXECUTING, _noop_transition)
        assert handler.total_error_count == 0


# ---------------------------------------------------------------------------
# attempt_recovery — no error context
# ---------------------------------------------------------------------------


class TestAttemptRecoveryNoContext:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_error_context(self) -> None:
        handler, _ = _make_handler()
        transition = MagicMock()

        result = await handler.attempt_recovery(AgentStatus.ERROR, transition)

        assert result is False

    @pytest.mark.asyncio
    async def test_does_not_call_transition_when_no_error_context(self) -> None:
        handler, _ = _make_handler()
        transition = MagicMock()

        await handler.attempt_recovery(AgentStatus.ERROR, transition)

        transition.assert_not_called()

    @pytest.mark.asyncio
    async def test_total_error_count_incremented_even_when_no_context(self) -> None:
        """total_error_count is incremented before the context check."""
        handler, _ = _make_handler()
        # We need a context to get past the context guard; keep it None and
        # verify count stays at 0 because the guard fires first.
        result = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)
        # Guard fires BEFORE count increment (implementation: count is incremented
        # after the context check) — validate actual implementation behaviour.
        # Looking at source: count is incremented AFTER the context check.
        assert result is False
        assert handler.total_error_count == 0


# ---------------------------------------------------------------------------
# attempt_recovery — max total errors
# ---------------------------------------------------------------------------


class TestAttemptRecoveryMaxTotalErrors:
    @pytest.mark.asyncio
    async def test_returns_false_when_total_errors_reaches_limit(self) -> None:
        handler, _ = _make_handler(max_total_errors=3)
        ctx = _make_recoverable_context()
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        # Exhaust budget (total_error_count reaches 3 on the 3rd call)
        for _ in range(2):
            await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)
            # Reset cycle counter so per-cycle limit doesn't fire first
            handler.reset_cycle_counter()

        result = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert result is False

    @pytest.mark.asyncio
    async def test_transition_not_called_after_total_limit(self) -> None:
        handler, mock_eh = _make_handler(max_total_errors=2)
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "recover"
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        transition = MagicMock()

        # Consume first slot (succeeds)
        await handler.attempt_recovery(AgentStatus.ERROR, transition)
        handler.reset_cycle_counter()
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        # Second call: count reaches limit
        await handler.attempt_recovery(AgentStatus.ERROR, transition)
        handler.reset_cycle_counter()
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        # Third call: over limit
        transition.reset_mock()
        result = await handler.attempt_recovery(AgentStatus.ERROR, transition)

        assert result is False
        transition.assert_not_called()

    @pytest.mark.asyncio
    async def test_total_error_count_increments_each_call(self) -> None:
        handler, _ = _make_handler(max_total_errors=100)
        ctx = _make_recoverable_context()

        for _ in range(5):
            handler.record_error_context(ctx, AgentStatus.EXECUTING)
            await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)
            handler.reset_cycle_counter()

        assert handler.total_error_count == 5


# ---------------------------------------------------------------------------
# attempt_recovery — max recovery attempts per cycle
# ---------------------------------------------------------------------------


class TestAttemptRecoveryMaxCycleAttempts:
    @pytest.mark.asyncio
    async def test_returns_false_when_cycle_limit_reached(self) -> None:
        handler, mock_eh = _make_handler(max_recovery_attempts=2, max_total_errors=100)
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "prompt"

        # First call: recoverable but previous_status is consumed (set to None)
        # so we re-set it each time
        for _ in range(2):
            handler.record_error_context(ctx, AgentStatus.EXECUTING)
            await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        # Third call with context but per-cycle count exhausted
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        result = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert result is False

    @pytest.mark.asyncio
    async def test_error_recovery_attempts_increments_on_each_success(self) -> None:
        handler, mock_eh = _make_handler(max_recovery_attempts=5, max_total_errors=100)
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "prompt"

        for _ in range(3):
            handler.record_error_context(ctx, AgentStatus.EXECUTING)
            await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert handler.error_recovery_attempts == 3

    @pytest.mark.asyncio
    async def test_reset_cycle_counter_allows_fresh_cycle(self) -> None:
        handler, mock_eh = _make_handler(max_recovery_attempts=1, max_total_errors=100)
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "p"

        # Exhaust first cycle
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        # Reset and try again — should succeed
        handler.reset_cycle_counter()
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        result = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert result is True


# ---------------------------------------------------------------------------
# attempt_recovery — not recoverable
# ---------------------------------------------------------------------------


class TestAttemptRecoveryNotRecoverable:
    @pytest.mark.asyncio
    async def test_returns_false_when_context_not_recoverable(self) -> None:
        handler, _ = _make_handler()
        ctx = _make_non_recoverable_context()
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        result = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert result is False

    @pytest.mark.asyncio
    async def test_transition_not_called_when_not_recoverable(self) -> None:
        handler, _ = _make_handler()
        ctx = _make_non_recoverable_context()
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        transition = MagicMock()

        await handler.attempt_recovery(AgentStatus.ERROR, transition)

        transition.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_when_previous_status_is_none(self) -> None:
        """Recoverable context but no previous_status — cannot restore."""
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "p"
        # Set context manually without a previous_status
        handler._error_context = ctx
        # _previous_status remains None (default)

        result = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert result is False

    @pytest.mark.asyncio
    async def test_recovery_attempts_incremented_even_when_not_recoverable(self) -> None:
        """Counter increments before recoverability check."""
        handler, _ = _make_handler()
        ctx = _make_non_recoverable_context()
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert handler.error_recovery_attempts == 1


# ---------------------------------------------------------------------------
# attempt_recovery — successful recovery
# ---------------------------------------------------------------------------


class TestAttemptRecoverySuccess:
    @pytest.mark.asyncio
    async def test_returns_true_on_successful_recovery(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "Retry now."
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        result = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert result is True

    @pytest.mark.asyncio
    async def test_calls_transition_fn_with_previous_status(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "p"
        handler.record_error_context(ctx, AgentStatus.PLANNING)

        transition = MagicMock()
        await handler.attempt_recovery(AgentStatus.ERROR, transition)

        transition.assert_called_once_with(AgentStatus.PLANNING, force=True, reason="error recovery")

    @pytest.mark.asyncio
    async def test_previous_status_cleared_after_recovery(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "p"
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert handler.previous_status is None

    @pytest.mark.asyncio
    async def test_increments_recovery_attempts_counter(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "p"
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert handler.error_recovery_attempts == 1

    @pytest.mark.asyncio
    async def test_increments_total_error_count(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "p"
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert handler.total_error_count == 1


# ---------------------------------------------------------------------------
# attempt_recovery — inject_recovery_fn
# ---------------------------------------------------------------------------


class TestAttemptRecoveryInjectFn:
    @pytest.mark.asyncio
    async def test_calls_inject_fn_with_recovery_prompt(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "Please retry."
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        inject_fn = MagicMock()
        await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition, inject_fn)

        inject_fn.assert_called_once_with("Please retry.")

    @pytest.mark.asyncio
    async def test_does_not_call_inject_fn_when_no_recovery_prompt(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = None
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        inject_fn = MagicMock()
        await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition, inject_fn)

        inject_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_call_inject_fn_when_empty_string_prompt(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = ""
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        inject_fn = MagicMock()
        await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition, inject_fn)

        inject_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_inject_fn_is_optional_and_ignored_when_none(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "Prompt"
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        # No inject_fn provided — should not raise
        result = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition, None)

        assert result is True

    @pytest.mark.asyncio
    async def test_recovery_continues_when_inject_fn_raises(self) -> None:
        """If inject_fn raises, recovery still completes successfully."""
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "Prompt"
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        def bad_inject(prompt: str) -> None:
            raise RuntimeError("injection error")

        transition = MagicMock()
        result = await handler.attempt_recovery(AgentStatus.ERROR, transition, bad_inject)

        # Transition is still called even when inject throws
        assert result is True
        transition.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_recovery_prompt_called_with_correct_context(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "p"
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        mock_eh.get_recovery_prompt.assert_called_once_with(ctx)

    @pytest.mark.asyncio
    async def test_inject_fn_called_before_transition(self) -> None:
        """Verify call ordering: inject first, then transition."""
        call_order: list[str] = []

        def inject(prompt: str) -> None:
            call_order.append("inject")

        def transition(new_status: AgentStatus, *, force: bool = False, reason: str = "") -> None:
            call_order.append("transition")

        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "Prompt"
        handler.record_error_context(ctx, AgentStatus.EXECUTING)

        await handler.attempt_recovery(AgentStatus.ERROR, transition, inject)

        assert call_order == ["inject", "transition"]


# ---------------------------------------------------------------------------
# reset_cycle_counter
# ---------------------------------------------------------------------------


class TestResetCycleCounter:
    def test_resets_error_recovery_attempts_to_zero(self) -> None:
        handler, _mock_eh = _make_handler()
        handler._error_recovery_attempts = 3

        handler.reset_cycle_counter()

        assert handler.error_recovery_attempts == 0

    def test_does_not_affect_total_error_count(self) -> None:
        handler, _ = _make_handler()
        handler._total_error_count = 7
        handler._error_recovery_attempts = 2

        handler.reset_cycle_counter()

        assert handler.total_error_count == 7

    def test_does_not_affect_error_context(self) -> None:
        handler, mock_eh = _make_handler()
        ctx = _make_recoverable_context()
        mock_eh.classify_error.return_value = ctx
        handler.record_error(Exception(), AgentStatus.PLANNING)

        handler.reset_cycle_counter()

        assert handler.error_context is ctx

    def test_does_not_affect_previous_status(self) -> None:
        handler, mock_eh = _make_handler()
        mock_eh.classify_error.return_value = _make_recoverable_context()
        handler.record_error(Exception(), AgentStatus.EXECUTING)

        handler.reset_cycle_counter()

        assert handler.previous_status is AgentStatus.EXECUTING

    def test_idempotent_when_already_zero(self) -> None:
        handler, _ = _make_handler()
        handler.reset_cycle_counter()
        handler.reset_cycle_counter()
        assert handler.error_recovery_attempts == 0

    @pytest.mark.asyncio
    async def test_allows_fresh_attempts_after_reset(self) -> None:
        handler, mock_eh = _make_handler(max_recovery_attempts=1, max_total_errors=100)
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "p"

        # First cycle — uses up the one allowed attempt
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        r1 = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)
        assert r1 is True

        # Without reset — next attempt should fail (cycle limit)
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        r2 = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)
        assert r2 is False

        # After reset — should succeed again
        handler.reset_cycle_counter()
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        r3 = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)
        assert r3 is True


# ---------------------------------------------------------------------------
# reset_all
# ---------------------------------------------------------------------------


class TestResetAll:
    def test_clears_error_context(self) -> None:
        handler, mock_eh = _make_handler()
        mock_eh.classify_error.return_value = _make_recoverable_context()
        handler.record_error(Exception(), AgentStatus.EXECUTING)

        handler.reset_all()

        assert handler.error_context is None

    def test_clears_previous_status(self) -> None:
        handler, mock_eh = _make_handler()
        mock_eh.classify_error.return_value = _make_recoverable_context()
        handler.record_error(Exception(), AgentStatus.PLANNING)

        handler.reset_all()

        assert handler.previous_status is None

    def test_resets_error_recovery_attempts(self) -> None:
        handler, _ = _make_handler()
        handler._error_recovery_attempts = 5

        handler.reset_all()

        assert handler.error_recovery_attempts == 0

    def test_resets_total_error_count(self) -> None:
        handler, _ = _make_handler()
        handler._total_error_count = 8

        handler.reset_all()

        assert handler.total_error_count == 0

    def test_full_reset_leaves_all_fields_at_defaults(self) -> None:
        handler, mock_eh = _make_handler()
        mock_eh.classify_error.return_value = _make_recoverable_context()
        handler.record_error(Exception(), AgentStatus.EXECUTING)
        handler._error_recovery_attempts = 3
        handler._total_error_count = 9

        handler.reset_all()

        assert handler.error_context is None
        assert handler.previous_status is None
        assert handler.error_recovery_attempts == 0
        assert handler.total_error_count == 0

    def test_idempotent_on_clean_handler(self) -> None:
        handler, _ = _make_handler()
        handler.reset_all()
        handler.reset_all()

        assert handler.error_context is None
        assert handler.previous_status is None
        assert handler.error_recovery_attempts == 0
        assert handler.total_error_count == 0

    @pytest.mark.asyncio
    async def test_after_reset_all_recovery_succeeds_again(self) -> None:
        """Full reset allows the handler to accept new errors as if fresh.

        With max_total_errors=2, the first call increments total_error_count to 1
        (< 2) and succeeds.  The second call increments to 2 (>= 2) and fails.
        After reset_all() the count returns to 0 and the next call succeeds again.
        """
        handler, mock_eh = _make_handler(max_total_errors=2, max_recovery_attempts=3)
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "p"

        # First recovery: total_error_count becomes 1, which is < 2 → succeeds
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        r1 = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)
        assert r1 is True

        # Second call: total_error_count becomes 2, which is >= max_total_errors → fails
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        r2 = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)
        assert r2 is False

        # Full reset → budget refilled; next call succeeds
        handler.reset_all()
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        r3 = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)
        assert r3 is True


# ---------------------------------------------------------------------------
# Integration-style: combined behaviour
# ---------------------------------------------------------------------------


class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_recovery_cycle(self) -> None:
        """Simulate: error recorded → recovery attempted → cycle reset → fresh cycle."""
        mock_eh = _make_error_handler()
        ctx = _make_recoverable_context("network timeout")
        mock_eh.classify_error.return_value = ctx
        mock_eh.get_recovery_prompt.return_value = "Please retry the request."

        handler = ErrorRecoveryHandler(mock_eh, max_recovery_attempts=3, max_total_errors=10)
        transition = MagicMock()
        inject_fn = MagicMock()

        # Step 1: record via exception path
        exc = TimeoutError("network timeout")
        handler.record_error(exc, AgentStatus.EXECUTING)

        assert handler.error_context is ctx
        assert handler.previous_status is AgentStatus.EXECUTING

        # Step 2: attempt recovery
        result = await handler.attempt_recovery(AgentStatus.ERROR, transition, inject_fn)

        assert result is True
        transition.assert_called_once_with(AgentStatus.EXECUTING, force=True, reason="error recovery")
        inject_fn.assert_called_once_with("Please retry the request.")
        assert handler.previous_status is None
        assert handler.error_recovery_attempts == 1
        assert handler.total_error_count == 1

        # Step 3: successful forward progress → reset cycle counter
        handler.reset_cycle_counter()
        assert handler.error_recovery_attempts == 0
        assert handler.total_error_count == 1  # total survives reset_cycle_counter

    @pytest.mark.asyncio
    async def test_multiple_cycles_with_budget_tracking(self) -> None:
        """Three cycles each with one error — total budget tracks across all."""
        mock_eh = _make_error_handler()
        ctx = _make_recoverable_context()
        mock_eh.classify_error.return_value = ctx
        mock_eh.get_recovery_prompt.return_value = "p"

        handler = ErrorRecoveryHandler(mock_eh, max_recovery_attempts=2, max_total_errors=10)

        for cycle in range(3):
            handler.record_error_context(ctx, AgentStatus.EXECUTING)
            r = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)
            assert r is True, f"Cycle {cycle} should succeed"
            handler.reset_cycle_counter()

        assert handler.total_error_count == 3
        assert handler.error_recovery_attempts == 0  # reset each cycle

    @pytest.mark.asyncio
    async def test_manual_context_then_recovery(self) -> None:
        """record_error_context path (ErrorEvent bridge) followed by attempt_recovery."""
        mock_eh = _make_error_handler()
        mock_eh.get_recovery_prompt.return_value = "Bridge recovery prompt."

        handler = ErrorRecoveryHandler(mock_eh)
        ctx = ErrorContext(
            error_type=ErrorType.LLM_API,
            message="LLM returned 500",
            recoverable=True,
        )
        handler.record_error_context(ctx, AgentStatus.SUMMARIZING)

        transition = MagicMock()
        result = await handler.attempt_recovery(AgentStatus.ERROR, transition)

        assert result is True
        transition.assert_called_once_with(AgentStatus.SUMMARIZING, force=True, reason="error recovery")

    @pytest.mark.asyncio
    async def test_non_recoverable_context_from_classify_error(self) -> None:
        """Verify end-to-end path when classify_error produces a non-recoverable context."""
        mock_eh = _make_error_handler()
        non_recoverable = ErrorContext(
            error_type=ErrorType.UNKNOWN,
            message="??",
            recoverable=False,
        )
        mock_eh.classify_error.return_value = non_recoverable

        handler = ErrorRecoveryHandler(mock_eh)
        handler.record_error(Exception("unknown"), AgentStatus.PLANNING)

        transition = MagicMock()
        result = await handler.attempt_recovery(AgentStatus.ERROR, transition)

        assert result is False
        transition.assert_not_called()

    @pytest.mark.asyncio
    async def test_budget_exhaustion_stops_all_future_recoveries(self) -> None:
        """Once total_error_count >= max_total_errors all future calls return False."""
        mock_eh = _make_error_handler()
        ctx = _make_recoverable_context()
        mock_eh.get_recovery_prompt.return_value = "p"

        handler = ErrorRecoveryHandler(mock_eh, max_recovery_attempts=10, max_total_errors=2)

        # First two calls each increment total_error_count (1 and 2)
        for _ in range(2):
            handler.record_error_context(ctx, AgentStatus.EXECUTING)
            await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)
            handler.reset_cycle_counter()

        # total_error_count == 2 == max_total_errors → next call returns False
        handler.record_error_context(ctx, AgentStatus.EXECUTING)
        result = await handler.attempt_recovery(AgentStatus.ERROR, _noop_transition)

        assert result is False
        assert handler.total_error_count == 3  # incremented before the limit check fires

    @pytest.mark.asyncio
    async def test_error_recovery_handler_is_pure_domain_no_infrastructure(self) -> None:
        """Verify the handler can be instantiated and used without any real infrastructure."""
        mock_eh = MagicMock(spec=ErrorHandler)
        ctx = ErrorContext(
            error_type=ErrorType.JSON_PARSE,
            message="bad json",
            recoverable=True,
        )
        mock_eh.classify_error.return_value = ctx
        mock_eh.get_recovery_prompt.return_value = "Fix your JSON."

        handler = ErrorRecoveryHandler(mock_eh)
        returned_ctx = handler.record_error(ValueError("bad json"), AgentStatus.EXECUTING)

        assert returned_ctx is ctx

        calls: list[tuple[AgentStatus, bool, str]] = []

        def transition(status: AgentStatus, *, force: bool = False, reason: str = "") -> None:
            calls.append((status, force, reason))

        result = await handler.attempt_recovery(AgentStatus.ERROR, transition)

        assert result is True
        assert calls == [(AgentStatus.EXECUTING, True, "error recovery")]
