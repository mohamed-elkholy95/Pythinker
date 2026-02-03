"""Agent Performance Metrics Collection

Centralized metrics collection for monitoring agent optimization performance.
Provides real-time visibility into token usage, cache performance, and tool execution.

Usage:
    metrics = get_metrics_collector()
    metrics.record_token_usage(prompt_tokens=100, completion_tokens=50, cached=True)

    # Get current metrics
    summary = metrics.get_summary()
"""

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Types of metrics collected."""

    TOKEN_USAGE = "token_usage"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    TOOL_EXECUTION = "tool_execution"
    HALLUCINATION = "hallucination"
    LATENCY = "latency"
    ERROR = "error"


@dataclass
class MetricEvent:
    """Single metric event."""

    metric_type: MetricType
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class TokenMetrics:
    """Token usage metrics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    cache_savings: int = 0  # Tokens saved via caching


@dataclass
class CacheMetrics:
    """Cache performance metrics."""

    l1_hits: int = 0
    l1_misses: int = 0
    l2_hits: int = 0
    l2_misses: int = 0
    tool_cache_hits: int = 0
    tool_cache_misses: int = 0

    @property
    def l1_hit_rate(self) -> float:
        total = self.l1_hits + self.l1_misses
        return self.l1_hits / total if total > 0 else 0.0

    @property
    def l2_hit_rate(self) -> float:
        total = self.l2_hits + self.l2_misses
        return self.l2_hits / total if total > 0 else 0.0

    @property
    def combined_hit_rate(self) -> float:
        total_hits = self.l1_hits + self.l2_hits
        total = total_hits + self.l1_misses + self.l2_misses
        return total_hits / total if total > 0 else 0.0


