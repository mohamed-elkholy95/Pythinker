"""Analyze tool execution results for anomalies."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models.tool_result import ToolResult


@dataclass
class ResultAnalysis:
    """Analysis results for a tool execution."""

    size: int
    is_empty: bool
    error_like: bool
    anomalies: list[str] = field(default_factory=list)


class ResultAnalyzer:
    """Detect anomalies in tool results."""

    MAX_RESULT_CHARS = 10000

    def analyze(self, result: ToolResult | None) -> ResultAnalysis:
        if result is None:
            return ResultAnalysis(size=0, is_empty=True, error_like=True, anomalies=["missing_result"])

        text = result.data if result.data is not None else result.message or ""
        text_str = str(text)
        size = len(text_str)
        is_empty = size == 0
        error_like = not result.success or "error" in text_str.lower()

        anomalies: list[str] = []
        if is_empty:
            anomalies.append("empty_result")
        if size > self.MAX_RESULT_CHARS:
            anomalies.append("oversized_result")
        if not result.success:
            anomalies.append("error_result")
        if result.success and "traceback" in text_str.lower():
            anomalies.append("traceback_in_success")

        return ResultAnalysis(size=size, is_empty=is_empty, error_like=error_like, anomalies=anomalies)
