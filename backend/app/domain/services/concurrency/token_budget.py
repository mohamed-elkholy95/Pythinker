"""Token Budget Tracker for enforcing per-session token limits.

Phase 6: P3 Architecture - Token Budget Enforcement

This module tracks token usage across LLM calls within a session and
enforces the max_tokens_per_run limit to prevent runaway costs.

Usage:
    budget = get_token_budget(session_id)
    budget.reserve(estimated_tokens)
    try:
        response = await llm.chat(messages)
        budget.consume(actual_tokens)
    except Exception:
        budget.release_reservation()
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency
_metrics_imported = False
_update_token_budget = None


def _import_metrics() -> None:
    """Lazy import metrics to avoid circular imports."""
    global _metrics_imported, _update_token_budget
    if not _metrics_imported:
        try:
            from app.domain.external.observability import get_null_metrics

            # Get the metrics instance and create a wrapper function
            _metrics_instance = get_null_metrics()

            def _wrapper(session_id: str, used: int, remaining: int) -> None:
                _metrics_instance.update_token_budget(used, remaining)

            _update_token_budget = _wrapper
        except ImportError:
            pass
        _metrics_imported = True


class TokenBudgetExceededError(Exception):
    """Raised when token budget is exceeded."""

    def __init__(
        self,
        message: str,
        used: int,
        limit: int,
        requested: int = 0,
    ):
        super().__init__(message)
        self.used = used
        self.limit = limit
        self.requested = requested


@dataclass
class TokenUsage:
    """Track token usage breakdown."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    last_updated: float = field(default_factory=time.time)

    def add(
        self,
        prompt: int = 0,
        completion: int = 0,
        cached: int = 0,
    ) -> None:
        """Add token usage."""
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cached_tokens += cached
        self.total_tokens += prompt + completion
        self.llm_calls += 1
        self.last_updated = time.time()