@dataclass
class ToolMetrics:
    """Tool execution metrics."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    parallel_executions: int = 0
    hallucinations_detected: int = 0
    total_duration_ms: float = 0

    @property
    def success_rate(self) -> float:
        return self.successful_calls / self.total_calls if self.total_calls > 0 else 0.0

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.total_calls if self.total_calls > 0 else 0.0


@dataclass
class LatencyMetrics:
    """Latency distribution metrics."""

    count: int = 0
    total_ms: float = 0
    min_ms: float = float("inf")
    max_ms: float = 0
    p50_ms: float = 0
    p95_ms: float = 0
    p99_ms: float = 0
    _samples: list[float] = field(default_factory=list)

    def record(self, latency_ms: float) -> None:
        self.count += 1
        self.total_ms += latency_ms
        self.min_ms = min(self.min_ms, latency_ms)
        self.max_ms = max(self.max_ms, latency_ms)
        self._samples.append(latency_ms)

        # Keep only last 1000 samples for percentile calculation
        if len(self._samples) > 1000:
            self._samples = self._samples[-1000:]

        self._update_percentiles()

    def _update_percentiles(self) -> None:
        if not self._samples:
            return
        sorted_samples = sorted(self._samples)
        n = len(sorted_samples)
        self.p50_ms = sorted_samples[int(n * 0.50)]
        self.p95_ms = sorted_samples[int(n * 0.95)]
        self.p99_ms = sorted_samples[min(int(n * 0.99), n - 1)]

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0.0


class MetricsCollector:
    """Central metrics collector for agent performance monitoring.

    Thread-safe singleton that aggregates metrics across all agent operations.
    Supports time-windowed metrics for trend analysis.
    """

    _instance: Optional["MetricsCollector"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._start_time = datetime.now()

        # Aggregate metrics
        self.tokens = TokenMetrics()
        self.cache = CacheMetrics()
        self.tools = ToolMetrics()
        self.latency = LatencyMetrics()

        # Time-series data (last hour, 1-minute buckets)
        self._time_series: deque = deque(maxlen=60)
        self._current_bucket: dict[str, Any] = self._new_bucket()
        self._bucket_start = datetime.now()

        # Error tracking
        self._errors: deque = deque(maxlen=100)

        # Dynamic toolset metrics
        self._toolset_reductions: list[float] = []

        logger.info("MetricsCollector initialized")

    def _new_bucket(self) -> dict[str, Any]:
        """Create a new time bucket for metrics."""
        return {
            "timestamp": datetime.now(),
            "token_usage": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "tool_calls": 0,
            "errors": 0,
            "latency_sum": 0,
            "latency_count": 0,
        }

    def _rotate_bucket_if_needed(self) -> None:
        """Rotate to new bucket if current one is > 1 minute old."""
        now = datetime.now()
        if (now - self._bucket_start) >= timedelta(minutes=1):
            self._time_series.append(self._current_bucket)
            self._current_bucket = self._new_bucket()
            self._bucket_start = now

    # ==================== Token Metrics ====================

    def record_token_usage(
        self, prompt_tokens: int, completion_tokens: int, cached: bool = False, cache_savings: int = 0
    ) -> None:
        """Record token usage for an LLM call."""
        self.tokens.prompt_tokens += prompt_tokens
        self.tokens.completion_tokens += completion_tokens
        self.tokens.total_tokens += prompt_tokens + completion_tokens

        if cached:
            self.tokens.cached_tokens += prompt_tokens

        self.tokens.cache_savings += cache_savings

        self._rotate_bucket_if_needed()
        self._current_bucket["token_usage"] += prompt_tokens + completion_tokens

    # ==================== Cache Metrics ====================

    def record_cache_hit(self, cache_tier: str = "l1") -> None:
        """Record a cache hit."""
        if cache_tier == "l1":
            self.cache.l1_hits += 1
        elif cache_tier == "l2":
            self.cache.l2_hits += 1
        elif cache_tier == "tool":
            self.cache.tool_cache_hits += 1

        self._rotate_bucket_if_needed()
        self._current_bucket["cache_hits"] += 1

    def record_cache_miss(self, cache_tier: str = "l1") -> None:
        """Record a cache miss."""
        if cache_tier == "l1":
            self.cache.l1_misses += 1
        elif cache_tier == "l2":
            self.cache.l2_misses += 1
        elif cache_tier == "tool":
            self.cache.tool_cache_misses += 1

        self._rotate_bucket_if_needed()
        self._current_bucket["cache_misses"] += 1

    # ==================== Tool Metrics ====================

    def record_tool_execution(self, tool_name: str, success: bool, duration_ms: float, parallel: bool = False) -> None:
        """Record a tool execution."""
        self.tools.total_calls += 1
        self.tools.total_duration_ms += duration_ms

        if success:
            self.tools.successful_calls += 1
        else:
            self.tools.failed_calls += 1

        if parallel:
            self.tools.parallel_executions += 1

        self.latency.record(duration_ms)

        self._rotate_bucket_if_needed()
        self._current_bucket["tool_calls"] += 1
        self._current_bucket["latency_sum"] += duration_ms
        self._current_bucket["latency_count"] += 1

    def record_hallucination(self, attempted_tool: str, suggestions: list[str]) -> None:
        """Record a tool hallucination detection."""
        self.tools.hallucinations_detected += 1
        logger.debug(f"Hallucination recorded: {attempted_tool} -> {suggestions}")

    # ==================== Dynamic Toolset Metrics ====================

    def record_toolset_reduction(self, total_tools: int, filtered_tools: int) -> None:
        """Record dynamic toolset filtering result."""
        if total_tools > 0:
            reduction = 1 - (filtered_tools / total_tools)
            self._toolset_reductions.append(reduction)
            # Keep last 100 samples
            if len(self._toolset_reductions) > 100:
                self._toolset_reductions = self._toolset_reductions[-100:]

    @property
    def avg_toolset_reduction(self) -> float:
        """Average toolset reduction percentage."""
        if not self._toolset_reductions:
            return 0.0
        return sum(self._toolset_reductions) / len(self._toolset_reductions)

    # ==================== Error Tracking ====================

    def record_error(self, error_type: str, message: str, context: dict | None = None) -> None:
        """Record an error event."""
        self._errors.append(
            {"timestamp": datetime.now(), "type": error_type, "message": message[:200], "context": context or {}}
        )

        self._rotate_bucket_if_needed()
        self._current_bucket["errors"] += 1

    # ==================== Latency Tracking ====================

    def record_latency(self, operation: str, latency_ms: float) -> None:
        """Record operation latency."""
        self.latency.record(latency_ms)

        self._rotate_bucket_if_needed()
        self._current_bucket["latency_sum"] += latency_ms
        self._current_bucket["latency_count"] += 1

    # ==================== Summary & Export ====================

    def get_summary(self) -> dict[str, Any]:
        """Get comprehensive metrics summary."""
        uptime = datetime.now() - self._start_time

        return {
            "uptime_seconds": uptime.total_seconds(),
            "tokens": {
                "prompt_tokens": self.tokens.prompt_tokens,
                "completion_tokens": self.tokens.completion_tokens,
                "total_tokens": self.tokens.total_tokens,
                "cached_tokens": self.tokens.cached_tokens,
                "cache_savings": self.tokens.cache_savings,
                "cache_savings_percent": (
                    self.tokens.cache_savings / self.tokens.total_tokens * 100 if self.tokens.total_tokens > 0 else 0
                ),
            },
            "cache": {
                "l1_hit_rate": f"{self.cache.l1_hit_rate:.1%}",
                "l2_hit_rate": f"{self.cache.l2_hit_rate:.1%}",
                "combined_hit_rate": f"{self.cache.combined_hit_rate:.1%}",
                "l1_hits": self.cache.l1_hits,
                "l1_misses": self.cache.l1_misses,
                "l2_hits": self.cache.l2_hits,
                "l2_misses": self.cache.l2_misses,
            },
            "tools": {
                "total_calls": self.tools.total_calls,
                "success_rate": f"{self.tools.success_rate:.1%}",
                "parallel_executions": self.tools.parallel_executions,
                "hallucinations_detected": self.tools.hallucinations_detected,
                "avg_duration_ms": f"{self.tools.avg_duration_ms:.2f}",
            },
            "latency": {
                "avg_ms": f"{self.latency.avg_ms:.2f}",
                "p50_ms": f"{self.latency.p50_ms:.2f}",
                "p95_ms": f"{self.latency.p95_ms:.2f}",
                "p99_ms": f"{self.latency.p99_ms:.2f}",
                "min_ms": f"{self.latency.min_ms:.2f}" if self.latency.min_ms != float("inf") else "N/A",
                "max_ms": f"{self.latency.max_ms:.2f}",
            },
            "dynamic_toolset": {
                "avg_reduction": f"{self.avg_toolset_reduction:.1%}",
                "samples": len(self._toolset_reductions),
            },
            "errors": {"total": len(self._errors), "recent": list(self._errors)[-5:] if self._errors else []},
        }

    def get_time_series(self, minutes: int = 60) -> list[dict[str, Any]]:
        """Get time-series data for the last N minutes."""
        # Include current bucket
        all_buckets = [*list(self._time_series), self._current_bucket]
        return all_buckets[-minutes:]

    def reset(self) -> None:
        """Reset all metrics."""
        self.tokens = TokenMetrics()
        self.cache = CacheMetrics()
        self.tools = ToolMetrics()
        self.latency = LatencyMetrics()
        self._time_series.clear()
        self._current_bucket = self._new_bucket()
        self._errors.clear()
        self._toolset_reductions.clear()
        self._start_time = datetime.now()
        logger.info("Metrics reset")

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = [
            "# HELP agent_tokens_total Total tokens used",
            "# TYPE agent_tokens_total counter",
            f'agent_tokens_total{{type="prompt"}} {self.tokens.prompt_tokens}',
            f'agent_tokens_total{{type="completion"}} {self.tokens.completion_tokens}',
            f'agent_tokens_total{{type="cached"}} {self.tokens.cached_tokens}',
            "",
            "# HELP agent_cache_hits_total Cache hits by tier",
            "# TYPE agent_cache_hits_total counter",
            f'agent_cache_hits_total{{tier="l1"}} {self.cache.l1_hits}',
            f'agent_cache_hits_total{{tier="l2"}} {self.cache.l2_hits}',
            "",
            "# HELP agent_cache_misses_total Cache misses by tier",
            "# TYPE agent_cache_misses_total counter",
            f'agent_cache_misses_total{{tier="l1"}} {self.cache.l1_misses}',
            f'agent_cache_misses_total{{tier="l2"}} {self.cache.l2_misses}',
            "",
            "# HELP agent_tool_calls_total Total tool calls",
            "# TYPE agent_tool_calls_total counter",
            f'agent_tool_calls_total{{status="success"}} {self.tools.successful_calls}',
            f'agent_tool_calls_total{{status="failure"}} {self.tools.failed_calls}',
            "",
            "# HELP agent_tool_duration_ms Tool execution duration",
            "# TYPE agent_tool_duration_ms summary",
            f'agent_tool_duration_ms{{quantile="0.5"}} {self.latency.p50_ms}',
            f'agent_tool_duration_ms{{quantile="0.95"}} {self.latency.p95_ms}',
            f'agent_tool_duration_ms{{quantile="0.99"}} {self.latency.p99_ms}',
            "",
            "# HELP agent_hallucinations_total Hallucinations detected",
            "# TYPE agent_hallucinations_total counter",
            f"agent_hallucinations_total {self.tools.hallucinations_detected}",
            "",
            "# HELP agent_toolset_reduction Dynamic toolset reduction ratio",
            "# TYPE agent_toolset_reduction gauge",
            f"agent_toolset_reduction {self.avg_toolset_reduction}",
        ]
        return "\n".join(lines)


# Global accessor
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
