"""Per-task LLM retry budget (domain layer).

Tracks how many LLM retries each task has consumed and blocks further
retries when the budget is exhausted.  Uses a token-bucket algorithm for
rate limiting across all tasks.

This prevents a single task (or a cascade of nested retries) from
consuming all available API quota.

Usage::

    budget = get_retry_budget()
    if budget.can_retry(task_id):
        # proceed with retry
    else:
        raise RuntimeError("retry budget exhausted")
    budget.record_retry(task_id, provider="openai", error_type="TimeoutError")
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RetryBudgetUsage:
    """Snapshot of retry usage for a single task."""

    task_id: str
    total_retries: int = 0
    retries_by_provider: dict[str, int] = field(default_factory=dict)
    retries_by_error: dict[str, int] = field(default_factory=dict)
    budget_exhausted: bool = False


class RetryBudget:
    """Token-bucket retry budget tracker.

    Enforces two limits:
    1. ``max_retries_per_task`` — lifetime cap for a single task_id.
    2. ``max_retries_per_minute`` — sliding-window rate limit across all tasks.

    Thread-safe (uses a single lock; fine-grained enough for the expected
    call volume from async LLM callers that yield between retries).

    Args:
        max_retries_per_task: Maximum total LLM retries allowed per task.
        max_retries_per_minute: Maximum retries across all tasks per minute.
    """

    def __init__(
        self,
        max_retries_per_task: int = 15,
        max_retries_per_minute: int = 30,
    ) -> None:
        self._max_per_task = max_retries_per_task
        self._max_per_minute = max_retries_per_minute

        # Per-task counters: task_id → RetryBudgetUsage
        self._task_usage: dict[str, RetryBudgetUsage] = defaultdict(
            lambda: RetryBudgetUsage(task_id="")
        )
        # Sliding-window timestamps for the global rate limit
        self._global_retry_times: list[float] = []
        self._lock = threading.Lock()

    def can_retry(self, task_id: str) -> bool:
        """Return True if a retry is allowed for this task.

        Checks both the per-task cap and the per-minute global rate limit.
        Does NOT record the retry — call ``record_retry`` after the attempt.
        """
        with self._lock:
            usage = self._task_usage[task_id]
            usage.task_id = task_id
            if usage.budget_exhausted:
                return False
            if usage.total_retries >= self._max_per_task:
                usage.budget_exhausted = True
                logger.warning(
                    "Retry budget exhausted for task_id=%s (total=%d/%d)",
                    task_id,
                    usage.total_retries,
                    self._max_per_task,
                )
                return False

            # Sliding-window rate check
            now = time.monotonic()
            cutoff = now - 60.0
            # Prune old entries
            self._global_retry_times = [t for t in self._global_retry_times if t > cutoff]
            if len(self._global_retry_times) >= self._max_per_minute:
                logger.warning(
                    "Global LLM retry rate limit reached (%d retries in last 60s, max=%d)",
                    len(self._global_retry_times),
                    self._max_per_minute,
                )
                return False

            return True

    def record_retry(
        self,
        task_id: str,
        provider: str = "unknown",
        error_type: str = "unknown",
    ) -> None:
        """Record that one retry was consumed for this task."""
        with self._lock:
            usage = self._task_usage[task_id]
            usage.task_id = task_id
            usage.total_retries += 1
            usage.retries_by_provider[provider] = usage.retries_by_provider.get(provider, 0) + 1
            usage.retries_by_error[error_type] = usage.retries_by_error.get(error_type, 0) + 1
            self._global_retry_times.append(time.monotonic())

    def get_usage(self, task_id: str) -> RetryBudgetUsage:
        """Return a copy of the usage snapshot for a task."""
        with self._lock:
            usage = self._task_usage.get(task_id)
            if usage is None:
                return RetryBudgetUsage(task_id=task_id)
            return RetryBudgetUsage(
                task_id=usage.task_id,
                total_retries=usage.total_retries,
                retries_by_provider=dict(usage.retries_by_provider),
                retries_by_error=dict(usage.retries_by_error),
                budget_exhausted=usage.budget_exhausted,
            )

    def reset_task(self, task_id: str) -> None:
        """Clear the retry budget for a completed task (free memory)."""
        with self._lock:
            self._task_usage.pop(task_id, None)


# ─────────────────────────── Singleton ───────────────────────────────────────

_budget_instance: RetryBudget | None = None
_budget_lock = threading.Lock()


def get_retry_budget() -> RetryBudget:
    """Return the process-level singleton RetryBudget.

    Creates the instance on first call using settings values for the caps.
    Thread-safe.
    """
    global _budget_instance
    if _budget_instance is not None:
        return _budget_instance

    with _budget_lock:
        if _budget_instance is not None:
            return _budget_instance
        try:
            from app.core.config import get_settings

            settings = get_settings()
            per_task = getattr(settings, "llm_retry_budget_per_task", 15)
            per_minute = getattr(settings, "llm_retry_budget_per_minute", 30)
        except Exception:
            per_task = 15
            per_minute = 30

        _budget_instance = RetryBudget(
            max_retries_per_task=per_task,
            max_retries_per_minute=per_minute,
        )
        return _budget_instance


def reset_retry_budget() -> None:
    """Reset the singleton (for testing)."""
    global _budget_instance
    with _budget_lock:
        _budget_instance = None