class TokenBudget:
    """Token budget tracker for a single session.

    Tracks token usage and enforces limits to prevent runaway costs.
    Supports reservation pattern for optimistic allocation.

    Attributes:
        session_id: Session identifier
        max_tokens: Maximum tokens allowed
        used: Current tokens used
        reserved: Tokens reserved but not yet consumed
    """

    def __init__(
        self,
        session_id: str,
        max_tokens: int | None = None,
        warn_threshold: float = 0.8,
    ):
        """Initialize token budget.

        Args:
            session_id: Session identifier
            max_tokens: Maximum tokens allowed (default from settings)
            warn_threshold: Threshold (0-1) at which to warn about budget
        """
        from app.core.config import get_settings

        settings = get_settings()

        self._session_id = session_id
        self._max_tokens = max_tokens or settings.max_tokens_per_run
        self._warn_threshold = warn_threshold
        self._usage = TokenUsage()
        self._reserved = 0
        self._warned = False

        logger.debug(f"Token budget initialized for session {session_id}: max={self._max_tokens}")

    @property
    def session_id(self) -> str:
        """Session identifier."""
        return self._session_id

    @property
    def max_tokens(self) -> int:
        """Maximum tokens allowed."""
        return self._max_tokens

    @property
    def used(self) -> int:
        """Total tokens used."""
        return self._usage.total_tokens

    @property
    def reserved(self) -> int:
        """Tokens reserved but not consumed."""
        return self._reserved

    @property
    def remaining(self) -> int:
        """Tokens remaining in budget."""
        return max(0, self._max_tokens - self._usage.total_tokens - self._reserved)

    @property
    def usage(self) -> TokenUsage:
        """Detailed usage breakdown."""
        return self._usage

    @property
    def utilization(self) -> float:
        """Budget utilization (0-1)."""
        if self._max_tokens == 0:
            return 0.0
        return (self._usage.total_tokens + self._reserved) / self._max_tokens

    def _update_metrics(self) -> None:
        """Update Prometheus metrics."""
        _import_metrics()
        if _update_token_budget:
            _update_token_budget(
                self._session_id,
                self._usage.total_tokens,
                self.remaining,
            )

    def _check_warn(self) -> None:
        """Check if we should warn about budget utilization."""
        if not self._warned and self.utilization >= self._warn_threshold:
            self._warned = True
            logger.warning(
                f"Token budget warning for session {self._session_id}: "
                f"{self.utilization:.0%} used ({self._usage.total_tokens}/{self._max_tokens})"
            )

    def can_use(self, tokens: int) -> bool:
        """Check if tokens can be used within budget.

        Args:
            tokens: Number of tokens to check

        Returns:
            True if tokens can be used without exceeding budget
        """
        return self._usage.total_tokens + self._reserved + tokens <= self._max_tokens

    def reserve(self, tokens: int, strict: bool = True) -> bool:
        """Reserve tokens for an upcoming operation.

        Use this before making an LLM call to ensure budget is available.
        Call consume() with actual tokens after the call completes,
        or release_reservation() if the call fails.

        Args:
            tokens: Number of tokens to reserve
            strict: If True, raise exception if budget exceeded

        Returns:
            True if reservation successful

        Raises:
            TokenBudgetExceeded: If strict=True and budget exceeded
        """
        if not self.can_use(tokens):
            if strict:
                raise TokenBudgetExceededError(
                    f"Token budget exceeded for session {self._session_id}: "
                    f"used={self._usage.total_tokens}, reserved={self._reserved}, "
                    f"requested={tokens}, limit={self._max_tokens}",
                    used=self._usage.total_tokens,
                    limit=self._max_tokens,
                    requested=tokens,
                )
            return False

        self._reserved += tokens
        self._check_warn()
        self._update_metrics()
        return True

    def release_reservation(self, tokens: int | None = None) -> None:
        """Release reserved tokens (e.g., if operation failed).

        Args:
            tokens: Number of tokens to release (default: all reserved)
        """
        if tokens is None:
            self._reserved = 0
        else:
            self._reserved = max(0, self._reserved - tokens)
        self._update_metrics()

    def consume(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
        release_reservation: bool = True,
    ) -> None:
        """Consume tokens after an LLM call.

        Args:
            prompt_tokens: Prompt tokens used
            completion_tokens: Completion tokens used
            cached_tokens: Cached tokens (don't count toward limit)
            release_reservation: Whether to release any reservation
        """
        total = prompt_tokens + completion_tokens
        self._usage.add(
            prompt=prompt_tokens,
            completion=completion_tokens,
            cached=cached_tokens,
        )

        if release_reservation:
            self._reserved = max(0, self._reserved - total)

        self._check_warn()
        self._update_metrics()

        logger.debug(
            f"Token budget update for session {self._session_id}: "
            f"+{total} tokens (total: {self._usage.total_tokens}/{self._max_tokens})"
        )

    def reset(self) -> None:
        """Reset the token budget (for testing or new runs)."""
        self._usage = TokenUsage()
        self._reserved = 0
        self._warned = False
        self._update_metrics()
        logger.debug(f"Token budget reset for session {self._session_id}")

    def get_status(self) -> dict[str, Any]:
        """Get current budget status.

        Returns:
            Dictionary with budget status
        """
        return {
            "session_id": self._session_id,
            "max_tokens": self._max_tokens,
            "used_tokens": self._usage.total_tokens,
            "reserved_tokens": self._reserved,
            "remaining_tokens": self.remaining,
            "utilization": round(self.utilization, 3),
            "usage": {
                "prompt_tokens": self._usage.prompt_tokens,
                "completion_tokens": self._usage.completion_tokens,
                "cached_tokens": self._usage.cached_tokens,
                "llm_calls": self._usage.llm_calls,
            },
        }


# Session-based budget storage
_session_budgets: dict[str, TokenBudget] = {}


def get_token_budget(session_id: str, **kwargs: Any) -> TokenBudget:
    """Get or create a token budget for a session.

    Args:
        session_id: Session identifier
        **kwargs: Additional arguments for TokenBudget constructor

    Returns:
        TokenBudget instance for the session
    """
    if session_id not in _session_budgets:
        _session_budgets[session_id] = TokenBudget(session_id, **kwargs)
    return _session_budgets[session_id]


def remove_token_budget(session_id: str) -> bool:
    """Remove a token budget for a session.

    Args:
        session_id: Session identifier

    Returns:
        True if budget was removed, False if not found
    """
    if session_id in _session_budgets:
        del _session_budgets[session_id]
        return True
    return False


def get_all_budgets() -> dict[str, TokenBudget]:
    """Get all active token budgets.

    Returns:
        Dictionary mapping session IDs to budgets
    """
    return _session_budgets.copy()


def clear_all_budgets() -> None:
    """Clear all token budgets (for testing)."""
    _session_budgets.clear()
