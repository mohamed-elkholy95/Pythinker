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
        label_tuple = tuple(labels.get(l, "") for l in self.labels)
        with self._lock:
            self._values[label_tuple] += value

    def get(self, labels: dict[str, str]) -> float:
        """Get counter value for given labels."""
        label_tuple = tuple(labels.get(l, "") for l in self.labels)
        return self._values.get(label_tuple, 0.0)

    def collect(self) -> list[dict[str, Any]]:
        """Collect all metric values for export."""
        result = []
        with self._lock:
            for label_tuple, value in self._values.items():
                label_dict = dict(zip(self.labels, label_tuple))
                result.append({
                    "name": self.name,
                    "type": "counter",
                    "labels": label_dict,
                    "value": value,
                })
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
        label_tuple = tuple(labels.get(l, "") for l in self.labels)
        with self._lock:
            self._values[label_tuple] = value

    def inc(self, labels: dict[str, str], value: float = 1.0) -> None:
        """Increment gauge value."""
        label_tuple = tuple(labels.get(l, "") for l in self.labels)
        with self._lock:
            self._values[label_tuple] += value

    def dec(self, labels: dict[str, str], value: float = 1.0) -> None:
        """Decrement gauge value."""
        label_tuple = tuple(labels.get(l, "") for l in self.labels)
        with self._lock:
            self._values[label_tuple] -= value

    def get(self, labels: dict[str, str]) -> float:
        """Get gauge value for given labels."""
        label_tuple = tuple(labels.get(l, "") for l in self.labels)
        return self._values.get(label_tuple, 0.0)

    def collect(self) -> list[dict[str, Any]]:
        """Collect all metric values for export."""
        result = []
        with self._lock:
            for label_tuple, value in self._values.items():
                label_dict = dict(zip(self.labels, label_tuple))
                result.append({
                    "name": self.name,
                    "type": "gauge",
                    "labels": label_dict,
                    "value": value,
                })
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
        label_tuple = tuple(labels.get(l, "") for l in self.labels)
        with self._lock:
            self._observations[label_tuple].append(value)

    def collect(self) -> list[dict[str, Any]]:
        """Collect all metric values for export."""
        result = []
        with self._lock:
            for label_tuple, values in self._observations.items():
                label_dict = dict(zip(self.labels, label_tuple))

                # Calculate bucket counts
                bucket_counts = {}
                for bucket in self.buckets:
                    bucket_counts[bucket] = sum(1 for v in values if v <= bucket)
                bucket_counts[float('inf')] = len(values)

                # Calculate sum and count
                total_sum = sum(values)
                total_count = len(values)

                result.append({
                    "name": self.name,
                    "type": "histogram",
                    "labels": label_dict,
                    "buckets": bucket_counts,
                    "sum": total_sum,
                    "count": total_count,
                })
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

errors_total = Counter(
    name="pythinker_errors_total",
    help_text="Total number of errors",
    labels=["type", "component"],
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
    errors_total,
]


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
                    bucket_str = "+Inf" if bucket == float('inf') else str(bucket)
                    if label_str:
                        lines.append(f'{metric.name}_bucket{{{label_str},le="{bucket_str}"}} {count}')
                    else:
                        lines.append(f'{metric.name}_bucket{{le="{bucket_str}"}} {count}')

                # Add sum and count
                if label_str:
                    lines.append(f'{metric.name}_sum{{{label_str}}} {item["sum"]}')
                    lines.append(f'{metric.name}_count{{{label_str}}} {item["count"]}')
                else:
                    lines.append(f'{metric.name}_sum {item["sum"]}')
                    lines.append(f'{metric.name}_count {item["count"]}')
            else:
                # Counter or Gauge
                if label_str:
                    lines.append(f'{metric.name}{{{label_str}}} {item["value"]}')
                else:
                    lines.append(f'{metric.name} {item["value"]}')

    return "\n".join(lines) + "\n"


def reset_all_metrics() -> None:
    """Reset all metrics (for testing)."""
    for metric in _metrics_registry:
        with metric._lock:
            if hasattr(metric, '_values'):
                metric._values.clear()
            if hasattr(metric, '_observations'):
                metric._observations.clear()
