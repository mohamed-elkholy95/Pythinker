"""Prometheus Metrics for Pythinker

Provides Prometheus-compatible metrics collection and export.
Supports counters, gauges, and histograms for LLM, tool, and session metrics.

Usage:
    from app.core.prometheus_metrics import (
        llm_calls_total,
        tool_calls_total,
        record_llm_call,
        record_tool_call,
    )

    # Record metrics
    record_llm_call(model="claude-sonnet-4", status="success", latency=1.5, tokens=500)
    record_tool_call(tool="file_read", status="success", latency=0.1)
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Counter:
    """Prometheus-style counter metric."""

    name: str
    help_text: str
    labels: list[str]
    _values: dict[tuple, float] = field(default_factory=lambda: defaultdict(float))
    _lock: Lock = field(default_factory=Lock)

    class _ValueCompat:
        """Compatibility shim for tests expecting prometheus_client-style `_value.get(...)`."""

        def __init__(self, values: dict[tuple, float]):
            self._values = values

        def get(self, key: Any, default: float = 0.0) -> float:
            if isinstance(key, frozenset):
                if not key:
                    return self._values.get((), default)
                try:
                    normalized = tuple(value for _, value in sorted(key))
                except Exception:
                    return default
                return self._values.get(normalized, default)
            if key == ():
                return self._values.get((), default)
            return self._values.get(key, default)

    @property
    def _value(self) -> "Counter._ValueCompat":
        """Backwards-compatible accessor for legacy tests."""
        return Counter._ValueCompat(self._values)

    def inc(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        """Increment counter with given labels."""
        if labels is None:
            labels = {}
        label_tuple = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            self._values[label_tuple] += value

    def get(self, labels: dict[str, str] | None = None) -> float:
        """Get counter value for given labels."""
        if labels is None:
            labels = {}
        label_tuple = tuple(labels.get(label, "") for label in self.labels)
        return self._values.get(label_tuple, 0.0)

    def collect(self) -> list[dict[str, Any]]:
        """Collect all metric values for export."""
        result = []
        with self._lock:
            for label_tuple, value in self._values.items():
                label_dict = dict(zip(self.labels, label_tuple, strict=False))
                result.append(
                    {
                        "name": self.name,
                        "type": "counter",
                        "labels": label_dict,
                        "value": value,
                    }
                )
        return result


@dataclass
class Gauge:
    """Prometheus-style gauge metric."""

    name: str
    help_text: str
    labels: list[str]
    _values: dict[tuple, float] = field(default_factory=lambda: defaultdict(float))
    _lock: Lock = field(default_factory=Lock)

    def set(self, labels: dict[str, str] | None = None, value: float = 0.0) -> None:
        """Set gauge value for given labels."""
        if labels is None:
            labels = {}
        label_tuple = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            self._values[label_tuple] = value

    def inc(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        """Increment gauge value."""
        if labels is None:
            labels = {}
        label_tuple = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            self._values[label_tuple] += value

    def dec(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        """Decrement gauge value."""
        if labels is None:
            labels = {}
        label_tuple = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            self._values[label_tuple] -= value

    def get(self, labels: dict[str, str] | None = None) -> float:
        """Get gauge value for given labels."""
        if labels is None:
            labels = {}
        label_tuple = tuple(labels.get(label, "") for label in self.labels)
        return self._values.get(label_tuple, 0.0)

    def collect(self) -> list[dict[str, Any]]:
        """Collect all metric values for export."""
        result = []
        with self._lock:
            for label_tuple, value in self._values.items():
                label_dict = dict(zip(self.labels, label_tuple, strict=False))
                result.append(
                    {
                        "name": self.name,
                        "type": "gauge",
                        "labels": label_dict,
                        "value": value,
                    }
                )
        return result


@dataclass
class Histogram:
    """Prometheus-style histogram metric."""

    name: str
    help_text: str
    labels: list[str]
    buckets: list[float] = field(default_factory=lambda: [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
    _observations: dict[tuple, list[float]] = field(default_factory=lambda: defaultdict(list))
    _lock: Lock = field(default_factory=Lock)

    def observe(self, labels: dict[str, str] | None = None, value: float = 0.0) -> None:
        """Record an observation."""
        if labels is None:
            labels = {}
        label_tuple = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            self._observations[label_tuple].append(value)

    def collect(self) -> list[dict[str, Any]]:
        """Collect all metric values for export."""
        result = []
        with self._lock:
            for label_tuple, values in self._observations.items():
                label_dict = dict(zip(self.labels, label_tuple, strict=False))

                # Calculate bucket counts
                bucket_counts = {}
                for bucket in self.buckets:
                    bucket_counts[bucket] = sum(1 for v in values if v <= bucket)
                bucket_counts[float("inf")] = len(values)

                # Calculate sum and count
                total_sum = sum(values)
                total_count = len(values)

                result.append(
                    {
                        "name": self.name,
                        "type": "histogram",
                        "labels": label_dict,
                        "buckets": bucket_counts,
                        "sum": total_sum,
                        "count": total_count,
                    }
                )
        return result


# Define metrics
llm_calls_total = Counter(
    name="pythinker_llm_calls_total",
    help_text="Total number of LLM API calls",
    labels=["model", "status"],
)

tool_calls_total = Counter(
    name="pythinker_tool_calls_total",
    help_text="Total number of tool executions",
    labels=["tool", "status"],
)

tokens_total = Counter(
    name="pythinker_tokens_total",
    help_text="Total tokens used",
    labels=["type"],  # "prompt", "completion", "cached"
)

llm_latency = Histogram(
    name="pythinker_llm_latency_seconds",
    help_text="LLM call latency in seconds",
    labels=["model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

tool_latency = Histogram(
    name="pythinker_tool_latency_seconds",
    help_text="Tool execution latency in seconds",
    labels=["tool"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

active_sessions = Gauge(
    name="pythinker_active_sessions",
    help_text="Number of active sessions",
    labels=[],
)

active_agents = Gauge(
    name="pythinker_active_agents",
    help_text="Number of active agents",
    labels=[],
)

# Screenshot Replay Metrics
screenshot_captures_total = Counter(
    name="pythinker_screenshot_captures_total",
    help_text="Total screenshot capture attempts",
    labels=["trigger", "status"],  # status: success, error
)

screenshot_capture_size_bytes = Counter(
    name="pythinker_screenshot_capture_size_bytes_total",
    help_text="Total bytes captured for screenshot replay",
    labels=["trigger"],
)

screenshot_capture_latency = Histogram(
    name="pythinker_screenshot_capture_latency_seconds",
    help_text="Screenshot capture latency in seconds",
    labels=["trigger", "status"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

screenshot_fetch_total = Counter(
    name="pythinker_screenshot_fetch_total",
    help_text="Total screenshot image fetches",
    labels=["access", "status"],  # access: full, thumbnail
)

screenshot_fetch_size_bytes = Counter(
    name="pythinker_screenshot_fetch_size_bytes_total",
    help_text="Total bytes served for screenshot replay",
    labels=["access"],
)

screenshot_fetch_latency = Histogram(
    name="pythinker_screenshot_fetch_latency_seconds",
    help_text="Screenshot fetch latency in seconds",
    labels=["access", "status"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

# Screenshot Deduplication Metrics
screenshot_dedup_total = Counter(
    name="pythinker_screenshot_dedup_total",
    help_text="Total deduplicated screenshots (storage skipped)",
    labels=["trigger"],
)

screenshot_dedup_saved_bytes = Counter(
    name="pythinker_screenshot_dedup_saved_bytes_total",
    help_text="Total bytes saved by screenshot deduplication",
    labels=["trigger"],
)

# Browser Element Extraction Metrics (Phase 6: timeout fixes)
browser_element_extraction_total = Counter(
    name="pythinker_browser_element_extraction_total",
    help_text="Total browser element extraction attempts",
    labels=["status"],  # status: success, timeout, error
)

browser_element_extraction_timeout_total = Counter(
    name="pythinker_browser_element_extraction_timeout_total",
    help_text="Total browser element extraction timeouts",
    labels=["attempt"],  # attempt: first, retry, final
)

browser_element_extraction_latency = Histogram(
    name="pythinker_browser_element_extraction_latency_seconds",
    help_text="Browser element extraction latency in seconds",
    labels=["status"],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0],
)

# Browser Crash Prevention Metrics (Priority 1)
browser_heavy_page_detections_total = Counter(
    name="pythinker_browser_heavy_page_detections_total",
    help_text="Total heavy page detections",
    labels=["detection_method"],  # detection_method: proactive, reactive
)

browser_wikipedia_summary_mode_total = Counter(
    name="pythinker_browser_wikipedia_summary_mode_total",
    help_text="Total Wikipedia pages using summary extraction mode",
    labels=[],
)

browser_memory_pressure_total = Counter(
    name="pythinker_browser_memory_pressure_total",
    help_text="Total browser memory pressure detections",
    labels=["level"],  # level: low, medium, high, critical
)

browser_memory_restarts_total = Counter(
    name="pythinker_browser_memory_restarts_total",
    help_text="Total browser restarts due to memory pressure",
    labels=[],
)

# Element Extraction Cache Metrics (Priority 5)
element_extraction_cache_hits_total = Counter(
    name="pythinker_element_extraction_cache_hits_total",
    help_text="Total element extraction cache hits",
    labels=[],
)

element_extraction_cache_misses_total = Counter(
    name="pythinker_element_extraction_cache_misses_total",
    help_text="Total element extraction cache misses",
    labels=[],
)

# Sandbox Connection Metrics (Phase 6: warmup optimization)
sandbox_connection_attempts_total = Counter(
    name="pythinker_sandbox_connection_attempts_total",
    help_text="Total sandbox connection attempts",
    labels=["result"],  # result: success, failure, timeout
)

sandbox_connection_failure_total = Counter(
    name="pythinker_sandbox_connection_failure_total",
    help_text="Total sandbox connection failures",
    labels=["reason"],  # reason: timeout, disconnected, refused, unreachable
)

sandbox_warmup_duration = Histogram(
    name="pythinker_sandbox_warmup_duration_seconds",
    help_text="Sandbox warmup duration in seconds",
    labels=["status"],  # status: success, failure
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0],
)

errors_total = Counter(
    name="pythinker_errors_total",
    help_text="Total number of errors",
    labels=["type", "component"],
)

# Phase 6: Circuit Breaker Metrics
circuit_breaker_state = Gauge(
    name="pythinker_circuit_breaker_state",
    help_text="Circuit breaker state (0=closed, 1=half_open, 2=open)",
    labels=["name"],
)

circuit_breaker_calls = Counter(
    name="pythinker_circuit_breaker_calls_total",
    help_text="Total circuit breaker calls",
    labels=["name", "result"],  # result: success, failure, rejected
)

circuit_breaker_state_changes = Counter(
    name="pythinker_circuit_breaker_state_changes_total",
    help_text="Total circuit breaker state changes",
    labels=["name", "from_state", "to_state"],
)

# Adaptive circuit breaker metrics
circuit_breaker_failure_rate = Gauge(
    name="pythinker_circuit_breaker_failure_rate",
    help_text="Circuit breaker recent failure rate",
    labels=["name"],
)

circuit_breaker_threshold = Gauge(
    name="pythinker_circuit_breaker_failure_threshold",
    help_text="Adaptive circuit breaker failure threshold",
    labels=["name"],
)

circuit_breaker_recovery = Counter(
    name="pythinker_circuit_breaker_recovery_total",
    help_text="Circuit breaker recovery attempts",
    labels=["name", "result"],  # attempt, success, failure
)

circuit_breaker_mttr = Histogram(
    name="pythinker_circuit_breaker_mttr_seconds",
    help_text="Circuit breaker mean time to recovery (seconds)",
    labels=["name"],
    buckets=[5, 15, 30, 60, 120, 300, 600, 1200],
)

# Screenshot Resilience Metrics (Priority 2)
screenshot_circuit_state = Gauge(
    name="pythinker_screenshot_circuit_state",
    help_text="Screenshot circuit breaker state (0=closed, 1=half_open, 2=open)",
    labels=["state"],  # state: closed, half_open, open
)

screenshot_retry_attempts_total = Counter(
    name="pythinker_screenshot_retry_attempts_total",
    help_text="Total screenshot retry attempts",
    labels=[],
)

# Sandbox Health Monitoring Metrics (Priority 3)
sandbox_health_check_total = Counter(
    name="pythinker_sandbox_health_check_total",
    help_text="Total sandbox health checks",
    labels=["status"],  # status: success, failure
)

sandbox_oom_kills_total = Counter(
    name="pythinker_sandbox_oom_kills_total",
    help_text="Total sandbox OOM kills detected",
    labels=[],
)

sandbox_runtime_crashes_total = Counter(
    name="pythinker_sandbox_runtime_crashes_total",
    help_text="Total sandbox runtime crashes",
    labels=[],
)

# Agent Robustness Metrics (2026-02-13 plan)
entity_drift_detected_total = Counter(
    name="pythinker_entity_drift_detected_total",
    help_text="Entity drift detected in output (phase: summarize|execute|route)",
    labels=["phase"],
)
output_relevance_failures_total = Counter(
    name="pythinker_output_relevance_failures_total",
    help_text="Output relevance check failures",
    labels=["severity"],  # low, medium, high
)
step_name_quality_violations_total = Counter(
    name="pythinker_step_name_quality_violations_total",
    help_text="Step naming quality violations",
    labels=["violation"],  # empty_verb, empty_target, banned_verb
)
guardrail_tripwire_total = Counter(
    name="pythinker_guardrail_tripwire_total",
    help_text="Guardrail tripwire events",
    labels=["guardrail"],  # fidelity, relevance, consistency, contradiction
)
delivery_fidelity_blocks_total = Counter(
    name="pythinker_delivery_fidelity_blocks_total",
    help_text="Delivery blocked by fidelity checks",
    labels=["mode"],  # shadow, warn, enforce
)
guardrail_latency_seconds = Histogram(
    name="pythinker_guardrail_latency_seconds",
    help_text="Guardrail execution latency in seconds",
    labels=["phase"],  # extract, validate, fidelity, relevance
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)
output_relevance_score = Histogram(
    name="pythinker_output_relevance_score",
    help_text="Output relevance score distribution (0-1)",
    labels=[],
    buckets=[0.1, 0.3, 0.5, 0.7, 0.9, 1.0],
)

# Security Gate Metrics (Task 7: mandatory execution gate)
security_gate_blocks_total = Counter(
    name="pythinker_security_gate_blocks_total",
    help_text="Total security gate blocks (CRITICAL/HIGH/MEDIUM risk)",
    labels=["risk_level", "pattern_type"],
)
security_gate_overrides_total = Counter(
    name="pythinker_security_gate_overrides_total",
    help_text="Total security gate overrides (MEDIUM allowed via config)",
    labels=["override_reason"],
)

# Token Authentication Security Metrics (fail-closed on Redis failure)
token_auth_fail_closed_total = Counter(
    name="pythinker_token_auth_fail_closed_total",
    help_text="Token authentication fail-closed events (access denied due to Redis unavailability)",
    labels=["check_type"],  # "blacklist" or "user_revocation"
)

# Token Management Metrics (Priority 4)
token_pressure_level = Gauge(
    name="pythinker_token_pressure_level",
    help_text="Token pressure level (0=normal, 1=early, 2=moderate, 3=critical, 4=overflow)",
    labels=["session_id"],
)

# Rating Endpoint Security Metrics (Priority 6)
rating_unauthorized_attempts_total = Counter(
    name="pythinker_rating_unauthorized_attempts_total",
    help_text="Total unauthorized rating attempts",
    labels=[],
)

# Admin Authorization Security Metrics
admin_unauthorized_access_total = Counter(
    name="pythinker_admin_unauthorized_access_total",
    help_text="Total unauthorized admin endpoint access attempts",
    labels=["endpoint"],
)

metrics_auth_failure_total = Counter(
    name="pythinker_metrics_auth_failure_total",
    help_text="Total failed metrics endpoint authentication attempts",
    labels=[],
)

# Phase 6: LLM Concurrency Metrics
llm_concurrent_requests = Gauge(
    name="pythinker_llm_concurrent_requests",
    help_text="Current number of concurrent LLM requests",
    labels=[],
)

llm_queue_waiting = Gauge(
    name="pythinker_llm_queue_waiting",
    help_text="Number of LLM requests waiting in queue",
    labels=[],
)

# Phase 6: Token Budget Metrics (Aggregated - removed session_id to prevent high cardinality)
token_budget_used = Counter(
    name="pythinker_token_budget_used_total",
    help_text="Total tokens used across all sessions",
    labels=[],  # Removed session_id - use logs for per-session tracking
)

token_budget_warnings = Counter(
    name="pythinker_token_budget_warnings_total",
    help_text="Token budget warning events (80% threshold)",
    labels=[],
)

# Internal state for converting per-session absolute token usage updates into
# aggregated counters without high-cardinality metric labels.
_token_budget_last_used_by_session: dict[str, int] = {}
_token_budget_warned_sessions: set[str] = set()

# Phase 6: Cache Metrics
cache_hits = Counter(
    name="pythinker_cache_hits_total",
    help_text="Total cache hits",
    labels=["cache_type"],  # embedding, reasoning, tool_result
)

cache_misses = Counter(
    name="pythinker_cache_misses_total",
    help_text="Total cache misses",
    labels=["cache_type"],
)

cache_size = Gauge(
    name="pythinker_cache_size",
    help_text="Current cache size (entries)",
    labels=["cache_type"],
)

# Redis Reliability Metrics
redis_operation_retries_total = Counter(
    name="pythinker_redis_operation_retries_total",
    help_text="Redis operation retries triggered by connection/timeouts",
    labels=["role", "operation"],
)

redis_operation_failures_total = Counter(
    name="pythinker_redis_operation_failures_total",
    help_text="Redis operation final failures after retry exhaustion",
    labels=["role", "error_type"],
)

rate_limit_fallback_total = Counter(
    name="pythinker_rate_limit_fallback_total",
    help_text="Rate-limit middleware fallbacks when Redis is unavailable",
    labels=["reason"],
)

# SSE Streaming Reliability Metrics
sse_stream_open_total = Counter(
    name="pythinker_sse_stream_open_total",
    help_text="Total opened SSE chat streams",
    labels=["endpoint"],
)

sse_stream_close_total = Counter(
    name="pythinker_sse_stream_close_total",
    help_text="Total closed SSE chat streams by close reason",
    labels=["endpoint", "reason"],
)

sse_stream_heartbeat_total = Counter(
    name="pythinker_sse_stream_heartbeat_total",
    help_text="Total SSE heartbeats sent",
    labels=["endpoint"],
)

sse_stream_error_total = Counter(
    name="pythinker_sse_stream_error_total",
    help_text="Total SSE stream errors emitted",
    labels=["endpoint", "error_type"],
)

sse_stream_retry_suggested_total = Counter(
    name="pythinker_sse_stream_retry_suggested_total",
    help_text="Total retry recommendations emitted from SSE stream errors",
    labels=["endpoint", "reason"],
)

sse_stream_duration_seconds = Histogram(
    name="pythinker_sse_stream_duration_seconds",
    help_text="SSE stream lifetime in seconds",
    labels=["endpoint", "close_reason"],
    buckets=[1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0],
)

sse_stream_active = Gauge(
    name="pythinker_sse_stream_active",
    help_text="Currently active SSE streams",
    labels=["endpoint"],
)

sse_resume_cursor_state_total = Counter(
    name="pythinker_sse_resume_cursor_state_total",
    help_text="Resume cursor resolution state for SSE reconnect attempts",
    labels=["endpoint", "state"],  # found, stale, format_mismatch, absent, redis_cursor
)

sse_resume_cursor_fallback_total = Counter(
    name="pythinker_sse_resume_cursor_fallback_total",
    help_text="Resume cursor fallback occurrences by reason",
    labels=["endpoint", "reason"],  # stale_cursor, format_mismatch, missing_event_id
)

sse_reconnect_first_non_heartbeat_seconds = Histogram(
    name="pythinker_sse_reconnect_first_non_heartbeat_seconds",
    help_text="Latency from reconnect to first non-heartbeat event",
    labels=["endpoint"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

sse_stream_events_total = Counter(
    name="pythinker_sse_stream_events_total",
    help_text="Total streamed SSE events by type and phase",
    labels=["endpoint", "event_type", "phase"],
)

# Orphaned Task Cleanup Metrics
orphaned_task_cleanup_runs_total = Counter(
    name="pythinker_orphaned_task_cleanup_runs_total",
    help_text="Total orphaned task cleanup runs",
    labels=["status"],  # success, error
)

orphaned_redis_streams_cleaned_total = Counter(
    name="pythinker_orphaned_redis_streams_cleaned_total",
    help_text="Total orphaned Redis streams cleaned up",
    labels=[],
)

zombie_sessions_cleaned_total = Counter(
    name="pythinker_zombie_sessions_cleaned_total",
    help_text="Total zombie sessions marked as FAILED",
    labels=[],
)

orphaned_task_cleanup_duration_seconds = Histogram(
    name="pythinker_orphaned_task_cleanup_duration_seconds",
    help_text="Orphaned task cleanup operation duration",
    labels=[],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

# Search API Budget Metrics
search_api_calls_total = Counter(
    name="pythinker_search_api_calls_total",
    help_text="Total search API calls (actual HTTP requests, not tool invocations)",
    labels=["provider", "tool"],  # provider: serper/tavily/brave/exa/duckduckgo, tool: info_search_web/wide_research
)

search_budget_exhausted_total = Counter(
    name="pythinker_search_budget_exhausted_total",
    help_text="Total times search budget was exhausted per task",
    labels=["tool"],
)

# Channel link lifecycle metrics
channel_link_code_generated_total = Counter(
    name="pythinker_channel_link_code_generated_total",
    help_text="Total channel link codes generated",
    labels=["channel"],
)

channel_link_redeemed_total = Counter(
    name="pythinker_channel_link_redeemed_total",
    help_text="Total channel link codes redeemed successfully",
    labels=["channel"],
)

channel_link_redeem_failed_total = Counter(
    name="pythinker_channel_link_redeem_failed_total",
    help_text="Total failed channel link redeem attempts",
    labels=["reason"],
)

# Telegram continuity + PDF delivery metrics
telegram_session_reused_total = Counter(
    name="pythinker_telegram_session_reused_total",
    help_text="Total Telegram sessions reused for continuity",
    labels=[],
)

telegram_session_rotated_total = Counter(
    name="pythinker_telegram_session_rotated_total",
    help_text="Total Telegram sessions rotated to a new session",
    labels=["reason"],
)

telegram_pdf_generated_total = Counter(
    name="pythinker_telegram_pdf_generated_total",
    help_text="Total Telegram PDFs generated",
    labels=[],
)

telegram_pdf_renderer_invocations_total = Counter(
    name="pythinker_telegram_pdf_renderer_invocations_total",
    help_text="Total Telegram PDF renderer invocation attempts",
    labels=["renderer"],
)

telegram_pdf_renderer_success_total = Counter(
    name="pythinker_telegram_pdf_renderer_success_total",
    help_text="Total successful Telegram PDF renderer executions",
    labels=["renderer"],
)

telegram_pdf_renderer_fallback_total = Counter(
    name="pythinker_telegram_pdf_renderer_fallback_total",
    help_text="Total Telegram PDF renderer fallbacks",
    labels=["from_renderer", "to_renderer", "reason"],
)

telegram_pdf_citation_integrity_total = Counter(
    name="pythinker_telegram_pdf_citation_integrity_total",
    help_text="Citation normalization integrity outcomes for Telegram PDF rendering",
    labels=["status"],  # status: ok, unresolved
)

telegram_pdf_generation_failed_total = Counter(
    name="pythinker_telegram_pdf_generation_failed_total",
    help_text="Total Telegram PDF generation failures",
    labels=["reason"],
)

telegram_pdf_sent_total = Counter(
    name="pythinker_telegram_pdf_sent_total",
    help_text="Total Telegram PDF documents sent",
    labels=[],
)


# Registry of all metrics
_metrics_registry = [
    llm_calls_total,
    tool_calls_total,
    tokens_total,
    llm_latency,
    tool_latency,
    active_sessions,
    active_agents,
    screenshot_captures_total,
    screenshot_capture_size_bytes,
    screenshot_capture_latency,
    screenshot_fetch_total,
    screenshot_fetch_size_bytes,
    screenshot_fetch_latency,
    screenshot_dedup_total,
    screenshot_dedup_saved_bytes,
    # Browser Element Extraction (Phase 6: timeout fixes)
    browser_element_extraction_total,
    browser_element_extraction_timeout_total,
    browser_element_extraction_latency,
    # Sandbox Connection (Phase 6: warmup optimization)
    sandbox_connection_attempts_total,
    sandbox_connection_failure_total,
    sandbox_warmup_duration,
    errors_total,
    # Phase 6: Circuit Breaker
    circuit_breaker_state,
    circuit_breaker_calls,
    circuit_breaker_state_changes,
    circuit_breaker_failure_rate,
    circuit_breaker_threshold,
    circuit_breaker_recovery,
    circuit_breaker_mttr,
    # Phase 6: Concurrency
    llm_concurrent_requests,
    llm_queue_waiting,
    # Phase 6: Token Budget
    token_budget_used,
    token_budget_warnings,
    # Phase 6: Cache
    cache_hits,
    cache_misses,
    cache_size,
    # Redis reliability
    redis_operation_retries_total,
    redis_operation_failures_total,
    rate_limit_fallback_total,
    # SSE Streaming Reliability
    sse_stream_open_total,
    sse_stream_close_total,
    sse_stream_heartbeat_total,
    sse_stream_error_total,
    sse_stream_retry_suggested_total,
    sse_stream_duration_seconds,
    sse_stream_active,
    sse_resume_cursor_state_total,
    sse_resume_cursor_fallback_total,
    sse_reconnect_first_non_heartbeat_seconds,
    sse_stream_events_total,
    # Orphaned Task Cleanup
    orphaned_task_cleanup_runs_total,
    orphaned_redis_streams_cleaned_total,
    zombie_sessions_cleaned_total,
    orphaned_task_cleanup_duration_seconds,
    # Search API Budget
    search_api_calls_total,
    search_budget_exhausted_total,
    # Channel links
    channel_link_code_generated_total,
    channel_link_redeemed_total,
    channel_link_redeem_failed_total,
    telegram_session_reused_total,
    telegram_session_rotated_total,
    telegram_pdf_generated_total,
    telegram_pdf_renderer_invocations_total,
    telegram_pdf_renderer_success_total,
    telegram_pdf_renderer_fallback_total,
    telegram_pdf_citation_integrity_total,
    telegram_pdf_generation_failed_total,
    telegram_pdf_sent_total,
]

# Workflow Phase Metrics (Monitoring Enhancement)
workflow_phase_duration = Histogram(
    name="pythinker_workflow_phase_duration_seconds",
    help_text="Duration of workflow phases",
    labels=["phase"],  # Removed session_id to prevent high cardinality
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

workflow_phase_transitions = Counter(
    name="pythinker_workflow_phase_transitions_total",
    help_text="Workflow phase transitions",
    labels=["from_phase", "to_phase", "result"],
)

# Tool Selection Metrics
tool_selection_accuracy = Counter(
    name="pythinker_tool_selection_accuracy_total",
    help_text="Tool selection outcomes",
    labels=["tool_name", "outcome"],  # success, failure, hallucination
)

# HTTP Client Pool Metrics (Phase 1: Connection Pooling)
http_pool_connections_total = Gauge(
    name="pythinker_http_pool_connections_total",
    help_text="Total active HTTP pool connections",
    labels=["client_name"],
)

http_pool_requests_total = Counter(
    name="pythinker_http_pool_requests_total",
    help_text="Total HTTP requests via pool",
    labels=["client_name", "status"],  # status: success, error
)

http_pool_request_latency = Histogram(
    name="pythinker_http_pool_request_latency_seconds",
    help_text="HTTP pool request latency in seconds",
    labels=["client_name"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0],
)

http_pool_errors_total = Counter(
    name="pythinker_http_pool_errors_total",
    help_text="Total HTTP pool errors",
    labels=["client_name", "error_type"],
)

http_pool_pool_exhaustion_total = Counter(
    name="pythinker_http_pool_exhaustion_total",
    help_text="HTTP pool exhaustion events (PoolTimeout)",
    labels=["client_name"],
)

# API Key Pool Metrics
api_key_selections_total = Counter(
    name="pythinker_api_key_selections_total",
    help_text="Total API key selections (successful and failed)",
    labels=["provider", "key_id", "status"],  # status: success, exhausted, invalid
)

api_key_exhaustions_total = Counter(
    name="pythinker_api_key_exhaustions_total",
    help_text="Total API key exhaustion events",
    labels=["provider", "reason"],  # reason: quota, invalid, error
)

api_key_health_score = Gauge(
    name="pythinker_api_key_health_score",
    help_text="Current health score of API keys (0=invalid, 1=healthy)",
    labels=["provider", "key_id"],
)

api_key_latency_seconds = Histogram(
    name="pythinker_api_key_latency_seconds",
    help_text="API request latency per key",
    labels=["provider", "key_id"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

api_key_early_recoveries_total = Counter(
    name="pythinker_api_key_early_recoveries_total",
    help_text="Total early key recoveries detected (adaptive TTL trigger)",
    labels=["provider"],
)

search_key_pool_healthy_keys = Gauge(
    name="pythinker_search_key_pool_healthy_keys",
    help_text="Number of healthy API keys per search provider",
    labels=["provider"],
)

hallucination_span_confidence = Histogram(
    name="pythinker_hallucination_span_confidence",
    help_text="Confidence scores of detected hallucination spans",
    labels=["model"],
    buckets=[0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# Plan Quality Metrics
plan_modifications_total = Counter(
    name="pythinker_plan_modifications_total",
    help_text="Plan modification events",
    labels=["type"],  # expand, prune, replan
)

# Plan Verification Metrics
plan_verification_total = Counter(
    name="pythinker_plan_verification_total",
    help_text="Plan verification outcomes",
    labels=["result"],  # pass, revise, fail, skip, error
)

# Reflection Metrics
reflection_checks_total = Counter(
    name="pythinker_reflection_checks_total",
    help_text="Reflection checks performed",
    labels=["result"],  # triggered, skipped
)

reflection_triggers_total = Counter(
    name="pythinker_reflection_triggers_total",
    help_text="Reflection triggers by type",
    labels=["trigger"],  # step_interval, after_error, etc.
)

reflection_decisions_total = Counter(
    name="pythinker_reflection_decisions_total",
    help_text="Reflection decisions",
    labels=["decision"],  # continue, adjust, replan, escalate, abort
)

# Reward Hacking Detection Metrics
reward_hacking_signals_total = Counter(
    name="pythinker_reward_hacking_signals_total",
    help_text="Reward hacking detection signals",
    labels=["signal", "severity"],
)

# Tool Tracing Metrics
tool_trace_anomalies_total = Counter(
    name="pythinker_tool_trace_anomalies_total",
    help_text="Tool tracing anomaly signals",
    labels=["tool", "type"],
)

# Failure Prediction Metrics
failure_prediction_total = Counter(
    name="pythinker_failure_prediction_total",
    help_text="Failure prediction outcomes",
    labels=["result"],  # predicted, clear
)

failure_prediction_probability = Histogram(
    name="pythinker_failure_prediction_probability",
    help_text="Failure prediction probability distribution",
    labels=["result"],
    buckets=[0.1, 0.25, 0.4, 0.6, 0.75, 0.85, 0.95, 1.0],
)

# Intent Classification Metrics (for simple query issue)
intent_classification_total = Counter(
    name="pythinker_intent_classification_total",
    help_text="Intent classification outcomes",
    labels=["detected_intent", "selected_mode"],  # greeting/simple_query/complex_task
)

# Domain MetricsPort-backed counters/histograms
response_policy_mode_total = Counter(
    name="pythinker_response_policy_mode_total",
    help_text="Response policy mode selections",
    labels=["mode"],
)

compression_rejected_total = Counter(
    name="pythinker_compression_rejected_total",
    help_text="Compression attempts rejected by quality checks",
    labels=["reason"],
)

clarification_requested_total = Counter(
    name="pythinker_clarification_requested_total",
    help_text="Clarification requests emitted by flow guardrails",
    labels=["reason"],
)

clarification_resolved_total = Counter(
    name="pythinker_clarification_resolved_total",
    help_text="Clarification requests resolved",
    labels=["source"],
)

clarification_wait_seconds = Histogram(
    name="pythinker_clarification_wait_seconds",
    help_text="Time user spent waiting before responding to clarification",
    labels=[],
    buckets=[1.0, 5.0, 15.0, 60.0, 300.0, 900.0, 3600.0],
)

user_stop_before_done_total = Counter(
    name="pythinker_user_stop_before_done_total",
    help_text="User manually stopped session before task completed",
    labels=[],
)

fast_ack_refiner_total = Counter(
    name="pythinker_fast_ack_refiner_total",
    help_text="Fast acknowledgment refiner outcomes",
    labels=["status", "reason"],
)

fast_ack_refiner_latency_seconds = Histogram(
    name="pythinker_fast_ack_refiner_latency_seconds",
    help_text="Fast acknowledgment refiner latency in seconds",
    labels=["status"],
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)

final_response_tokens = Histogram(
    name="pythinker_final_response_tokens",
    help_text="Estimated token count of final response content",
    labels=["mode"],
    buckets=[64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384],
)

delivery_integrity_gate_result_total = Counter(
    name="pythinker_delivery_integrity_gate_result_total",
    help_text="Delivery integrity gate outcomes",
    labels=["provider", "result", "strict_mode"],
)

delivery_integrity_gate_warning_total = Counter(
    name="pythinker_delivery_integrity_gate_warning_total",
    help_text="Delivery integrity gate warning reasons",
    labels=["provider", "reason", "strict_mode"],
)

delivery_integrity_gate_block_reason_total = Counter(
    name="pythinker_delivery_integrity_gate_block_reason_total",
    help_text="Delivery integrity gate blocking reasons",
    labels=["provider", "reason", "strict_mode"],
)

delivery_integrity_stream_truncation_total = Counter(
    name="pythinker_delivery_integrity_stream_truncation_total",
    help_text="Stream truncation lifecycle outcomes for delivery integrity",
    labels=["provider", "finish_reason", "outcome"],
)

# Phase 4: Grounding Safety Metrics (Aggregated - removed session_id to prevent high cardinality)
grounded_claims_total = Counter(
    name="pythinker_grounded_claims_total",
    help_text="Total claims supported by high-confidence evidence",
    labels=["confidence_level"],  # low, medium, high
)

hallucination_detected_total = Counter(
    name="pythinker_hallucination_detected_total",
    help_text="Total detected hallucinations",
    labels=["detection_method"],  # evidence_contradiction, confidence_threshold, etc.
)

evidence_caveat_total = Counter(
    name="pythinker_evidence_caveat_total",
    help_text="Evidence blocks with caveats injected",
    labels=["confidence_level"],
)

evidence_rejection_total = Counter(
    name="pythinker_evidence_rejection_total",
    help_text="Evidence blocks rejected due to low confidence",
    labels=["reason"],
)

evidence_contradiction_total = Counter(
    name="pythinker_evidence_contradiction_total",
    help_text="Contradictions detected in evidence",
    labels=["detection_type"],  # "numeric", "negation", "llm"
)

# Phase 5: Long-Context Pressure & Context Loss Metrics
context_loss_detected = Counter(
    name="pythinker_context_loss_detected_total",
    help_text="Detected context loss events (repeated questions, forgotten context)",
    labels=["loss_type"],  # "repeat_question", "forgotten_fact", "repeat_tool"
)

repeat_tool_invocation = Counter(
    name="pythinker_repeat_tool_invocation_total",
    help_text="Tool invocations that repeat previous identical calls",
    labels=["tool_name"],
)

checkpoint_written_total = Counter(
    name="pythinker_checkpoint_written_total",
    help_text="Execution checkpoints written to memory",
    labels=["checkpoint_type"],  # "incremental", "final"
)

session_summary_written_total = Counter(
    name="pythinker_session_summary_written_total",
    help_text="Session summaries written to long-term memory",
    labels=["outcome"],  # "success", "failure"
)

memory_budget_pressure_high = Counter(
    name="pythinker_memory_budget_pressure_high_total",
    help_text="Events where context pressure exceeded 0.8",
    labels=[],  # Removed session_id - use logs for per-session tracking
)

memory_budget_exhausted = Counter(
    name="pythinker_memory_budget_exhausted_total",
    help_text="Events where memory budget was exhausted",
    labels=[],
)

# Phase 6: Semantic Cache & Circuit Breaker Metrics
semantic_cache_query_total = Counter(
    name="pythinker_semantic_cache_query_total",
    help_text="Total semantic cache queries",
    labels=["result"],  # "hit", "miss", "error", "bypassed"
)

semantic_cache_hit_total = Counter(
    name="pythinker_semantic_cache_hit_total",
    help_text="Total semantic cache hits",
    labels=[],
)

semantic_cache_miss_total = Counter(
    name="pythinker_semantic_cache_miss_total",
    help_text="Total semantic cache misses",
    labels=[],
)

semantic_cache_store_total = Counter(
    name="pythinker_semantic_cache_store_total",
    help_text="Total responses stored in semantic cache",
    labels=["success"],  # "true", "false"
)

semantic_cache_circuit_breaker_state = Gauge(
    name="pythinker_semantic_cache_circuit_breaker_state",
    help_text="Circuit breaker state (0=CLOSED/healthy, 1=OPEN/bypassed, 2=HALF_OPEN/testing)",
    labels=[],
)

semantic_cache_hit_rate = Gauge(
    name="pythinker_semantic_cache_hit_rate",
    help_text="Current semantic cache hit rate (0-1)",
    labels=[],
)

semantic_cache_circuit_transitions_total = Counter(
    name="pythinker_semantic_cache_circuit_transitions_total",
    help_text="Circuit breaker state transitions",
    labels=["from_state", "to_state"],  # "CLOSED", "OPEN", "HALF_OPEN"
)

# Capacity Planning Metrics
qdrant_collection_size = Gauge(
    name="pythinker_qdrant_collection_size",
    help_text="Number of vectors in Qdrant collection",
    labels=["collection"],
)

qdrant_collection_growth_rate = Gauge(
    name="pythinker_qdrant_collection_growth_rate",
    help_text="Vector growth rate (vectors per hour)",
    labels=["collection"],
)

memory_budget_tokens_used = Gauge(
    name="pythinker_memory_budget_tokens_used",
    help_text="Current memory budget token usage",
    labels=["user_id"],
)

memory_budget_tokens_total = Gauge(
    name="pythinker_memory_budget_tokens_total",
    help_text="Total memory budget tokens available",
    labels=["user_id"],
)

memory_budget_pressure = Gauge(
    name="pythinker_memory_budget_pressure",
    help_text="Current memory budget pressure ratio (0-1)",
    labels=["user_id"],
)

cache_eviction_rate = Gauge(
    name="pythinker_cache_eviction_rate",
    help_text="Cache eviction rate (evictions per minute)",
    labels=["cache_type"],  # "semantic", "redis", "prompt"
)

session_duration_seconds = Histogram(
    name="pythinker_session_duration_seconds",
    help_text="Session duration distribution",
    labels=["outcome"],  # "success", "failure", "timeout"
    buckets=[60, 300, 900, 1800, 3600, 7200, 14400],  # 1m, 5m, 15m, 30m, 1h, 2h, 4h
)

qdrant_disk_usage_bytes = Gauge(
    name="pythinker_qdrant_disk_usage_bytes",
    help_text="Qdrant storage disk usage in bytes",
    labels=["collection"],
)

qdrant_query_duration_seconds = Histogram(
    name="pythinker_qdrant_query_duration_seconds",
    help_text="Qdrant query duration in seconds",
    labels=["operation", "collection"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

# Register additional metrics defined after the base registry
_metrics_registry.extend(
    [
        http_pool_connections_total,
        http_pool_requests_total,
        http_pool_request_latency,
        http_pool_errors_total,
        http_pool_pool_exhaustion_total,
        # API Key Pool Metrics
        api_key_selections_total,
        api_key_exhaustions_total,
        api_key_health_score,
        api_key_latency_seconds,
        api_key_early_recoveries_total,
        search_key_pool_healthy_keys,
        hallucination_span_confidence,
        workflow_phase_duration,
        workflow_phase_transitions,
        tool_selection_accuracy,
        plan_modifications_total,
        plan_verification_total,
        reflection_checks_total,
        reflection_triggers_total,
        reflection_decisions_total,
        reward_hacking_signals_total,
        tool_trace_anomalies_total,
        failure_prediction_total,
        failure_prediction_probability,
        intent_classification_total,
        response_policy_mode_total,
        compression_rejected_total,
        clarification_requested_total,
        clarification_resolved_total,
        clarification_wait_seconds,
        user_stop_before_done_total,
        fast_ack_refiner_total,
        fast_ack_refiner_latency_seconds,
        final_response_tokens,
        delivery_integrity_gate_result_total,
        delivery_integrity_gate_warning_total,
        delivery_integrity_gate_block_reason_total,
        delivery_integrity_stream_truncation_total,
        # Phase 4: Grounding Safety Metrics
        grounded_claims_total,
        hallucination_detected_total,
        evidence_caveat_total,
        evidence_rejection_total,
        evidence_contradiction_total,
        # Phase 5: Long-Context Pressure & Context Loss Metrics
        context_loss_detected,
        repeat_tool_invocation,
        checkpoint_written_total,
        session_summary_written_total,
        memory_budget_pressure_high,
        memory_budget_exhausted,
        # Phase 6: Semantic Cache & Circuit Breaker Metrics
        semantic_cache_query_total,
        semantic_cache_hit_total,
        semantic_cache_miss_total,
        semantic_cache_store_total,
        semantic_cache_circuit_breaker_state,
        semantic_cache_hit_rate,
        semantic_cache_circuit_transitions_total,
        # Capacity Planning Metrics
        qdrant_collection_size,
        qdrant_collection_growth_rate,
        memory_budget_tokens_used,
        memory_budget_tokens_total,
        memory_budget_pressure,
        cache_eviction_rate,
        session_duration_seconds,
        qdrant_disk_usage_bytes,
        qdrant_query_duration_seconds,
        # Security Gate (Task 7)
        security_gate_blocks_total,
        security_gate_overrides_total,
        # Token Authentication Security (fail-closed)
        token_auth_fail_closed_total,
        # Agent Robustness (2026-02-13 plan)
        entity_drift_detected_total,
        output_relevance_failures_total,
        step_name_quality_violations_total,
        guardrail_tripwire_total,
        delivery_fidelity_blocks_total,
        guardrail_latency_seconds,
        output_relevance_score,
        # Admin Authorization Security
        admin_unauthorized_access_total,
        metrics_auth_failure_total,
    ]
)

# Conversation Context Metrics (real-time session vectorization)
conversation_context_turns_stored = Counter(
    name="pythinker_conversation_context_turns_stored_total",
    help_text="Total conversation turns stored to Qdrant",
    labels=["role", "event_type"],
)

conversation_context_flush_duration = Histogram(
    name="pythinker_conversation_context_flush_duration_seconds",
    help_text="Time to flush conversation context buffer to Qdrant",
    labels=[],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

conversation_context_retrieval_duration = Histogram(
    name="pythinker_conversation_context_retrieval_duration_seconds",
    help_text="Time to retrieve conversation context",
    labels=["source"],  # sliding_window, intra_session, cross_session
    buckets=[0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

conversation_context_embed_errors = Counter(
    name="pythinker_conversation_context_embed_errors_total",
    help_text="Embedding errors during conversation context storage",
    labels=[],
)

_metrics_registry.extend(
    [
        conversation_context_turns_stored,
        conversation_context_flush_duration,
        conversation_context_retrieval_duration,
        conversation_context_embed_errors,
    ]
)

# --- Infrastructure Metrics (Phases 1-4) ---

# Phase 1A: Event Store Archival
event_store_archived_total = Counter(
    name="pythinker_event_store_archived_total",
    help_text="Total events archived from agent_events to archive collection",
    labels=[],
)
event_store_archival_runs = Counter(
    name="pythinker_event_store_archival_runs_total",
    help_text="Total archival task executions",
    labels=["status"],  # "success" | "error"
)

# Phase 3A: MinIO Retry & Failure
minio_operation_retries_total = Counter(
    name="pythinker_minio_operation_retries_total",
    help_text="Total MinIO operation retries",
    labels=["operation"],
)

minio_operation_failures_total = Counter(
    name="pythinker_minio_operation_failures_total",
    help_text="Total MinIO operation final failures after retry exhaustion",
    labels=["operation"],
)

# Phase 4A: Infrastructure Latency SLOs
mongodb_operation_duration_seconds = Histogram(
    name="pythinker_mongodb_operation_duration_seconds",
    help_text="MongoDB operation duration in seconds",
    labels=["operation", "collection"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

minio_operation_duration_seconds = Histogram(
    name="pythinker_minio_operation_duration_seconds",
    help_text="MinIO operation duration in seconds",
    labels=["operation", "bucket"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

slo_violations_total = Counter(
    name="pythinker_slo_violations_total",
    help_text="Total SLO violations by service",
    labels=["service", "operation"],
)

# Phase 4B: MongoDB Slow Query Profiler
mongodb_slow_queries_total = Counter(
    name="pythinker_mongodb_slow_queries_total",
    help_text="Total slow MongoDB queries detected by profiler",
    labels=["collection", "operation"],
)

# Phase 2.2-2.5: Deep Health Metrics (WiredTiger, Redis INFO, Qdrant collection stats)
mongodb_wiredtiger_cache_bytes = Gauge(
    name="pythinker_mongodb_wiredtiger_cache_bytes",
    help_text="WiredTiger cache usage in bytes",
    labels=["type"],  # "current", "max", "dirty"
)

mongodb_connections_current = Gauge(
    name="pythinker_mongodb_connections_current",
    help_text="Current MongoDB connections",
    labels=[],
)

redis_memory_bytes = Gauge(
    name="pythinker_redis_memory_bytes",
    help_text="Redis memory usage in bytes",
    labels=["type"],  # "used", "max"
)

redis_keyspace_hit_ratio = Gauge(
    name="pythinker_redis_keyspace_hit_ratio",
    help_text="Redis keyspace hit ratio (0-1)",
    labels=[],
)

# Phase 7A: MongoDB COLLSCAN detection
mongodb_collscan_total = Counter(
    name="pythinker_mongodb_collscan_total",
    help_text="Total COLLSCAN (full table scan) operations detected by profiler",
    labels=["collection", "operation"],
)

# Phase 6.2: Semantic failure tracking for LLM JSON output
llm_json_parse_failures_total = Counter(
    name="pythinker_llm_json_parse_failures_total",
    help_text="Total LLM JSON parse failures (malformed output)",
    labels=["model", "method"],
)

structured_output_requests_total = Counter(
    name="pythinker_structured_output_requests_total",
    help_text="Total structured output requests by tier and selected strategy",
    labels=["tier", "strategy"],
)

structured_output_success_total = Counter(
    name="pythinker_structured_output_success_total",
    help_text="Total successful structured output responses by tier and strategy",
    labels=["tier", "strategy"],
)

structured_output_fallback_total = Counter(
    name="pythinker_structured_output_fallback_total",
    help_text="Total structured output fallbacks by tier and strategy",
    labels=["tier", "strategy"],
)

structured_output_schema_retries_total = Counter(
    name="pythinker_structured_output_schema_retries_total",
    help_text="Total structured output schema retry attempts",
    labels=["tier", "strategy"],
)

structured_output_refusals_total = Counter(
    name="pythinker_structured_output_refusals_total",
    help_text="Total structured output refusals",
    labels=["tier", "strategy"],
)

structured_output_truncations_total = Counter(
    name="pythinker_structured_output_truncations_total",
    help_text="Total structured output truncations",
    labels=["tier", "strategy"],
)

structured_output_content_filter_total = Counter(
    name="pythinker_structured_output_content_filter_total",
    help_text="Total structured output responses blocked by content filters",
    labels=["tier", "strategy"],
)

_metrics_registry.extend(
    [
        event_store_archived_total,
        event_store_archival_runs,
        minio_operation_retries_total,
        minio_operation_failures_total,
        mongodb_operation_duration_seconds,
        minio_operation_duration_seconds,
        slo_violations_total,
        mongodb_slow_queries_total,
        # Deep health metrics
        mongodb_wiredtiger_cache_bytes,
        mongodb_connections_current,
        redis_memory_bytes,
        redis_keyspace_hit_ratio,
        mongodb_collscan_total,
        llm_json_parse_failures_total,
        structured_output_requests_total,
        structured_output_success_total,
        structured_output_fallback_total,
        structured_output_schema_retries_total,
        structured_output_refusals_total,
        structured_output_truncations_total,
        structured_output_content_filter_total,
    ]
)


# URL Failure Guard metrics
url_guard_actions_total = Counter(
    name="pythinker_url_failure_guard_actions_total",
    help_text="Total URL guard actions by tier and action type",
    labels=["tier", "action"],
)

url_guard_escalations_total = Counter(
    name="pythinker_url_failure_guard_escalations_total",
    help_text="URLs that escalated to higher tiers",
    labels=["tier"],
)

url_guard_tracked_urls = Gauge(
    name="pythinker_url_failure_guard_tracked_urls",
    help_text="Current number of failed URLs tracked in session",
    labels=[],
)

_metrics_registry.extend(
    [
        url_guard_actions_total,
        url_guard_escalations_total,
        url_guard_tracked_urls,
    ]
)


# --- Infrastructure Helper Functions ---


def record_mongodb_operation(operation: str, collection: str, duration: float, slo_threshold: float = 0.1) -> None:
    """Record a MongoDB operation with SLO violation detection."""
    mongodb_operation_duration_seconds.observe({"operation": operation, "collection": collection}, duration)
    if duration > slo_threshold:
        slo_violations_total.inc({"service": "mongodb", "operation": operation})


def record_minio_operation(operation: str, bucket: str, duration: float, slo_threshold: float = 0.5) -> None:
    """Record a MinIO operation with SLO violation detection."""
    minio_operation_duration_seconds.observe({"operation": operation, "bucket": bucket}, duration)
    if duration > slo_threshold:
        slo_violations_total.inc({"service": "minio", "operation": operation})


def record_channel_link_code_generated(channel: str) -> None:
    """Record generation of a short-lived channel link code."""
    channel_link_code_generated_total.inc({"channel": channel or "unknown"})


def record_channel_link_redeemed(channel: str) -> None:
    """Record successful redemption of a channel link code."""
    channel_link_redeemed_total.inc({"channel": channel or "unknown"})


def record_channel_link_redeem_failed(reason: str) -> None:
    """Record failed channel link code redemption."""
    channel_link_redeem_failed_total.inc({"reason": reason or "unknown"})


def record_llm_call(
    model: str,
    status: str,
    latency: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
) -> None:
    """Record an LLM call with all associated metrics.

    Args:
        model: Model name
        status: "success" or "error"
        latency: Latency in seconds
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        cached_tokens: Number of cached tokens
    """
    llm_calls_total.inc({"model": model, "status": status})
    llm_latency.observe({"model": model}, latency)

    if prompt_tokens > 0:
        tokens_total.inc({"type": "prompt"}, prompt_tokens)
    if completion_tokens > 0:
        tokens_total.inc({"type": "completion"}, completion_tokens)
    if cached_tokens > 0:
        tokens_total.inc({"type": "cached"}, cached_tokens)


def record_tool_call(
    tool: str,
    status: str,
    latency: float,
) -> None:
    """Record a tool execution with associated metrics.

    Args:
        tool: Tool name
        status: "success" or "error"
        latency: Latency in seconds
    """
    tool_calls_total.inc({"tool": tool, "status": status})
    tool_latency.observe({"tool": tool}, latency)


def record_screenshot_capture(
    trigger: str,
    status: str,
    latency: float,
    size_bytes: int = 0,
) -> None:
    """Record screenshot capture metrics.

    Args:
        trigger: Screenshot trigger type
        status: "success" or "error"
        latency: Capture latency in seconds
        size_bytes: Captured image size in bytes
    """
    normalized_trigger = (trigger or "").strip().lower() or "unknown"
    normalized_status = (status or "").strip().lower()
    if normalized_status not in {"success", "error"}:
        normalized_status = "error"

    screenshot_captures_total.inc({"trigger": normalized_trigger, "status": normalized_status})
    screenshot_capture_latency.observe({"trigger": normalized_trigger, "status": normalized_status}, latency)

    if normalized_status == "success" and size_bytes > 0:
        screenshot_capture_size_bytes.inc({"trigger": normalized_trigger}, size_bytes)


def record_screenshot_fetch(
    access: str,
    status: str,
    latency: float,
    size_bytes: int = 0,
) -> None:
    """Record screenshot fetch metrics.

    Args:
        access: "full" or "thumbnail"
        status: "success" or "error"
        latency: Fetch latency in seconds
        size_bytes: Served image size in bytes
    """
    normalized_access = (access or "").strip().lower()
    if normalized_access not in {"full", "thumbnail"}:
        normalized_access = "full"

    normalized_status = (status or "").strip().lower()
    if normalized_status not in {"success", "error"}:
        normalized_status = "error"

    screenshot_fetch_total.inc({"access": normalized_access, "status": normalized_status})
    screenshot_fetch_latency.observe({"access": normalized_access, "status": normalized_status}, latency)

    if normalized_status == "success" and size_bytes > 0:
        screenshot_fetch_size_bytes.inc({"access": normalized_access}, size_bytes)


def record_sandbox_health_check(status: str) -> None:
    """Record sandbox health check result.

    Priority 3: Sandbox Health Monitoring

    Args:
        status: "success", "failure", or "error"
    """
    normalized_status = (status or "").strip().lower()
    if normalized_status not in {"success", "failure", "error"}:
        normalized_status = "error"

    sandbox_health_check_total.inc({"status": normalized_status})


def record_sandbox_oom_kill() -> None:
    """Record sandbox OOM kill detection.

    Priority 3: Sandbox Health Monitoring
    """
    sandbox_oom_kills_total.inc({})


def record_security_gate_block(risk_level: str, pattern_type: str = "static") -> None:
    """Record security gate block (execution blocked).
    Args:
        risk_level: critical, high, or medium
        pattern_type: static or llm
    """
    security_gate_blocks_total.inc(
        {"risk_level": (risk_level or "unknown").lower(), "pattern_type": pattern_type or "static"}
    )


def record_security_gate_override(override_reason: str = "medium_risk_dev") -> None:
    """Record security gate override (MEDIUM allowed via config)."""
    security_gate_overrides_total.inc({"override_reason": override_reason or "unknown"})


def record_sandbox_runtime_crash() -> None:
    """Record sandbox runtime crash (non-OOM).

    Priority 3: Sandbox Health Monitoring
    """
    sandbox_runtime_crashes_total.inc({})


def record_plan_verification(result: str) -> None:
    """Record a plan verification outcome.

    Args:
        result: Outcome label (pass, revise, fail, skip, error)
    """
    normalized = (result or "").strip().lower()
    if normalized not in {"pass", "revise", "fail", "skip", "error"}:
        normalized = "error"
    plan_verification_total.inc({"result": normalized})


def record_reflection_check(result: str) -> None:
    """Record whether a reflection check triggered or skipped."""
    normalized = (result or "").strip().lower()
    if normalized not in {"triggered", "skipped"}:
        normalized = "skipped"
    reflection_checks_total.inc({"result": normalized})


def record_reflection_trigger(trigger: str) -> None:
    """Record reflection trigger type."""
    normalized = (trigger or "").strip().lower() or "unknown"
    reflection_triggers_total.inc({"trigger": normalized})


def record_reflection_decision(decision: str) -> None:
    """Record reflection decision."""
    normalized = (decision or "").strip().lower() or "unknown"
    reflection_decisions_total.inc({"decision": normalized})


def record_reward_hacking_signal(signal: str, severity: str) -> None:
    """Record a reward hacking detection signal."""
    normalized_signal = (signal or "").strip().lower() or "unknown"
    normalized_severity = (severity or "").strip().lower() or "unknown"
    reward_hacking_signals_total.inc({"signal": normalized_signal, "severity": normalized_severity})


def record_tool_trace_anomaly(tool: str, anomaly_type: str) -> None:
    """Record a tool tracing anomaly signal."""
    normalized_tool = (tool or "").strip().lower() or "unknown"
    normalized_type = (anomaly_type or "").strip().lower() or "unknown"
    tool_trace_anomalies_total.inc({"tool": normalized_tool, "type": normalized_type})


def record_failure_prediction(result: str, probability: float) -> None:
    """Record failure prediction outcome and probability."""
    normalized = (result or "").strip().lower()
    if normalized not in {"predicted", "clear"}:
        normalized = "clear"
    failure_prediction_total.inc({"result": normalized})
    failure_prediction_probability.observe({"result": normalized}, probability)


def record_error(error_type: str, component: str) -> None:
    """Record an error occurrence.

    Args:
        error_type: Type of error (e.g., "token_limit", "timeout")
        component: Component where error occurred
    """
    errors_total.inc({"type": error_type, "component": component})


def update_active_sessions(count: int) -> None:
    """Update the count of active sessions."""
    active_sessions.set({}, count)


def update_active_agents(count: int) -> None:
    """Update the count of active agents."""
    active_agents.set({}, count)


def record_sse_stream_open(endpoint: str = "chat") -> None:
    """Record a newly opened SSE stream."""
    normalized_endpoint = (endpoint or "").strip().lower() or "unknown"
    sse_stream_open_total.inc({"endpoint": normalized_endpoint})
    sse_stream_active.inc({"endpoint": normalized_endpoint}, 1.0)


def record_sse_stream_close(endpoint: str = "chat", reason: str = "unknown", duration_seconds: float = 0.0) -> None:
    """Record SSE stream closure and duration."""
    normalized_endpoint = (endpoint or "").strip().lower() or "unknown"
    normalized_reason = (reason or "").strip().lower() or "unknown"
    sse_stream_close_total.inc({"endpoint": normalized_endpoint, "reason": normalized_reason})
    sse_stream_duration_seconds.observe(
        {"endpoint": normalized_endpoint, "close_reason": normalized_reason},
        max(0.0, duration_seconds),
    )
    current_active = sse_stream_active.get({"endpoint": normalized_endpoint})
    if current_active <= 1.0:
        sse_stream_active.set({"endpoint": normalized_endpoint}, 0.0)
    else:
        sse_stream_active.dec({"endpoint": normalized_endpoint}, 1.0)


def record_sse_stream_heartbeat(endpoint: str = "chat") -> None:
    """Record heartbeat frames sent over SSE."""
    normalized_endpoint = (endpoint or "").strip().lower() or "unknown"
    sse_stream_heartbeat_total.inc({"endpoint": normalized_endpoint})


def record_sse_stream_error(endpoint: str = "chat", error_type: str = "unknown") -> None:
    """Record stream-level SSE error events."""
    normalized_endpoint = (endpoint or "").strip().lower() or "unknown"
    normalized_error_type = (error_type or "").strip().lower() or "unknown"
    sse_stream_error_total.inc({"endpoint": normalized_endpoint, "error_type": normalized_error_type})


def record_sse_stream_retry_suggestion(endpoint: str = "chat", reason: str = "unknown") -> None:
    """Record retry recommendations emitted to clients."""
    normalized_endpoint = (endpoint or "").strip().lower() or "unknown"
    normalized_reason = (reason or "").strip().lower() or "unknown"
    sse_stream_retry_suggested_total.inc({"endpoint": normalized_endpoint, "reason": normalized_reason})


def record_sse_resume_cursor_state(endpoint: str = "chat", state: str = "absent") -> None:
    """Record resume cursor state transitions for reconnect attempts."""
    normalized_endpoint = (endpoint or "").strip().lower() or "unknown"
    normalized_state = (state or "").strip().lower() or "unknown"
    if normalized_state not in {"found", "stale", "format_mismatch", "absent", "redis_cursor"}:
        normalized_state = "unknown"
    sse_resume_cursor_state_total.inc({"endpoint": normalized_endpoint, "state": normalized_state})


def record_sse_resume_cursor_fallback(endpoint: str = "chat", reason: str = "stale_cursor") -> None:
    """Record resume fallback reason when cursor-based replay cannot continue."""
    normalized_endpoint = (endpoint or "").strip().lower() or "unknown"
    normalized_reason = (reason or "").strip().lower() or "unknown"
    if normalized_reason not in {"stale_cursor", "format_mismatch", "missing_event_id"}:
        normalized_reason = "unknown"
    sse_resume_cursor_fallback_total.inc({"endpoint": normalized_endpoint, "reason": normalized_reason})


def record_sse_reconnect_first_non_heartbeat(endpoint: str = "chat", latency_seconds: float = 0.0) -> None:
    """Record reconnect latency until the first non-heartbeat event is emitted."""
    normalized_endpoint = (endpoint or "").strip().lower() or "unknown"
    sse_reconnect_first_non_heartbeat_seconds.observe(
        {"endpoint": normalized_endpoint},
        max(0.0, float(latency_seconds)),
    )


def record_sse_stream_event(endpoint: str = "chat", event_type: str = "unknown", phase: str | None = None) -> None:
    """Record each emitted SSE event for phase-aware event-rate queries."""
    normalized_endpoint = (endpoint or "").strip().lower() or "unknown"
    normalized_event_type = str(event_type or "").strip().lower() or "unknown"
    normalized_phase = str(phase or "").strip().lower() or "unknown"
    sse_stream_events_total.inc(
        {
            "endpoint": normalized_endpoint,
            "event_type": normalized_event_type,
            "phase": normalized_phase,
        }
    )


# Orphaned Task Cleanup Metric Functions
def record_orphaned_task_cleanup(
    orphaned_streams: int = 0,
    zombie_sessions: int = 0,
    duration_ms: float = 0.0,
    status: str = "success",
) -> None:
    """Record orphaned task cleanup operation metrics.

    Args:
        orphaned_streams: Number of orphaned Redis streams cleaned
        zombie_sessions: Number of zombie sessions marked as FAILED
        duration_ms: Cleanup operation duration in milliseconds
        status: Cleanup status ("success" or "error")
    """
    # Record cleanup run
    normalized_status = (status or "").strip().lower() or "unknown"
    orphaned_task_cleanup_runs_total.inc({"status": normalized_status})

    # Record cleaned resources
    if orphaned_streams > 0:
        orphaned_redis_streams_cleaned_total.inc({}, orphaned_streams)

    if zombie_sessions > 0:
        zombie_sessions_cleaned_total.inc({}, zombie_sessions)

    # Record duration
    if duration_ms > 0:
        orphaned_task_cleanup_duration_seconds.observe({}, duration_ms / 1000.0)


# Phase 6: Circuit Breaker Metric Functions
def record_circuit_breaker_state(name: str, state: str) -> None:
    """Record circuit breaker state.

    Args:
        name: Circuit breaker name
        state: State string ("closed", "half_open", "open")
    """
    state_map = {"closed": 0, "half_open": 1, "open": 2}
    circuit_breaker_state.set({"name": name}, state_map.get(state, 0))


def record_circuit_breaker_call(name: str, result: str) -> None:
    """Record a circuit breaker call result.

    Args:
        name: Circuit breaker name
        result: "success", "failure", or "rejected"
    """
    circuit_breaker_calls.inc({"name": name, "result": result})


def record_circuit_breaker_state_change(name: str, from_state: str, to_state: str) -> None:
    """Record a circuit breaker state transition.

    Args:
        name: Circuit breaker name
        from_state: Previous state
        to_state: New state
    """
    circuit_breaker_state_changes.inc({"name": name, "from_state": from_state, "to_state": to_state})


def record_circuit_breaker_failure_rate(name: str, rate: float) -> None:
    """Record a circuit breaker failure rate."""
    circuit_breaker_failure_rate.set({"name": name}, rate)


def record_circuit_breaker_threshold(name: str, threshold: int) -> None:
    """Record adaptive circuit breaker failure threshold."""
    circuit_breaker_threshold.set({"name": name}, threshold)


def record_circuit_breaker_recovery(name: str, result: str) -> None:
    """Record circuit breaker recovery attempts."""
    normalized = (result or "").strip().lower() or "attempt"
    circuit_breaker_recovery.inc({"name": name, "result": normalized})


def record_circuit_breaker_mttr(name: str, seconds: float) -> None:
    """Record circuit breaker mean time to recovery."""
    circuit_breaker_mttr.observe({"name": name}, seconds)


# Phase 6: LLM Concurrency Metric Functions
def update_llm_concurrent_requests(count: int) -> None:
    """Update the count of concurrent LLM requests."""
    llm_concurrent_requests.set({}, count)


def update_llm_queue_waiting(count: int) -> None:
    """Update the count of LLM requests waiting in queue."""
    llm_queue_waiting.set({}, count)


# Phase 6: Token Budget Metric Functions (Updated for aggregated metrics)
def record_token_budget_usage(tokens: int, warning: bool = False) -> None:
    """Record token budget usage.

    Args:
        tokens: Number of tokens used
        warning: Whether this represents a budget warning event (>80%)
    """
    token_budget_used.inc({}, tokens)
    if warning:
        token_budget_warnings.inc({})


def update_token_budget(session_id: str, used: int, remaining: int) -> None:
    """Update aggregated token budget metrics from per-session absolute values.

    This preserves the legacy adapter API while emitting only low-cardinality
    counters. `used` is treated as an absolute per-session value; this function
    records only the positive delta since the last update for that session.

    Args:
        session_id: Session identifier used only for in-process delta tracking
        used: Absolute number of tokens used in the session
        remaining: Remaining token budget in the session
    """
    normalized_session_id = (session_id or "").strip() or "unknown"
    safe_used = max(0, int(used))
    safe_remaining = max(0, int(remaining))

    previous_used = _token_budget_last_used_by_session.get(normalized_session_id, 0)
    delta_used = safe_used - previous_used

    # Handle resets/restarts where usage may decrease between updates.
    if delta_used < 0:
        delta_used = safe_used

    if delta_used > 0:
        token_budget_used.inc({}, delta_used)

    total_budget = safe_used + safe_remaining
    if total_budget > 0:
        utilization = safe_used / total_budget
        if utilization >= 0.8:
            if normalized_session_id not in _token_budget_warned_sessions:
                token_budget_warnings.inc({})
                _token_budget_warned_sessions.add(normalized_session_id)
        else:
            _token_budget_warned_sessions.discard(normalized_session_id)

    _token_budget_last_used_by_session[normalized_session_id] = safe_used


# Phase 6: Cache Metric Functions
def record_cache_hit(cache_type: str) -> None:
    """Record a cache hit.

    Args:
        cache_type: Type of cache ("embedding", "reasoning", "tool_result")
    """
    cache_hits.inc({"cache_type": cache_type})


def record_cache_miss(cache_type: str) -> None:
    """Record a cache miss.

    Args:
        cache_type: Type of cache ("embedding", "reasoning", "tool_result")
    """
    cache_misses.inc({"cache_type": cache_type})


def update_cache_size(cache_type: str, size: int) -> None:
    """Update cache size metric.

    Args:
        cache_type: Type of cache
        size: Current number of entries in cache
    """
    cache_size.set({"cache_type": cache_type}, size)


# Phase 1: HTTP Client Pool Metric Functions
def record_http_pool_request(
    client_name: str,
    status: str,
    latency: float,
) -> None:
    """Record an HTTP pool request.

    Args:
        client_name: Name of the HTTP client
        status: "success" or "error"
        latency: Request latency in seconds
    """
    http_pool_requests_total.inc({"client_name": client_name, "status": status})
    http_pool_request_latency.observe({"client_name": client_name}, latency)


def record_http_pool_error(client_name: str, error_type: str) -> None:
    """Record an HTTP pool error.

    Args:
        client_name: Name of the HTTP client
        error_type: Type of error (e.g., "timeout", "connection", "pool_exhaustion")
    """
    http_pool_errors_total.inc({"client_name": client_name, "error_type": error_type})

    if error_type == "pool_exhaustion":
        http_pool_pool_exhaustion_total.inc({"client_name": client_name})


def update_http_pool_connections(client_name: str, count: int) -> None:
    """Update the count of active HTTP pool connections.

    Args:
        client_name: Name of the HTTP client
        count: Number of active connections
    """
    http_pool_connections_total.set({"client_name": client_name}, count)


# ---------------------------------------------------------------------------
# PR-7: Prompt Optimization Metrics
# ---------------------------------------------------------------------------

prompt_profile_selection_total = Counter(
    name="pythinker_prompt_profile_selection_total",
    help_text="Number of prompt profile selection events",
    labels=["profile_id", "target", "mode"],
)

prompt_profile_fallback_total = Counter(
    name="pythinker_prompt_profile_fallback_total",
    help_text="Number of times the profile resolver fell back to baseline due to an error",
    labels=["reason"],
)

prompt_optimization_run_duration_seconds = Histogram(
    name="pythinker_prompt_optimization_run_duration_seconds",
    help_text="Duration of an offline prompt optimization run in seconds",
    labels=["optimizer"],
    buckets=[60, 300, 600, 1800, 3600, 7200],
)

prompt_optimization_score = Gauge(
    name="pythinker_prompt_optimization_score",
    help_text="Optimization score for a profile and target (0..1)",
    labels=["profile_id", "target", "metric"],
)

prompt_shadow_delta = Gauge(
    name="pythinker_prompt_shadow_delta",
    help_text="Delta metric computed in shadow mode (optimized - baseline)",
    labels=["metric", "target"],
)

_metrics_registry.extend(
    [
        prompt_profile_selection_total,
        prompt_profile_fallback_total,
        prompt_optimization_run_duration_seconds,
        prompt_optimization_score,
        prompt_shadow_delta,
    ]
)

# Live Shell Streaming Metrics
live_shell_polls_total = Counter(
    name="pythinker_live_shell_polls_total",
    help_text="Total live shell output polls",
    labels=["status"],  # status: success, error, empty
)

live_stream_events_total = Counter(
    name="pythinker_live_stream_events_total",
    help_text="Total live streaming events emitted",
    labels=["tool_name"],  # tool_name: shell, file_write, etc.
)

_metrics_registry.extend(
    [
        live_shell_polls_total,
        live_stream_events_total,
    ]
)

# ---------------------------------------------------------------------------
# Search API resilience metrics (search-resilience plan 2026-03-02)
# ---------------------------------------------------------------------------

search_429_total = Counter(
    name="pythinker_search_429_total",
    help_text="Total 429 rate-limit responses per search provider",
    labels=["provider"],
)

search_request_total = Counter(
    name="pythinker_search_request_total",
    help_text="Total search requests by provider and outcome",
    labels=["provider", "status"],  # status: success|rate_limited|error|circuit_open|cached
)

search_key_exhaustion_ratio = Gauge(
    name="pythinker_search_key_exhaustion_ratio",
    help_text="Ratio of exhausted API keys to total keys per provider (0.0-1.0)",
    labels=["provider"],
)

search_provider_health_score = Gauge(
    name="pythinker_search_provider_health_score",
    help_text="Composite provider health score (0.0=unhealthy, 1.0=healthy)",
    labels=["provider"],
)

search_cache_hit_total = Counter(
    name="pythinker_search_cache_hit_total",
    help_text="Search cache hits by tier",
    labels=["tier"],  # tier: hot|redis|miss
)

search_retry_total = Counter(
    name="pythinker_search_retry_total",
    help_text="Search request retries by provider",
    labels=["provider", "attempt"],  # attempt: 2|3 (first attempt not counted as retry)
)

_metrics_registry.extend(
    [
        search_429_total,
        search_request_total,
        search_key_exhaustion_ratio,
        search_provider_health_score,
        search_cache_hit_total,
        search_retry_total,
    ]
)


def record_profile_selection(
    profile_id: str,
    target: str,
    mode: str,
) -> None:
    """Record a prompt profile selection event."""
    prompt_profile_selection_total.inc({"profile_id": profile_id, "target": target, "mode": mode})


def record_profile_fallback(reason: str) -> None:
    """Record a profile resolver fallback to baseline."""
    prompt_profile_fallback_total.inc({"reason": reason})


def record_optimization_run_duration(optimizer: str, duration_seconds: float) -> None:
    """Record the wall-clock duration of an optimization run."""
    prompt_optimization_run_duration_seconds.observe({"optimizer": optimizer}, duration_seconds)


def record_optimization_score(profile_id: str, target: str, metric: str, score: float) -> None:
    """Update the optimization score gauge for a profile/target."""
    prompt_optimization_score.set({"profile_id": profile_id, "target": target, "metric": metric}, score)


def record_shadow_delta(metric: str, target: str, delta: float) -> None:
    """Record a shadow-mode delta (optimized - baseline) for a specific metric."""
    prompt_shadow_delta.set({"metric": metric, "target": target}, delta)


def collect_all_metrics() -> dict[str, Any]:
    """Collect all metrics for JSON export.

    Returns:
        Dictionary with all metrics data
    """
    all_metrics = []
    for metric in _metrics_registry:
        all_metrics.extend(metric.collect())

    return {
        "metrics": all_metrics,
        "timestamp": time.time(),
    }


def format_prometheus() -> str:
    """Format all metrics in Prometheus text exposition format.

    Returns:
        Prometheus-compatible text output
    """
    lines = []

    for metric in _metrics_registry:
        collected = metric.collect()
        if not collected:
            continue

        # Add HELP and TYPE comments
        lines.append(f"# HELP {metric.name} {metric.help_text}")

        if isinstance(metric, Counter):
            lines.append(f"# TYPE {metric.name} counter")
        elif isinstance(metric, Gauge):
            lines.append(f"# TYPE {metric.name} gauge")
        elif isinstance(metric, Histogram):
            lines.append(f"# TYPE {metric.name} histogram")

        # Add metric values
        for item in collected:
            labels = item.get("labels", {})
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items()) if labels else ""

            if item["type"] == "histogram":
                # Format histogram buckets
                for bucket, count in item["buckets"].items():
                    bucket_str = "+Inf" if bucket == float("inf") else str(bucket)
                    if label_str:
                        lines.append(f'{metric.name}_bucket{{{label_str},le="{bucket_str}"}} {count}')
                    else:
                        lines.append(f'{metric.name}_bucket{{le="{bucket_str}"}} {count}')

                # Add sum and count
                if label_str:
                    lines.append(f"{metric.name}_sum{{{label_str}}} {item['sum']}")
                    lines.append(f"{metric.name}_count{{{label_str}}} {item['count']}")
                else:
                    lines.append(f"{metric.name}_sum {item['sum']}")
                    lines.append(f"{metric.name}_count {item['count']}")
            else:
                # Counter or Gauge
                if label_str:
                    lines.append(f"{metric.name}{{{label_str}}} {item['value']}")
                else:
                    lines.append(f"{metric.name} {item['value']}")

    return "\n".join(lines) + "\n"


def reset_all_metrics() -> None:
    """Reset all metrics (for testing)."""
    for metric in _metrics_registry:
        with metric._lock:
            if hasattr(metric, "_values"):
                metric._values.clear()
            if hasattr(metric, "_observations"):
                metric._observations.clear()
    _token_budget_last_used_by_session.clear()
    _token_budget_warned_sessions.clear()
