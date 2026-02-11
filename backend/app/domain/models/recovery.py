"""Response Recovery Domain Models

Models for response recovery policy and decisions.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class RecoveryReason(str, Enum):
    """Reasons for triggering response recovery."""

    JSON_PARSING_FAILED = "json_parsing_failed"
    REFUSAL_DETECTED = "refusal_detected"
    EMPTY_RESPONSE = "empty_response"
    NULL_RESPONSE = "null_response"
    MALFORMED_TOOL_CALL = "malformed_tool_call"
    VALIDATION_ERROR = "validation_error"


class RecoveryStrategy(str, Enum):
    """Recovery strategies available."""

    ROLLBACK_RETRY = "rollback_retry"
    SIMPLIFIED_PROMPT = "simplified_prompt"
    FALLBACK_RESPONSE = "fallback_response"
    TERMINAL_ERROR = "terminal_error"


class RecoveryDecision(BaseModel):
    """Decision outcome from recovery policy.

    Attributes:
        should_recover: Whether recovery should be attempted
        recovery_reason: Why recovery is needed
        strategy: Which recovery strategy to use
        retry_count: Current retry attempt number
        message: Human-readable explanation
    """

    should_recover: bool
    recovery_reason: RecoveryReason
    strategy: RecoveryStrategy
    retry_count: int = Field(ge=0)
    message: str

    @field_validator("retry_count")
    @classmethod
    def validate_retry_count(cls, v: int) -> int:
        """Ensure retry count is non-negative."""
        if v < 0:
            raise ValueError("retry_count must be non-negative")
        return v


class RecoveryAttempt(BaseModel):
    """Record of a recovery attempt.

    Attributes:
        attempt_number: Which retry attempt this is (1-indexed)
        recovery_reason: Why recovery was triggered
        strategy_used: Which recovery strategy was applied
        start_time: When recovery started
        end_time: When recovery completed (None if in progress)
        success: Whether recovery succeeded (None if in progress)
        error_message: Error message if recovery failed
    """

    attempt_number: int = Field(ge=1)
    recovery_reason: RecoveryReason
    strategy_used: RecoveryStrategy
    start_time: datetime
    end_time: datetime | None = None
    success: bool | None = None
    error_message: str | None = None

    @field_validator("attempt_number")
    @classmethod
    def validate_attempt_number(cls, v: int) -> int:
        """Ensure attempt number is positive."""
        if v < 1:
            raise ValueError("attempt_number must be >= 1")
        return v


class RecoveryBudgetExhaustedError(Exception):
    """Raised when recovery budget is exhausted.

    Attributes:
        attempt_count: Number of recovery attempts made
        max_retries: Maximum retries allowed
        recovery_reason: What triggered the recoveries
        cooldown_seconds: Suggested cooldown period
    """

    def __init__(
        self,
        attempt_count: int,
        max_retries: int,
        recovery_reason: RecoveryReason,
        cooldown_seconds: int = 60,
    ):
        self.attempt_count = attempt_count
        self.max_retries = max_retries
        self.recovery_reason = recovery_reason
        self.cooldown_seconds = cooldown_seconds

        super().__init__(
            f"Recovery budget exhausted: {attempt_count} attempts made "
            f"(max: {max_retries}) for reason: {recovery_reason.value}. "
            f"Suggested cooldown: {cooldown_seconds}s"
        )


class MalformedResponseError(Exception):
    """Raised when LLM response is malformed and cannot be recovered.

    Attributes:
        response_text: The malformed response
        detection_reason: Why it was classified as malformed
        raw_error: Original error that triggered detection
    """

    def __init__(
        self,
        response_text: str,
        detection_reason: RecoveryReason,
        raw_error: Exception | None = None,
    ):
        self.response_text = response_text
        self.detection_reason = detection_reason
        self.raw_error = raw_error

        super().__init__(f"Malformed response detected ({detection_reason.value}): {response_text[:100]}...")
