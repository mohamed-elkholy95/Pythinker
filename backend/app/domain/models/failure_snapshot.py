"""Failure Snapshot Domain Model

Structured failure context for retry quality improvement.
Implements token budget enforcement via Pydantic validators.
"""

from datetime import UTC, datetime
from typing import Any, ClassVar, Self

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.functional_validators import ModelWrapValidatorHandler


class FailureSnapshot(BaseModel):
    """Structured failure context for retry quality improvement.

    Attributes:
        failed_step: Name of the step that failed
        error_type: Type/category of error
        error_message: Error message (truncated to budget)
        tool_call_context: Tool call details (truncated if oversized)
        retry_count: Current retry attempt number
        timestamp: When the failure occurred
        context_pressure: Estimated context window pressure (0-1)
    """

    failed_step: str
    error_type: str
    error_message: str
    tool_call_context: dict[str, Any] = Field(default_factory=dict)
    retry_count: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    context_pressure: float = Field(default=0.0, ge=0.0, le=1.0)

    # Token budget configuration
    MAX_ERROR_MESSAGE_LENGTH: ClassVar[int] = 500
    MAX_TOTAL_TOKENS: ClassVar[int] = 300

    @field_validator("error_message")
    @classmethod
    def truncate_error_message(cls, v: str) -> str:
        """Cap error message to prevent token bloat.

        Args:
            v: Error message to validate

        Returns:
            str: Truncated error message
        """
        if len(v) > cls.MAX_ERROR_MESSAGE_LENGTH:
            return v[: cls.MAX_ERROR_MESSAGE_LENGTH] + "... [truncated]"
        return v

    @field_validator("retry_count")
    @classmethod
    def validate_retry_count(cls, v: int) -> int:
        """Ensure retry count is non-negative.

        Args:
            v: Retry count to validate

        Returns:
            int: Validated retry count

        Raises:
            ValueError: If retry_count is negative
        """
        if v < 0:
            raise ValueError("retry_count must be non-negative")
        return v

    @field_validator("context_pressure")
    @classmethod
    def validate_context_pressure(cls, v: float) -> float:
        """Ensure context pressure is between 0 and 1.

        Args:
            v: Context pressure to validate

        Returns:
            float: Validated context pressure

        Raises:
            ValueError: If context_pressure not in [0, 1]
        """
        if not 0.0 <= v <= 1.0:
            raise ValueError("context_pressure must be between 0.0 and 1.0")
        return v

    @model_validator(mode="wrap")
    @classmethod
    def enforce_token_budget(cls, data: Any, handler: ModelWrapValidatorHandler[Self]) -> Self:
        """Enforce total snapshot size under token budget.

        Uses model_validator in wrap mode to enforce cross-field constraints.
        Truncates tool_call_context if total size exceeds budget.

        Args:
            data: Raw input data
            handler: Pydantic validation handler

        Returns:
            Self: Validated instance with budget enforced
        """
        # Let Pydantic perform standard validation first
        instance = handler(data)

        # Calculate approximate token count (rough estimate: 4 chars = 1 token)
        serialized = instance.model_dump_json()
        approx_tokens = len(serialized) // 4

        if approx_tokens > cls.MAX_TOTAL_TOKENS:
            # Truncate tool_call_context to fit budget
            # Keep only first 3 items, truncate values to 100 chars
            instance.tool_call_context = {k: str(v)[:100] for k, v in list(instance.tool_call_context.items())[:3]}

        return instance

    @classmethod
    def minimal(cls, error_type: str, retry_count: int) -> "FailureSnapshot":
        """Create minimal snapshot for high context pressure.

        Args:
            error_type: Type of error
            retry_count: Current retry count

        Returns:
            FailureSnapshot: Minimal snapshot instance
        """
        return cls(
            failed_step="unknown",
            error_type=error_type,
            error_message="Error details omitted (context pressure)",
            tool_call_context={},
            retry_count=retry_count,
            context_pressure=1.0,
        )

    @classmethod
    def full(
        cls,
        failed_step: str,
        error_type: str,
        error_message: str,
        tool_call_context: dict[str, Any],
        retry_count: int,
        context_pressure: float = 0.0,
    ) -> "FailureSnapshot":
        """Create full snapshot with all context.

        Args:
            failed_step: Step that failed
            error_type: Type of error
            error_message: Error message
            tool_call_context: Tool call details
            retry_count: Retry count
            context_pressure: Context pressure (0-1)

        Returns:
            FailureSnapshot: Full snapshot instance
        """
        return cls(
            failed_step=failed_step,
            error_type=error_type,
            error_message=error_message,
            tool_call_context=tool_call_context,
            retry_count=retry_count,
            context_pressure=context_pressure,
        )

    def to_retry_context(self) -> str:
        """Convert snapshot to human-readable retry context.

        Returns:
            str: Formatted context for LLM prompt
        """
        context_parts = [
            "## Previous Attempt Failed",
            f"**Step**: {self.failed_step}",
            f"**Error Type**: {self.error_type}",
            f"**Error Message**: {self.error_message}",
            f"**Retry Count**: {self.retry_count}",
        ]

        if self.tool_call_context:
            context_parts.append("**Tool Context**:")
            for key, value in self.tool_call_context.items():
                context_parts.append(f"  - {key}: {value}")

        context_parts.append("\nPlease retry with the above context in mind.")

        return "\n".join(context_parts)

    def calculate_size_tokens(self) -> int:
        """Calculate approximate size in tokens.

        Returns:
            int: Approximate token count
        """
        serialized = self.model_dump_json()
        return len(serialized) // 4
