"""Domain-layer metrics abstractions for agent enhancement features.

Provides abstract metric interfaces (counter, gauge, histogram) that
domain services can use without depending on infrastructure (Prometheus).

The concrete implementations are injected at application startup via
the module-level setter functions. If no implementation is injected,
a no-op implementation is used to ensure domain services work without
infrastructure dependencies.

Usage in domain services:
    from app.domain.metrics.agent_metrics import get_agent_metrics

    metrics = get_agent_metrics()
    metrics.failure_snapshot_generated.inc(
        labels={"failure_type": "ValueError", "step_name": "execute"}
    )
"""

from __future__ import annotations

from typing import Protocol


class MetricCounter(Protocol):
    """Protocol for a counter metric that can only go up."""

    def inc(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        """Increment counter with given labels."""
        ...


class MetricGauge(Protocol):
    """Protocol for a gauge metric that can go up and down."""

    def set(self, labels: dict[str, str] | None = None, value: float = 0.0) -> None:
        """Set gauge to given value."""
        ...


class MetricHistogram(Protocol):
    """Protocol for a histogram metric that records distributions."""

    def observe(self, labels: dict[str, str] | None = None, value: float = 0.0) -> None:
        """Record an observation."""
        ...


class _NoOpCounter:
    """No-op counter used when no metrics implementation is configured."""

    def inc(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        pass


class _NoOpGauge:
    """No-op gauge used when no metrics implementation is configured."""

    def set(self, labels: dict[str, str] | None = None, value: float = 0.0) -> None:
        pass


class _NoOpHistogram:
    """No-op histogram used when no metrics implementation is configured."""

    def observe(self, labels: dict[str, str] | None = None, value: float = 0.0) -> None:
        pass


class AgentMetrics:
    """Container for all agent enhancement metrics.

    Provides named metric accessors that domain services use.
    By default, all metrics are no-op. The infrastructure layer
    replaces them with real Prometheus metrics at startup.
    """

    def __init__(self) -> None:
        # Response Recovery metrics
        self.response_recovery_trigger: MetricCounter = _NoOpCounter()
        self.response_recovery_success: MetricCounter = _NoOpCounter()
        self.response_recovery_failure: MetricCounter = _NoOpCounter()
        self.recovery_duration: MetricHistogram = _NoOpHistogram()

        # Failure Snapshot metrics
        self.failure_snapshot_generated: MetricCounter = _NoOpCounter()
        self.failure_snapshot_size: MetricHistogram = _NoOpHistogram()
        self.failure_snapshot_injected: MetricCounter = _NoOpCounter()
        self.failure_snapshot_budget_violations: MetricCounter = _NoOpCounter()

        # Duplicate Query metrics
        self.duplicate_query_blocked: MetricCounter = _NoOpCounter()
        self.duplicate_query_override: MetricCounter = _NoOpCounter()
        self.duplicate_query_window_size: MetricGauge = _NoOpGauge()

        # Tool Argument Canonicalization metrics
        self.tool_args_canonicalized: MetricCounter = _NoOpCounter()
        self.tool_args_rejected: MetricCounter = _NoOpCounter()

        # Tool Definition Cache metrics
        self.tool_definition_cache_hits: MetricCounter = _NoOpCounter()
        self.tool_definition_cache_misses: MetricCounter = _NoOpCounter()
        self.tool_cache_invalidations: MetricCounter = _NoOpCounter()
        self.tool_cache_size: MetricGauge = _NoOpGauge()
        self.tool_cache_hit_rate: MetricGauge = _NoOpGauge()
        self.tool_cache_memory_bytes: MetricGauge = _NoOpGauge()
        self.tool_cache_lookup_duration: MetricHistogram = _NoOpHistogram()


# Module-level singleton
_agent_metrics: AgentMetrics | None = None


def get_agent_metrics() -> AgentMetrics:
    """Get the global AgentMetrics instance.

    Returns a no-op implementation if not yet configured.
    Domain services should always call this to get metrics.

    Returns:
        AgentMetrics instance
    """
    global _agent_metrics
    if _agent_metrics is None:
        _agent_metrics = AgentMetrics()
    return _agent_metrics


def set_agent_metrics(metrics: AgentMetrics) -> None:
    """Set the global AgentMetrics instance.

    Called from the composition root to inject infrastructure
    (Prometheus) metrics into the domain layer.

    Args:
        metrics: Configured AgentMetrics with real metric implementations
    """
    global _agent_metrics
    _agent_metrics = metrics
