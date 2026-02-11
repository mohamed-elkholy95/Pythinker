"""Prometheus Metrics for Pythinker

Provides Prometheus-compatible metrics collection and export.
Supports counters, gauges, and histograms for LLM, tool, and session metrics.

Usage:
    from app.infrastructure.observability.prometheus_metrics import (
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

    def inc(self, labels: dict[str, str], value: float = 1.0) -> None:
        """Increment counter with given labels."""
        label_tuple = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            self._values[label_tuple] += value

    def get(self, labels: dict[str, str]) -> float:
        """Get counter value for given labels."""
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

    def set(self, labels: dict[str, str], value: float) -> None:
        """Set gauge value for given labels."""
        label_tuple = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            self._values[label_tuple] = value

    def inc(self, labels: dict[str, str], value: float = 1.0) -> None:
        """Increment gauge value."""
        label_tuple = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            self._values[label_tuple] += value

    def dec(self, labels: dict[str, str], value: float = 1.0) -> None:
        """Decrement gauge value."""
        label_tuple = tuple(labels.get(label, "") for label in self.labels)
        with self._lock:
            self._values[label_tuple] -= value

    def get(self, labels: dict[str, str]) -> float:
        """Get gauge value for given labels."""
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

    def observe(self, labels: dict[str, str], value: float) -> None:
        """Record an observation."""
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

# Phase 6: Token Budget Metrics
token_budget_used = Gauge(
    name="pythinker_token_budget_used",
    help_text="Tokens used in current session",
    labels=["session_id"],
)

token_budget_remaining = Gauge(
    name="pythinker_token_budget_remaining",
    help_text="Tokens remaining in current session budget",
    labels=["session_id"],
)

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
    token_budget_remaining,
    # Phase 6: Cache
    cache_hits,
    cache_misses,
    cache_size,
]

# Workflow Phase Metrics (Monitoring Enhancement)
workflow_phase_duration = Histogram(
    name="pythinker_workflow_phase_duration_seconds",
    help_text="Duration of workflow phases",
    labels=["phase", "session_id"],
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

# Phase 4: Grounding Safety Metrics
grounded_claim_ratio = Gauge(
    name="pythinker_grounded_claim_ratio",
    help_text="Ratio of claims supported by high-confidence evidence",
    labels=["session_id"],
)

hallucination_rate = Gauge(
    name="pythinker_hallucination_rate",
    help_text="Rate of detected hallucinations per response",
    labels=["session_id"],
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

memory_budget_pressure = Gauge(
    name="pythinker_memory_budget_pressure",
    help_text="Context pressure signal (0.0-1.0, where 1.0 = at limit)",
    labels=["session_id"],
)

memory_budget_tokens = Gauge(
    name="pythinker_memory_budget_tokens",
    help_text="Dynamic memory token budget based on pressure",
    labels=["session_id"],
)

# Register additional metrics defined after the base registry
_metrics_registry.extend(
    [
        http_pool_connections_total,
        http_pool_requests_total,
        http_pool_request_latency,
        http_pool_errors_total,
        http_pool_pool_exhaustion_total,
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
        fast_ack_refiner_total,
        fast_ack_refiner_latency_seconds,
        final_response_tokens,
        delivery_integrity_gate_result_total,
        delivery_integrity_gate_warning_total,
        delivery_integrity_gate_block_reason_total,
        delivery_integrity_stream_truncation_total,
        # Phase 4: Grounding Safety Metrics
        grounded_claim_ratio,
        hallucination_rate,
        evidence_caveat_total,
        evidence_rejection_total,
        evidence_contradiction_total,
        # Phase 5: Long-Context Pressure & Context Loss Metrics
        context_loss_detected,
        repeat_tool_invocation,
        checkpoint_written_total,
        session_summary_written_total,
        memory_budget_pressure,
        memory_budget_tokens,
    ]
)


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


# Phase 6: Token Budget Metric Functions
def update_token_budget(session_id: str, used: int, remaining: int) -> None:
    """Update token budget metrics for a session.

    Args:
        session_id: Session identifier
        used: Tokens used so far
        remaining: Tokens remaining in budget
    """
    token_budget_used.set({"session_id": session_id}, used)
    token_budget_remaining.set({"session_id": session_id}, remaining)


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
