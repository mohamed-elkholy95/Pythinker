"""Detect potential reward hacking and gaming patterns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GamingSignal:
    """Detected gaming signal."""

    signal_type: str
    severity: str
    detail: str
    evidence: dict[str, Any] | None = None


class GamingDetector:
    """Heuristic detector for reward hacking patterns."""

    def __init__(
        self,
        repetitive_threshold: int = 3,
        failure_rate_threshold: float = 0.6,
        unique_tool_ratio_threshold: float = 0.8,
    ) -> None:
        self._repetitive_threshold = repetitive_threshold
        self._failure_rate_threshold = failure_rate_threshold
        self._unique_tool_ratio_threshold = unique_tool_ratio_threshold

    def detect(
        self,
        output: str,
        user_request: str,
        recent_actions: list[dict[str, Any]] | None = None,
        tool_traces: list[Any] | None = None,
    ) -> list[GamingSignal]:
        actions = recent_actions or []
        traces = tool_traces or []

        signals: list[GamingSignal] = []

        tool_names = [a.get("function_name") for a in actions if a.get("function_name")]

        if tool_names:
            # Repetitive tool calls
            recent = tool_names[-self._repetitive_threshold :]
            if len(recent) == self._repetitive_threshold and len(set(recent)) == 1:
                signals.append(
                    GamingSignal(
                        signal_type="repetitive_tool_calls",
                        severity="medium",
                        detail=f"Repeated {recent[0]} {self._repetitive_threshold} times in a row",
                        evidence={"tool": recent[0]},
                    )
                )

            # Random exploration: many unique tools in a short window
            unique_ratio = len(set(tool_names)) / max(1, len(tool_names))
            if len(tool_names) >= 5 and unique_ratio >= self._unique_tool_ratio_threshold:
                signals.append(
                    GamingSignal(
                        signal_type="random_tool_exploration",
                        severity="low",
                        detail=f"High tool diversity ratio {unique_ratio:.2f}",
                        evidence={"unique_tools": len(set(tool_names)), "total_tools": len(tool_names)},
                    )
                )

            # High failure rate
            failures = [a for a in actions if not a.get("success", True)]
            failure_rate = len(failures) / max(1, len(actions))
            if len(actions) >= 4 and failure_rate >= self._failure_rate_threshold:
                signals.append(
                    GamingSignal(
                        signal_type="high_failure_rate",
                        severity="medium",
                        detail=f"Failure rate {failure_rate:.0%} across recent actions",
                        evidence={"failures": len(failures), "total": len(actions)},
                    )
                )

        # Answer without tool usage when tooling expected
        if self._needs_tooling(user_request) and not tool_names and len(output) > 200:
            signals.append(
                GamingSignal(
                    signal_type="answer_without_tool_usage",
                    severity="medium",
                    detail="Output provided without tool usage despite tool-heavy request",
                    evidence={"request": user_request[:120]},
                )
            )

        # Parameter injection attempts
        injection_signal = self._detect_parameter_injection(traces)
        if injection_signal:
            signals.append(injection_signal)

        return signals

    def _needs_tooling(self, user_request: str) -> bool:
        request_lower = (user_request or "").lower()
        keywords = [
            "search",
            "browse",
            "look up",
            "find",
            "latest",
            "current",
            "today",
            "news",
            "verify",
        ]
        return any(word in request_lower for word in keywords)

    def _detect_parameter_injection(self, traces: list[Any]) -> GamingSignal | None:
        patterns = [
            "ignore previous",
            "system prompt",
            "developer message",
            "instruction override",
            "bypass",
            "jailbreak",
        ]
        for trace in traces:
            args_summary = getattr(trace, "args_summary", None)
            if args_summary is None and isinstance(trace, dict):
                args_summary = trace.get("args_summary")
            if not args_summary:
                continue
            serialized = str(args_summary).lower()
            if any(pattern in serialized for pattern in patterns):
                return GamingSignal(
                    signal_type="parameter_injection_attempt",
                    severity="high",
                    detail="Detected potential prompt injection patterns in tool parameters",
                    evidence={"patterns": [p for p in patterns if p in serialized][:3]},
                )
        return None
