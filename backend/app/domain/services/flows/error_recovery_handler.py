"""Error state management and recovery logic for PlanActFlow.

Encapsulates the error recovery state machine: classifying errors,
tracking recovery attempts across cycles, injecting recovery prompts,
and deciding whether to restore a previous flow state or give up.

Usage:
    handler = ErrorRecoveryHandler()
    handler.record_error(exception, current_status)
    recovered = await handler.attempt_recovery(transition_fn, inject_recovery_fn)
    handler.reset_cycle_counter()       # called on successful forward transition

This is a pure domain service with zero infrastructure imports.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.domain.models.state_model import AgentStatus
    from app.domain.services.agents.error_handler import ErrorContext, ErrorHandler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Callback protocols — narrow interfaces the flow must satisfy
# ---------------------------------------------------------------------------


class TransitionFn(Protocol):
    """Callback to perform a state transition on the owning flow."""

    def __call__(self, new_status: AgentStatus, *, force: bool = False, reason: str = "") -> None: ...


class InjectRecoveryFn(Protocol):
    """Callback to inject a recovery prompt into the executor's memory."""

    def __call__(self, prompt: str) -> None: ...


class ErrorRecoveryHandler:
    """Owns the error recovery state machine extracted from PlanActFlow.

    Responsibilities:
    - Classify exceptions via ``ErrorHandler`` and store ``ErrorContext``
    - Track per-cycle and total error counts with configurable limits
    - Decide recoverability and generate recovery prompts
    - Restore the previous flow state on successful recovery

    The handler does NOT import any infrastructure or flow class.
    State transitions and memory injection are delegated via callbacks.
    """

    __slots__ = (
        "_error_context",
        "_error_handler",
        "_error_recovery_attempts",
        "_max_error_recovery_attempts",
        "_max_total_errors",
        "_previous_status",
        "_total_error_count",
    )

    def __init__(
        self,
        error_handler: ErrorHandler,
        *,
        max_recovery_attempts: int = 3,
        max_total_errors: int = 10,
    ) -> None:
        self._error_handler: ErrorHandler = error_handler
        self._error_context: ErrorContext | None = None
        self._previous_status: AgentStatus | None = None  # type: ignore[assignment]
        self._error_recovery_attempts: int = 0
        self._total_error_count: int = 0
        self._max_error_recovery_attempts: int = max_recovery_attempts
        self._max_total_errors: int = max_total_errors

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def error_handler(self) -> ErrorHandler:
        """Expose the shared ``ErrorHandler`` for callers that need it (e.g. ErrorIntegrationBridge)."""
        return self._error_handler

    @property
    def error_context(self) -> ErrorContext | None:  # type: ignore[override]
        """Current error context, or None if no error has been recorded."""
        return self._error_context

    @property
    def previous_status(self) -> AgentStatus | None:
        """Flow status captured before transitioning to ERROR."""
        return self._previous_status

    @property
    def total_error_count(self) -> int:
        return self._total_error_count

    @property
    def error_recovery_attempts(self) -> int:
        return self._error_recovery_attempts

    # ── Error Recording ────────────────────────────────────────────────

    def record_error(self, exception: Exception, current_status: AgentStatus) -> ErrorContext:
        """Classify *exception* and snapshot the current flow status.

        This replaces the two-line pattern scattered across ``state_context``
        and the main ``except`` block::

            self._previous_status = old_status
            self._error_context = self._error_handler.classify_error(e)

        Returns:
            The newly created ``ErrorContext`` for immediate use by callers.
        """
        self._error_context = self._error_handler.classify_error(exception)
        self._previous_status = current_status
        return self._error_context

    def record_error_context(self, error_context: ErrorContext, status: AgentStatus) -> None:
        """Record a manually-constructed ``ErrorContext`` (e.g. from ErrorEvent).

        Used when an ``ErrorEvent`` is received that bypasses Python's exception
        mechanism (the summarization error-bridge pattern).
        """
        self._error_context = error_context
        self._previous_status = status

    # ── Recovery Attempt ───────────────────────────────────────────────

    async def attempt_recovery(
        self,
        current_flow_status: AgentStatus,
        transition_fn: TransitionFn,
        inject_recovery_fn: InjectRecoveryFn | None = None,
    ) -> bool:
        """Attempt to recover from an ERROR state.

        Mirrors the original ``handle_error_state()`` logic:

        1. Check that we're in ERROR and have an error context.
        2. Enforce total-error and per-cycle limits.
        3. If the error is recoverable and a previous status exists,
           inject a recovery prompt and transition back.

        Args:
            current_flow_status: The flow's current ``AgentStatus`` (should be ERROR).
            transition_fn: Callback to perform the state transition.
            inject_recovery_fn: Optional callback to inject a recovery prompt
                into the executor's conversation memory.

        Returns:
            True if recovery succeeded (flow transitioned back), False otherwise.
        """
        from app.domain.models.state_model import AgentStatus

        if current_flow_status != AgentStatus.ERROR:
            return True

        if not self._error_context:
            logger.error("No error context available for recovery")
            return False

        # Absolute error cap across all recovery cycles
        self._total_error_count += 1
        if self._total_error_count >= self._max_total_errors:
            logger.error(f"Max total errors ({self._max_total_errors}) reached across all recovery cycles")
            return False

        # Per-cycle cap
        if self._error_recovery_attempts >= self._max_error_recovery_attempts:
            logger.error(f"Max recovery attempts ({self._max_error_recovery_attempts}) reached")
            return False

        self._error_recovery_attempts += 1
        logger.info(f"Attempting error recovery ({self._error_recovery_attempts}/{self._max_error_recovery_attempts})")

        # Recoverable + previous status available → restore
        if self._error_context.recoverable and self._previous_status:
            recovery_prompt = self._error_handler.get_recovery_prompt(self._error_context)
            if recovery_prompt and inject_recovery_fn is not None:
                try:
                    inject_recovery_fn(recovery_prompt)
                    logger.info(f"Injected recovery prompt for {self._error_context.error_type.value}")
                except Exception as e:
                    logger.debug(f"Could not inject recovery prompt: {e}")

            transition_fn(self._previous_status, force=True, reason="error recovery")
            self._previous_status = None
            logger.info("Recovered to previous state via error recovery handler")
            return True

        return False

    # ── Counter Management ─────────────────────────────────────────────

    def reset_cycle_counter(self) -> None:
        """Reset per-cycle recovery attempts.

        Called by ``_transition_to()`` when the flow successfully enters
        ``AgentStatus.EXECUTING``, indicating a fresh execution cycle.
        """
        self._error_recovery_attempts = 0

    def reset_all(self) -> None:
        """Full reset of all error state (e.g. for a new run)."""
        self._error_context = None
        self._previous_status = None
        self._error_recovery_attempts = 0
        self._total_error_count = 0
