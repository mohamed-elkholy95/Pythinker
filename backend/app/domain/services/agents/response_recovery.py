"""Response Recovery Policy Service

Implements malformed response detection and recovery strategies.
"""

import json
import logging
import re
import time
from datetime import UTC
from typing import Any, ClassVar

from app.domain.models.recovery import (
    RecoveryAttempt,
    RecoveryBudgetExhaustedError,
    RecoveryDecision,
    RecoveryReason,
    RecoveryStrategy,
)
from app.infrastructure.observability.agent_metrics import (
    agent_response_recovery_failure,
    agent_response_recovery_success,
    agent_response_recovery_trigger,
    recovery_duration,
)

logger = logging.getLogger(__name__)


class ResponseRecoveryPolicy:
    """Policy for detecting and recovering from malformed LLM responses.

    Implements:
    - Malformed response detection (JSON, refusals, empty)
    - Recovery budget enforcement
    - Strategy selection
    - Metrics tracking
    """

    # Refusal patterns to detect
    REFUSAL_PATTERNS: ClassVar[list[str]] = [
        r"I cannot help",
        r"I can't help",
        r"I am not able to",
        r"I'm not able to",
        r"I don't have access to",
        r"I cannot provide",
        r"I can't provide",
        r"I'm sorry, but I cannot",
        r"I apologize, but I cannot",
    ]

    def __init__(
        self,
        max_retries: int = 3,
        rollback_threshold: int = 2,
        agent_type: str = "plan_act",
    ):
        """Initialize recovery policy.

        Args:
            max_retries: Maximum recovery attempts before exhaustion
            rollback_threshold: Attempts before switching to fallback strategy
            agent_type: Type of agent for metrics labeling
        """
        self.max_retries = max_retries
        self.rollback_threshold = rollback_threshold
        self.agent_type = agent_type

        self._recovery_history: list[RecoveryAttempt] = []

    async def detect_malformed(self, response_text: str | None) -> RecoveryDecision:
        """Detect if response is malformed and should be recovered.

        Args:
            response_text: LLM response to check

        Returns:
            RecoveryDecision: Whether recovery is needed and why
        """
        # Empty response check
        if not response_text or response_text.strip() == "":
            reason = RecoveryReason.EMPTY_RESPONSE
            logger.warning(f"Detected {reason.value}: response is empty")
            return RecoveryDecision(
                should_recover=True,
                recovery_reason=reason,
                strategy=self._select_strategy(reason),
                retry_count=len(self._recovery_history),
                message="Response is empty",
            )

        # Null response check
        if response_text.strip().lower() in ("null", "none"):
            reason = RecoveryReason.NULL_RESPONSE
            logger.warning(f"Detected {reason.value}: {response_text}")
            return RecoveryDecision(
                should_recover=True,
                recovery_reason=reason,
                strategy=self._select_strategy(reason),
                retry_count=len(self._recovery_history),
                message=f"Response is null: {response_text}",
            )

        # JSON parsing check
        json_reason = self._check_json_parsing(response_text)
        if json_reason:
            logger.warning(f"Detected {json_reason.value}: invalid JSON")
            return RecoveryDecision(
                should_recover=True,
                recovery_reason=json_reason,
                strategy=self._select_strategy(json_reason),
                retry_count=len(self._recovery_history),
                message="JSON parsing failed",
            )

        # Refusal pattern check
        refusal_reason = self._check_refusal_patterns(response_text)
        if refusal_reason:
            logger.warning(f"Detected {refusal_reason.value}: refusal pattern matched")
            return RecoveryDecision(
                should_recover=True,
                recovery_reason=refusal_reason,
                strategy=self._select_strategy(refusal_reason),
                retry_count=len(self._recovery_history),
                message="Refusal pattern detected",
            )

        # No issues detected
        return RecoveryDecision(
            should_recover=False,
            recovery_reason=RecoveryReason.JSON_PARSING_FAILED,  # Placeholder
            strategy=RecoveryStrategy.ROLLBACK_RETRY,
            retry_count=len(self._recovery_history),
            message="Response is valid",
        )

    def _check_json_parsing(self, response_text: str) -> RecoveryReason | None:
        """Check if response contains valid JSON.

        Args:
            response_text: Response to check

        Returns:
            RecoveryReason if malformed, None if valid
        """
        try:
            # Try to parse as JSON
            json.loads(response_text)
            return None
        except json.JSONDecodeError:
            # Check if it looks like incomplete JSON
            if response_text.strip().startswith(("{", "[")):
                return RecoveryReason.JSON_PARSING_FAILED
            # Otherwise might not be JSON response at all
            return None

    def _check_refusal_patterns(self, response_text: str) -> RecoveryReason | None:
        """Check if response matches refusal patterns.

        Args:
            response_text: Response to check

        Returns:
            RecoveryReason if refusal detected, None otherwise
        """
        for pattern in self.REFUSAL_PATTERNS:
            if re.search(pattern, response_text, re.IGNORECASE):
                return RecoveryReason.REFUSAL_DETECTED

        return None

    def _select_strategy(self, reason: RecoveryReason) -> RecoveryStrategy:
        """Select recovery strategy based on reason and history.

        Args:
            reason: Why recovery is needed

        Returns:
            RecoveryStrategy: Strategy to use
        """
        retry_count = len(self._recovery_history)

        # If we've exhausted retries, use terminal error
        if retry_count >= self.max_retries:
            return RecoveryStrategy.TERMINAL_ERROR

        # If we've hit rollback threshold, try simplified prompt
        if retry_count >= self.rollback_threshold:
            return RecoveryStrategy.SIMPLIFIED_PROMPT

        # Default: rollback and retry
        return RecoveryStrategy.ROLLBACK_RETRY

    async def execute_recovery(
        self,
        response_text: str | None,
        recovery_reason: RecoveryReason,
        strategy: RecoveryStrategy,
    ) -> tuple[bool, str]:
        """Execute recovery strategy.

        Args:
            response_text: The malformed response
            recovery_reason: Why recovery is needed
            strategy: Which strategy to use

        Returns:
            tuple[bool, str]: (success, message)

        Raises:
            RecoveryBudgetExhaustedError: If budget exhausted
        """
        attempt_number = len(self._recovery_history) + 1

        # Check budget
        if attempt_number > self.max_retries:
            # Track failure
            agent_response_recovery_failure.inc(
                labels={
                    "recovery_reason": recovery_reason.value,
                    "agent_type": self.agent_type,
                }
            )

            raise RecoveryBudgetExhaustedError(
                attempt_count=attempt_number - 1,
                max_retries=self.max_retries,
                recovery_reason=recovery_reason,
            )

        # Track recovery trigger
        agent_response_recovery_trigger.inc(
            labels={
                "recovery_reason": recovery_reason.value,
                "agent_type": self.agent_type,
            }
        )

        # Start timing
        start_time = time.time()

        try:
            # Execute strategy
            if strategy == RecoveryStrategy.TERMINAL_ERROR:
                return False, "Recovery budget exhausted"

            # For now, all strategies succeed (actual implementation in integration)
            success = True
            message = f"Recovery successful using {strategy.value}"

            # Track duration
            duration = time.time() - start_time
            recovery_duration.observe(
                labels={"recovery_reason": recovery_reason.value},
                value=duration,
            )

            # Track success
            agent_response_recovery_success.inc(
                labels={
                    "recovery_strategy": strategy.value,
                    "retry_count": str(attempt_number),
                }
            )

            # Record attempt
            from datetime import datetime

            attempt = RecoveryAttempt(
                attempt_number=attempt_number,
                recovery_reason=recovery_reason,
                strategy_used=strategy,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                success=success,
                error_message=None if success else message,
            )
            self._recovery_history.append(attempt)

            return success, message

        except Exception as e:
            # Track duration even on failure
            duration = time.time() - start_time
            recovery_duration.observe(
                labels={"recovery_reason": recovery_reason.value},
                value=duration,
            )

            logger.error(f"Recovery failed: {e}")
            return False, str(e)

    async def cleanup(self) -> None:
        """Clean up resources (for testing)."""
        self._recovery_history.clear()

    def get_recovery_stats(self) -> dict[str, Any]:
        """Get recovery statistics.

        Returns:
            dict: Recovery stats
        """
        return {
            "total_attempts": len(self._recovery_history),
            "successful_attempts": sum(1 for a in self._recovery_history if a.success),
            "failed_attempts": sum(1 for a in self._recovery_history if not a.success),
            "budget_remaining": max(0, self.max_retries - len(self._recovery_history)),
        }
