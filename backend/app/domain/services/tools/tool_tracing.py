"""Tool tracing with parameter validation and result analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.result_analyzer import ResultAnalyzer
from app.domain.services.tools.schemas import get_schema_for_tool
from app.infrastructure.observability.prometheus_metrics import record_tool_trace_anomaly

logger = logging.getLogger(__name__)


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
            timestamp=datetime.now(),
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
            record_tool_trace_anomaly(tool=tool_name, anomaly_type=anomaly)

        if trace.anomalies:
            logger.debug(
                "Tool tracing anomalies detected",
                extra={
                    "tool_name": tool_name,
                    "anomalies": trace.anomalies,
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

    def _detect_injection(self, arguments: dict[str, Any]) -> bool:
        patterns = [
            "ignore previous",
            "system prompt",
            "developer message",
            "instruction override",
            "bypass",
            "jailbreak",
        ]
        serialized = " ".join(str(value).lower() for value in arguments.values())
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
