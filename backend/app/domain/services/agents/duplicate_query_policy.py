"""Duplicate Query Suppression Policy

Prevents low-value repeated tool calls unless prior results were low quality or failed.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.domain.metrics.agent_metrics import get_agent_metrics

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result from a query execution."""

    query_signature: str
    timestamp: float
    quality_score: float  # 0-1, where 1 is highest quality
    success: bool
    result_data: Any = None


@dataclass
class QueryCache:
    """Cache of recent queries with time-based expiration."""

    window_minutes: int = 5
    _cache: dict[str, QueryResult] = field(default_factory=dict)

    def add(self, result: QueryResult) -> None:
        """Add query result to cache."""
        self._cache[result.query_signature] = result

    def get(self, signature: str) -> QueryResult | None:
        """Get cached result if within window."""
        if signature not in self._cache:
            return None

        result = self._cache[signature]
        age_seconds = time.time() - result.timestamp

        if age_seconds > (self.window_minutes * 60):
            # Expired, remove from cache
            del self._cache[signature]
            return None

        return result

    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        current_time = time.time()
        window_seconds = self.window_minutes * 60

        expired = [sig for sig, result in self._cache.items() if (current_time - result.timestamp) > window_seconds]

        for sig in expired:
            del self._cache[sig]

        return len(expired)


class DuplicateQueryPolicy:
    """Policy for detecting and suppressing duplicate queries.

    Implements:
    - Query signature generation
    - Time-windowed duplicate detection
    - Quality-aware override
    - Explicit retry support
    - Metrics tracking
    """

    def __init__(
        self,
        window_minutes: int = 5,
        quality_threshold: float = 0.5,
    ):
        """Initialize duplicate query policy.

        Args:
            window_minutes: Suppression window duration
            quality_threshold: Quality score below which retries are allowed
        """
        self.window_minutes = window_minutes
        self.quality_threshold = quality_threshold
        self._cache = QueryCache(window_minutes=window_minutes)

        # Update window size gauge
        metrics = get_agent_metrics()
        metrics.duplicate_query_window_size.set(
            labels={"policy_type": "time_windowed"},
            value=float(window_minutes),
        )

    def generate_signature(self, tool_name: str, args: dict[str, Any]) -> str:
        """Generate deterministic signature for query.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            str: SHA256 signature of tool + args
        """
        # Sort args for deterministic hashing
        sorted_args = sorted(args.items())
        content = f"{tool_name}:{sorted_args}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def should_suppress(
        self,
        tool_name: str,
        args: dict[str, Any],
        force_retry: bool = False,
    ) -> tuple[bool, str]:
        """Determine if query should be suppressed.

        Args:
            tool_name: Name of the tool
            args: Tool arguments
            force_retry: Explicit retry flag (bypasses suppression)

        Returns:
            tuple[bool, str]: (should_suppress, reason)
        """
        signature = self.generate_signature(tool_name, args)

        # Check force retry flag
        if force_retry:
            logger.info(f"Query {signature} allowed: explicit retry")
            get_agent_metrics().duplicate_query_override.inc(labels={"override_reason": "explicit_retry"})
            return False, "explicit_retry"

        # Check if duplicate exists in cache
        cached_result = self._cache.get(signature)

        if cached_result is None:
            # Not a duplicate
            return False, "not_duplicate"

        # Duplicate found - check if previous execution failed
        if not cached_result.success:
            logger.info(f"Query {signature} allowed: previous execution failed")
            get_agent_metrics().duplicate_query_override.inc(labels={"override_reason": "previous_failure"})
            return False, "previous_failure"

        # Duplicate found - check quality
        if cached_result.quality_score < self.quality_threshold:
            logger.info(f"Query {signature} allowed: low quality result ({cached_result.quality_score:.2f})")
            get_agent_metrics().duplicate_query_override.inc(labels={"override_reason": "low_quality_result"})
            return False, "low_quality_result"

        # Suppress duplicate
        logger.info(f"Query {signature} suppressed: duplicate within {self.window_minutes}m window")
        get_agent_metrics().duplicate_query_blocked.inc(
            labels={
                "tool_name": tool_name,
                "suppression_reason": "duplicate_within_window",
            }
        )

        return True, "duplicate_within_window"

    def record_execution(
        self,
        tool_name: str,
        args: dict[str, Any],
        success: bool,
        quality_score: float,
        result_data: Any = None,
    ) -> None:
        """Record query execution result.

        Args:
            tool_name: Name of the tool
            args: Tool arguments
            success: Whether execution succeeded
            quality_score: Quality score (0-1)
            result_data: Result data (optional)
        """
        signature = self.generate_signature(tool_name, args)

        result = QueryResult(
            query_signature=signature,
            timestamp=time.time(),
            quality_score=quality_score,
            success=success,
            result_data=result_data,
        )

        self._cache.add(result)

        logger.debug(f"Recorded query {signature}: success={success}, quality={quality_score:.2f}")

    def cleanup(self) -> int:
        """Clean up expired cache entries.

        Returns:
            int: Number of entries removed
        """
        removed = self._cache.cleanup_expired()
        if removed > 0:
            logger.debug(f"Cleaned up {removed} expired query entries")
        return removed

    def get_stats(self) -> dict[str, Any]:
        """Get policy statistics.

        Returns:
            dict: Statistics
        """
        return {
            "window_minutes": self.window_minutes,
            "quality_threshold": self.quality_threshold,
            "cached_queries": len(self._cache._cache),
        }
