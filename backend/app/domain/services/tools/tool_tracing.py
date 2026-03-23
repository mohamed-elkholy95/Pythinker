"""Tool tracing with parameter validation and result analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.domain.external.observability import MetricsPort, get_null_metrics
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.result_analyzer import ResultAnalyzer
from app.domain.services.tools.schemas import get_schema_for_tool

logger = logging.getLogger(__name__)

# Module-level metrics instance (can be overridden for testing)
_metrics: MetricsPort = get_null_metrics()

# Tools whose results are expected to exceed MAX_RESULT_CHARS.
# oversized_result anomalies are suppressed in logs for these tools.
_LARGE_RESULT_TOOLS = frozenset({
    "info_search_web", "wide_research", "search",
    "browser_get_content", "browser_navigate",
})


def set_metrics(metrics: MetricsPort) -> None:
    """Set the metrics instance for this module."""
    global _metrics
    _metrics = metrics


def _record_tool_trace_anomaly(tool: str, anomaly_type: str) -> None:
    """Record tool trace anomaly metric."""
    _metrics.record_tool_trace_anomaly(tool, anomaly_type)


@dataclass
class ToolTrace:
    """Record of a single tool execution trace."""

    tool_name: str
    timestamp: datetime
    duration_ms: float
    success: bool
    args_summary: dict[str, str] = field(default_factory=dict)
    result_size: int = 0
    anomalies: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    error: str | None = None


class ToolTracer:
    """Trace tool executions for validation and anomaly detection."""

    def __init__(self, history_limit: int = 200, arg_value_limit: int = 160) -> None:
        self._history: list[ToolTrace] = []
        self._history_limit = history_limit
        self._arg_value_limit = arg_value_limit
        self._result_analyzer = ResultAnalyzer()

    def trace_execution(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult | None,
        duration_ms: float,
        error: str | None = None,
    ) -> ToolTrace:
        validation_errors: list[str] = []
        anomalies: list[str] = []

        # Schema validation (non-blocking)
        schema = get_schema_for_tool(tool_name)
        if schema is not None:
            try:
                schema(**arguments)
            except ValidationError as exc:
                validation_errors = [err.get("msg", "validation error") for err in exc.errors()]
                anomalies.append("args_validation_failed")
            except Exception as exc:
                validation_errors = [str(exc)[:200]]
                anomalies.append("args_validation_failed")

        # Parameter injection heuristics
        if self._detect_injection(arguments):
            anomalies.append("param_injection_pattern")

        # Result analysis
        analysis = self._result_analyzer.analyze(result)
        anomalies.extend(analysis.anomalies)

        trace = ToolTrace(
            tool_name=tool_name,
            timestamp=datetime.now(UTC),
            duration_ms=duration_ms,
            success=result.success if result else False,
            args_summary=self._summarize_args(arguments),
            result_size=analysis.size,
            anomalies=_dedupe(anomalies),
            validation_errors=validation_errors,
            error=error,
        )

        self._history.append(trace)
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit :]

        for anomaly in trace.anomalies:
            _record_tool_trace_anomaly(tool=tool_name, anomaly_type=anomaly)

        if trace.anomalies:
            # Filter out expected anomalies for specific tool categories
            # to reduce log noise.  Search/research tools legitimately
            # return 10K-30K chars of enriched results.
            log_anomalies = trace.anomalies
            if tool_name in _LARGE_RESULT_TOOLS:
                log_anomalies = [a for a in trace.anomalies if a != "oversized_result"]

            if log_anomalies:
                # Use warning for validation failures (indicates LLM generating bad
                # tool args), info for oversized_result (expected for large web pages).
                has_validation_failure = any(a == "args_validation_failed" for a in log_anomalies)
                log_fn = logger.warning if has_validation_failure else logger.info
                log_fn(
                    "Tool tracing anomalies: %s on %s",
                    ", ".join(log_anomalies),
                    tool_name,
                    extra={
                        "tool_name": tool_name,
                        "anomalies": log_anomalies,
                        "validation_errors": trace.validation_errors,
                    },
                )

        return trace

    def get_recent_traces(self, limit: int = 20, tool_name: str | None = None) -> list[ToolTrace]:
        traces = self._history
        if tool_name:
            traces = [trace for trace in traces if trace.tool_name == tool_name]
        return traces[-limit:]

    def reset(self) -> None:
        self._history.clear()

    def _summarize_args(self, arguments: dict[str, Any]) -> dict[str, str]:
        summary: dict[str, str] = {}
        redaction_keys = {"key", "token", "secret", "password", "auth"}
        for key, value in arguments.items():
            key_lower = key.lower()
            if any(redact in key_lower for redact in redaction_keys):
                summary[key] = "[redacted]"
                continue
            value_str = str(value)
            if len(value_str) > self._arg_value_limit:
                summary[key] = f"{value_str[: self._arg_value_limit]}..."
            else:
                summary[key] = value_str
        return summary

    # Argument keys that carry instructions/commands and should be checked
    # for injection.  Bulk content fields (file body, report text) are
    # excluded to avoid false positives — a cybersecurity report mentioning
    # "bypass" or "system prompt injection" is normal, not an attack.
    _INJECTION_CHECK_KEYS = frozenset({
        "command", "cmd", "query", "path", "url", "name",
        "working_directory", "session_id", "tool_name",
        "search_query", "input", "selector", "text",
    })

    def _detect_injection(self, arguments: dict[str, Any]) -> bool:
        patterns = [
            "ignore previous",
            "ignore all previous instructions",
            "system prompt",
            "developer message",
            "instruction override",
            "jailbreak",
            "disregard above",
            "forget your instructions",
        ]
        # Only check instruction-carrying arguments, not bulk content fields
        # like file body.  This eliminates false positives from cybersecurity
        # reports, AI discussions, etc. that naturally contain these terms.
        values_to_check: list[str] = []
        for key, value in arguments.items():
            key_lower = key.lower()
            if key_lower in self._INJECTION_CHECK_KEYS:
                values_to_check.append(str(value).lower())
            elif key_lower not in {"content", "body", "data", "file_content", "text_content"}:
                # For unknown keys, check short values only (instructions tend
                # to be short; large blobs are likely content).
                val_str = str(value)
                if len(val_str) <= 500:
                    values_to_check.append(val_str.lower())
        if not values_to_check:
            return False
        serialized = " ".join(values_to_check)
        return any(pattern in serialized for pattern in patterns)


_global_tracer: ToolTracer | None = None


def get_tool_tracer() -> ToolTracer:
    """Get or create the global tool tracer instance."""
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = ToolTracer()
    return _global_tracer


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
