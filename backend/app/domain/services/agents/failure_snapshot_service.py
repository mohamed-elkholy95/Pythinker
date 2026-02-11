"""Failure Snapshot Service

Generates and manages failure snapshots for retry quality improvement.
"""

import logging
from typing import Any

from app.domain.models.failure_snapshot import FailureSnapshot
from app.infrastructure.observability.agent_metrics import (
    failure_snapshot_budget_violations,
    failure_snapshot_generated,
    failure_snapshot_injected,
    failure_snapshot_size,
)

logger = logging.getLogger(__name__)


class FailureSnapshotService:
    """Service for generating and managing failure snapshots.

    Implements:
    - Snapshot generation from failures
    - Adaptive truncation based on context pressure
    - Retry context injection
    - Metrics tracking
    """

    def __init__(
        self,
        token_budget: int = 300,
        pressure_threshold: float = 0.8,
    ):
        """Initialize failure snapshot service.

        Args:
            token_budget: Maximum tokens per snapshot
            pressure_threshold: Context pressure threshold for minimal snapshots
        """
        self.token_budget = token_budget
        self.pressure_threshold = pressure_threshold

    async def generate_snapshot(
        self,
        failed_step: str,
        error: Exception,
        tool_call_context: dict[str, Any] | None = None,
        retry_count: int = 0,
        context_pressure: float = 0.0,
    ) -> FailureSnapshot:
        """Generate failure snapshot from error.

        Args:
            failed_step: Name of step that failed
            error: The exception that occurred
            tool_call_context: Tool call details
            retry_count: Current retry count
            context_pressure: Estimated context window pressure (0-1)

        Returns:
            FailureSnapshot: Generated snapshot
        """
        error_type = type(error).__name__
        error_message = str(error)
        tool_context = tool_call_context or {}

        # Use adaptive generation based on context pressure
        if context_pressure > self.pressure_threshold:
            logger.info(f"High context pressure ({context_pressure:.2f}), generating minimal snapshot")
            snapshot = FailureSnapshot.minimal(
                error_type=error_type,
                retry_count=retry_count,
            )
        else:
            snapshot = FailureSnapshot.full(
                failed_step=failed_step,
                error_type=error_type,
                error_message=error_message,
                tool_call_context=tool_context,
                retry_count=retry_count,
                context_pressure=context_pressure,
            )

        # Track metrics
        failure_snapshot_generated.inc(
            labels={
                "failure_type": error_type,
                "step_name": failed_step,
            }
        )

        # Track snapshot size
        snapshot_tokens = snapshot.calculate_size_tokens()
        failure_snapshot_size.observe(
            labels={},
            value=float(snapshot_tokens),
        )

        # Track budget violations
        if snapshot_tokens > self.token_budget:
            logger.warning(f"Snapshot exceeds token budget: {snapshot_tokens} > {self.token_budget}")
            failure_snapshot_budget_violations.inc(labels={"violation_type": "token_budget_exceeded"})

        logger.info(f"Generated failure snapshot: {error_type} ({snapshot_tokens} tokens, retry {retry_count})")

        return snapshot

    async def inject_into_retry(
        self,
        snapshot: FailureSnapshot,
        base_prompt: str,
    ) -> str:
        """Inject snapshot into retry prompt.

        Args:
            snapshot: Failure snapshot to inject
            base_prompt: Base prompt for retry

        Returns:
            str: Enhanced prompt with snapshot context
        """
        # Track injection
        failure_snapshot_injected.inc(labels={"retry_count": str(snapshot.retry_count)})

        # Build enhanced prompt
        snapshot_context = snapshot.to_retry_context()
        enhanced_prompt = f"{snapshot_context}\n\n---\n\n{base_prompt}"

        logger.debug(f"Injected snapshot into retry (retry count: {snapshot.retry_count})")

        return enhanced_prompt

    def should_generate_snapshot(
        self,
        error: Exception,
        retry_count: int,
        max_retries: int,
    ) -> bool:
        """Determine if snapshot should be generated.

        Args:
            error: The error that occurred
            retry_count: Current retry count
            max_retries: Maximum retries allowed

        Returns:
            bool: True if snapshot should be generated
        """
        # Don't generate for last retry (no more retries after)
        if retry_count >= max_retries:
            return False

        # Don't generate for certain error types (extend as needed)
        skip_types = (KeyboardInterrupt, SystemExit)
        return not isinstance(error, skip_types)

    async def calculate_context_pressure(
        self,
        current_tokens: int,
        max_tokens: int,
    ) -> float:
        """Calculate context window pressure.

        Args:
            current_tokens: Current tokens in context
            max_tokens: Maximum tokens allowed

        Returns:
            float: Pressure ratio (0-1)
        """
        if max_tokens <= 0:
            return 0.0

        pressure = current_tokens / max_tokens
        return min(1.0, max(0.0, pressure))
