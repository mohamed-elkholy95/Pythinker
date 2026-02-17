"""Infrastructure adapter that wires Prometheus metrics into the domain AgentMetrics.

Called during application startup to replace domain no-op metrics
with real Prometheus counters, gauges, and histograms.

Usage (in main.py or composition root):
    from app.infrastructure.observability.agent_metrics_adapter import configure_agent_metrics
    configure_agent_metrics()
"""

import logging

from app.domain.metrics.agent_metrics import AgentMetrics, set_agent_metrics
from app.infrastructure.observability.agent_metrics import (
    agent_duplicate_query_blocked,
    agent_duplicate_query_override,
    agent_response_recovery_failure,
    agent_response_recovery_success,
    agent_response_recovery_trigger,
    agent_tool_args_canonicalized,
    agent_tool_args_rejected,
    agent_tool_cache_hit_rate,
    agent_tool_cache_invalidations,
    agent_tool_cache_memory_bytes,
    agent_tool_cache_size,
    agent_tool_definition_cache_hits,
    agent_tool_definition_cache_misses,
    duplicate_query_window_size,
    failure_snapshot_budget_violations,
    failure_snapshot_generated,
    failure_snapshot_injected,
    failure_snapshot_size,
    recovery_duration,
    tool_cache_lookup_duration,
)

logger = logging.getLogger(__name__)


def configure_agent_metrics() -> None:
    """Wire Prometheus metrics into the domain AgentMetrics singleton.

    This bridges the infrastructure (Prometheus) implementation to the
    domain-layer abstractions, allowing domain services to record metrics
    without importing from infrastructure.
    """
    metrics = AgentMetrics()

    # Response Recovery
    metrics.response_recovery_trigger = agent_response_recovery_trigger
    metrics.response_recovery_success = agent_response_recovery_success
    metrics.response_recovery_failure = agent_response_recovery_failure
    metrics.recovery_duration = recovery_duration

    # Failure Snapshot
    metrics.failure_snapshot_generated = failure_snapshot_generated
    metrics.failure_snapshot_size = failure_snapshot_size
    metrics.failure_snapshot_injected = failure_snapshot_injected
    metrics.failure_snapshot_budget_violations = failure_snapshot_budget_violations

    # Duplicate Query
    metrics.duplicate_query_blocked = agent_duplicate_query_blocked
    metrics.duplicate_query_override = agent_duplicate_query_override
    metrics.duplicate_query_window_size = duplicate_query_window_size

    # Tool Argument Canonicalization
    metrics.tool_args_canonicalized = agent_tool_args_canonicalized
    metrics.tool_args_rejected = agent_tool_args_rejected

    # Tool Definition Cache
    metrics.tool_definition_cache_hits = agent_tool_definition_cache_hits
    metrics.tool_definition_cache_misses = agent_tool_definition_cache_misses
    metrics.tool_cache_invalidations = agent_tool_cache_invalidations
    metrics.tool_cache_size = agent_tool_cache_size
    metrics.tool_cache_hit_rate = agent_tool_cache_hit_rate
    metrics.tool_cache_memory_bytes = agent_tool_cache_memory_bytes
    metrics.tool_cache_lookup_duration = tool_cache_lookup_duration

    set_agent_metrics(metrics)
    logger.info("Agent metrics wired to Prometheus implementation")
