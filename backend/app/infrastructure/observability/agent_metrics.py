"""Agent Enhancement Metrics

Provides Prometheus-compatible metrics for agent enhancement features.
Uses custom metrics implementation from prometheus_metrics.py.

Metrics Categories:
- Response Recovery: Track malformed output recovery success/duration
- Failure Snapshots: Track snapshot generation and token budget
- Duplicate Queries: Track suppression and override rates
- Tool Canonicalization: Track argument alias conversions
- Tool Cache: Track definition cache hits/misses and stats

Usage:
    from app.infrastructure.observability.agent_metrics import (
        agent_response_recovery_trigger,
        recovery_duration,
    )

    # Increment counter
    agent_response_recovery_trigger.inc(
        labels={'recovery_reason': 'malformed_output', 'agent_type': 'plan_act'}
    )

    # Observe histogram
    recovery_duration.observe(
        labels={'recovery_reason': 'malformed_output'},
        value=1.5
    )
"""

import logging

from app.infrastructure.observability.prometheus_metrics import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# ============================================================================
# RESPONSE RECOVERY METRICS (Workstream A)
# ============================================================================

agent_response_recovery_trigger = Counter(
    name="agent_response_recovery_trigger_total",
    help_text="Total response recovery triggers",
    labels=["recovery_reason", "agent_type"],
)

agent_response_recovery_success = Counter(
    name="agent_response_recovery_success_total",
    help_text="Successful response recoveries",
    labels=["recovery_strategy", "retry_count"],
)

agent_response_recovery_failure = Counter(
    name="agent_response_recovery_failure_total",
    help_text="Failed response recoveries (budget exhausted)",
    labels=["recovery_reason", "agent_type"],
)

recovery_duration = Histogram(
    name="agent_response_recovery_duration_seconds",
    help_text="Time spent in recovery flow",
    labels=["recovery_reason"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf")],
)

# ============================================================================
# FAILURE SNAPSHOT METRICS (Workstream B)
# ============================================================================

failure_snapshot_generated = Counter(
    name="agent_failure_snapshot_generated_total",
    help_text="Failure snapshots generated",
    labels=["failure_type", "step_name"],
)

failure_snapshot_size = Histogram(
    name="agent_failure_snapshot_tokens",
    help_text="Snapshot size in approximate tokens",
    labels=[],
    buckets=[50, 100, 200, 300, 500, float("inf")],
)

failure_snapshot_injected = Counter(
    name="agent_failure_snapshot_injected_total",
    help_text="Snapshots injected into retry context",
    labels=["retry_count"],
)

failure_snapshot_budget_violations = Counter(
    name="agent_failure_snapshot_budget_violations_total",
    help_text="Snapshots exceeding token budget",
    labels=["violation_type"],
)

# ============================================================================
# DUPLICATE QUERY SUPPRESSION METRICS (Workstream D)
# ============================================================================

agent_duplicate_query_blocked = Counter(
    name="agent_duplicate_query_blocked_total",
    help_text="Queries suppressed as duplicates",
    labels=["tool_name", "suppression_reason"],
)

agent_duplicate_query_override = Counter(
    name="agent_duplicate_query_override_total",
    help_text="Duplicate suppressions overridden (false positives)",
    labels=["override_reason"],
)

duplicate_query_window_size = Gauge(
    name="agent_duplicate_query_window_size",
    help_text="Current duplicate query window size (minutes)",
    labels=["policy_type"],
)

# ============================================================================
# TOOL ARGUMENT CANONICALIZATION METRICS (Workstream C)
# ============================================================================

agent_tool_args_canonicalized = Counter(
    name="agent_tool_args_canonicalized_total",
    help_text="Tool arguments canonicalized",
    labels=["tool_name", "alias_type"],
)

agent_tool_args_rejected = Counter(
    name="agent_tool_args_rejected_total",
    help_text="Unknown tool arguments rejected",
    labels=["tool_name", "rejection_reason"],
)

# ============================================================================
# TOOL DEFINITION CACHE METRICS (Workstream E)
# ============================================================================

agent_tool_definition_cache_hits = Counter(
    name="agent_tool_definition_cache_hits_total",
    help_text="Tool definition cache hits",
    labels=["cache_scope"],
)

agent_tool_definition_cache_misses = Counter(
    name="agent_tool_definition_cache_misses_total",
    help_text="Tool definition cache misses",
    labels=["cache_scope"],
)

agent_tool_cache_invalidations = Counter(
    name="agent_tool_cache_invalidations_total",
    help_text="Cache invalidations triggered",
    labels=["invalidation_reason"],
)

agent_tool_cache_size = Gauge(
    name="agent_tool_cache_size",
    help_text="Current tool cache size (number of cached definitions)",
    labels=["cache_type"],
)

agent_tool_cache_hit_rate = Gauge(
    name="agent_tool_cache_hit_rate",
    help_text="Cache hit rate (0-1) over time window",
    labels=["window"],
)

agent_tool_cache_memory_bytes = Gauge(
    name="agent_tool_cache_memory_bytes",
    help_text="Approximate cache memory usage in bytes",
    labels=["cache_type"],
)

tool_cache_lookup_duration = Histogram(
    name="agent_tool_cache_lookup_duration_seconds",
    help_text="Time spent looking up tool definitions",
    labels=["cache_hit"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, float("inf")],
)

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def reset_all_metrics() -> None:
    """Reset all agent enhancement metrics (for testing only).

    WARNING: This should only be called in test environments.
    """
    logger.warning("Resetting all agent enhancement metrics (test mode only)")

    # Note: Custom metrics don't have a reset() method in base implementation
    # This is a placeholder for future implementation if needed
    # For now, metrics accumulate across test runs


def get_metrics_summary() -> dict[str, int]:
    """Get summary of current metric values (for debugging/monitoring).

    Returns:
        dict: Summary of metric counts
    """
    return {
        "recovery_triggers": sum(agent_response_recovery_trigger._values.values()),
        "recovery_successes": sum(agent_response_recovery_success._values.values()),
        "snapshots_generated": sum(failure_snapshot_generated._values.values()),
        "duplicate_queries_blocked": sum(agent_duplicate_query_blocked._values.values()),
        "cache_hits": sum(agent_tool_definition_cache_hits._values.values()),
        "cache_misses": sum(agent_tool_definition_cache_misses._values.values()),
    }
