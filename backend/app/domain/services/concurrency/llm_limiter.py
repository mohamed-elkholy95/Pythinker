"""LLM Concurrency Limiter for preventing API quota exhaustion.

Phase 6: P3 Architecture - Concurrency Control

This module provides a semaphore-based limiter for concurrent LLM API calls,
preventing quota exhaustion under high load and providing queue management.

Usage:
    limiter = get_llm_limiter()
    async with limiter.acquire():
        response = await llm.chat(messages)
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency
_metrics_imported = False
_update_llm_concurrent_requests = None
_update_llm_queue_waiting = None


def _import_metrics() -> None:
    """Lazy import metrics to avoid circular imports."""
    global _metrics_imported, _update_llm_concurrent_requests, _update_llm_queue_waiting
    if not _metrics_imported:
        try:
            from app.infrastructure.observability.prometheus_metrics import (
                update_llm_concurrent_requests,
                update_llm_queue_waiting,
            )

            _update_llm_concurrent_requests = update_llm_concurrent_requests
            _update_llm_queue_waiting = update_llm_queue_waiting
        except ImportError:
            pass
        _metrics_imported = True


@dataclass
class LimiterStats:
    """Statistics for the LLM concurrency limiter."""

    total_requests: int = 0
    active_requests: int = 0
    queued_requests: int = 0
    completed_requests: int = 0
    rejected_requests: int = 0
    total_wait_time: float = 0.0
    max_wait_time: float = 0.0
    timeouts: int = 0


class LLMConcurrencyLimiter:
    """Semaphore-based concurrency limiter for LLM API calls.

    Prevents API quota exhaustion by limiting concurrent requests and
    providing queue management with optional timeout.

    Attributes:
        max_concurrent: Maximum concurrent LLM requests allowed
        queue_timeout: Maximum time to wait in queue (seconds)
        stats: Limiter statistics
    """

    _instance: "LLMConcurrencyLimiter | None" = None

    def __init__(
        self,
        max_concurrent: int | None = None,
        queue_timeout: float | None = None,
    ):
        """Initialize the concurrency limiter.

        Args:
            max_concurrent: Maximum concurrent requests (default from settings)
            queue_timeout: Timeout for queue waiting in seconds (default 120s)
        """
        from app.core.config import get_settings

        settings = get_settings()

        self._max_concurrent = max_concurrent or getattr(settings, "llm_max_concurrent", 5)
        self._queue_timeout = queue_timeout or getattr(settings, "llm_queue_timeout", 120.0)
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._lock = asyncio.Lock()
        self._stats = LimiterStats()
        self._queued = 0

        logger.info(
            f"LLM Concurrency Limiter initialized: max_concurrent={self._max_concurrent}, "
            f"queue_timeout={self._queue_timeout}s"
        )

    @classmethod
    def get_instance(cls, **kwargs: Any) -> "LLMConcurrencyLimiter":
        """Get the singleton limiter instance."""
        if cls._instance is None:
            cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None

    @property
    def max_concurrent(self) -> int:
        """Maximum concurrent requests allowed."""
        return self._max_concurrent

    @property
    def queue_timeout(self) -> float:
        """Queue timeout in seconds."""
        return self._queue_timeout

    @property
    def stats(self) -> LimiterStats:
        """Get limiter statistics."""
        return self._stats

    @property
    def active_count(self) -> int:
        """Current number of active (running) requests."""
        return self._stats.active_requests

    @property
    def queued_count(self) -> int:
        """Current number of queued (waiting) requests."""
        return self._queued

    def _update_metrics(self) -> None:
        """Update Prometheus metrics."""
        _import_metrics()
        if _update_llm_concurrent_requests:
            _update_llm_concurrent_requests(self._stats.active_requests)
        if _update_llm_queue_waiting:
            _update_llm_queue_waiting(self._queued)

    @asynccontextmanager
    async def acquire(self, timeout: float | None = None):
        """Acquire a slot for an LLM request.

        Args:
            timeout: Custom timeout for this request (overrides default)

        Yields:
            None when slot is acquired

        Raises:
            asyncio.TimeoutError: If queue timeout is exceeded
            LLMConcurrencyLimitError: If the limiter is at capacity and timeout is 0
        """
        effective_timeout = timeout if timeout is not None else self._queue_timeout
        start_time = time.monotonic()

        async with self._lock:
            self._stats.total_requests += 1
            self._queued += 1
            self._update_metrics()

        try:
            # Try to acquire semaphore with timeout
            try:
                await asyncio.wait_for(
                    self._semaphore.acquire(),
                    timeout=effective_timeout if effective_timeout > 0 else None,
                )
            except TimeoutError:
                async with self._lock:
                    self._queued -= 1
                    self._stats.rejected_requests += 1
                    self._stats.timeouts += 1
                    self._update_metrics()

                logger.warning(
                    f"LLM request queue timeout after {effective_timeout}s "
                    f"(queued: {self._queued}, active: {self._stats.active_requests})"
                )
                raise

            # Successfully acquired
            wait_time = time.monotonic() - start_time
            async with self._lock:
                self._queued -= 1
                self._stats.active_requests += 1
                self._stats.total_wait_time += wait_time
                self._stats.max_wait_time = max(self._stats.max_wait_time, wait_time)
                self._update_metrics()

            if wait_time > 1.0:
                logger.debug(f"LLM request waited {wait_time:.2f}s in queue")

            try:
                yield
            finally:
                async with self._lock:
                    self._stats.active_requests -= 1
                    self._stats.completed_requests += 1
                    self._update_metrics()
                self._semaphore.release()

        except asyncio.CancelledError:
            async with self._lock:
                if self._queued > 0:
                    self._queued -= 1
                self._update_metrics()
            raise

    def get_status(self) -> dict[str, Any]:
        """Get current limiter status.

        Returns:
            Dictionary with limiter status and statistics
        """
        return {
            "max_concurrent": self._max_concurrent,
            "queue_timeout": self._queue_timeout,
            "active_requests": self._stats.active_requests,
            "queued_requests": self._queued,
            "stats": {
                "total_requests": self._stats.total_requests,
                "completed_requests": self._stats.completed_requests,
                "rejected_requests": self._stats.rejected_requests,
                "timeouts": self._stats.timeouts,
                "avg_wait_time": (
                    self._stats.total_wait_time / self._stats.completed_requests
                    if self._stats.completed_requests > 0
                    else 0.0
                ),
                "max_wait_time": self._stats.max_wait_time,
            },
        }


class LLMConcurrencyLimitError(Exception):
    """Raised when the LLM concurrency limit prevents a request."""

    pass


def get_llm_limiter(**kwargs: Any) -> LLMConcurrencyLimiter:
    """Get the global LLM concurrency limiter instance.

    Convenience function for accessing the singleton limiter.
    """
    return LLMConcurrencyLimiter.get_instance(**kwargs)
