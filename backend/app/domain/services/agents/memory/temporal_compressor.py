"""Temporal compression for older, low-importance messages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.memory.importance_analyzer import ImportanceAnalyzer


@dataclass
class TemporalCompressionStats:
    compacted: int = 0
    tool_compacted: int = 0
    assistant_compacted: int = 0


SummaryBuilder = Callable[[dict[str, Any]], tuple[str, bool]]


class TemporalCompressor:
    """Compress older messages while preserving recent context."""

    def __init__(
        self,
        summary_builder: SummaryBuilder | None = None,
        tool_max_chars: int = 800,
        assistant_max_chars: int = 600,
    ) -> None:
        self._summary_builder = summary_builder or self._default_summary
        self._tool_max_chars = tool_max_chars
        self._assistant_max_chars = assistant_max_chars

    def compress(
        self,
        messages: list[dict[str, Any]],
        preserve_recent: int = 10,
        importance_analyzer: ImportanceAnalyzer | None = None,
    ) -> tuple[list[dict[str, Any]], TemporalCompressionStats]:
        stats = TemporalCompressionStats()
        total = len(messages)
        analyzer = importance_analyzer or ImportanceAnalyzer()
        compressed: list[dict[str, Any]] = []

        for idx, message in enumerate(messages):
            role = message.get("role")
            if idx >= max(0, total - preserve_recent):
                compressed.append(message)
                continue

            if message.get("_semantic_compacted"):
                compressed.append(message)
                continue

            if role in {"system", "user"}:
                compressed.append(message)
                continue

            content = str(message.get("content", ""))
            if "(compacted)" in content or "(removed)" in content:
                compressed.append(message)
                continue

            score = analyzer.score_message(message, idx, total, preserve_recent)

            if role == "tool":
                if len(content) <= self._tool_max_chars and not analyzer.is_low_importance(score.score, 0.6):
                    compressed.append(message)
                    continue

                summary, success = self._summary_builder(message)
                new_message = dict(message)
                new_message["content"] = ToolResult(
                    success=success,
                    data=f"Temporal summary: {summary}",
                ).model_dump_json()
                new_message["_temporal_compacted"] = True
                stats.compacted += 1
                stats.tool_compacted += 1
                compressed.append(new_message)
                continue

            if role == "assistant":
                if len(content) <= self._assistant_max_chars and not analyzer.is_low_importance(score.score, 0.7):
                    compressed.append(message)
                    continue

                truncated = content[: self._assistant_max_chars].replace("\n", " ").rstrip()
                if len(content) > self._assistant_max_chars:
                    truncated = truncated + "..."
                new_message = dict(message)
                new_message["content"] = f"{truncated} [truncated for context optimization]"
                new_message["_temporal_compacted"] = True
                stats.compacted += 1
                stats.assistant_compacted += 1
                compressed.append(new_message)
                continue

            compressed.append(message)

        return compressed, stats

    @staticmethod
    def _default_summary(message: dict[str, Any]) -> tuple[str, bool]:
        content = str(message.get("content", ""))
        summary = content[:160].replace("\n", " ")
        if len(content) > 160:
            summary = summary.rstrip() + "..."
        return summary, True
