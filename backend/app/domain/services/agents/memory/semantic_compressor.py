"""Semantic compression helpers for deduplicating similar tool outputs."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.memory.importance_analyzer import ImportanceAnalyzer


@dataclass
class SemanticCompressionStats:
    compacted: int = 0
    duplicates: int = 0


SummaryBuilder = Callable[[dict[str, Any]], tuple[str, bool]]


class SemanticCompressor:
    """Deduplicate semantically similar tool outputs."""

    def __init__(self, summary_builder: SummaryBuilder | None = None) -> None:
        self._summary_builder = summary_builder or self._default_summary

    def compress(
        self,
        messages: list[dict[str, Any]],
        preserve_recent: int = 10,
        importance_analyzer: ImportanceAnalyzer | None = None,
    ) -> tuple[list[dict[str, Any]], SemanticCompressionStats]:
        stats = SemanticCompressionStats()
        total = len(messages)
        analyzer = importance_analyzer or ImportanceAnalyzer()

        seen: dict[str, str] = {}
        compressed: list[dict[str, Any]] = []

        for idx, message in enumerate(messages):
            role = message.get("role")
            if role != "tool":
                compressed.append(message)
                continue

            if idx >= max(0, total - preserve_recent):
                compressed.append(message)
                continue

            score = analyzer.score_message(message, idx, total, preserve_recent)
            if not analyzer.is_low_importance(score.score):
                compressed.append(message)
                continue

            content = str(message.get("content", ""))
            if "(compacted)" in content or "(removed)" in content:
                compressed.append(message)
                continue

            fingerprint = self._fingerprint(message)
            if fingerprint in seen:
                summary, success = self._summary_builder(message)
                new_message = dict(message)
                new_message["content"] = ToolResult(
                    success=success,
                    data=f"Duplicate tool output suppressed. Summary: {summary}",
                ).model_dump_json()
                new_message["_semantic_compacted"] = True
                stats.compacted += 1
                stats.duplicates += 1
                compressed.append(new_message)
            else:
                seen[fingerprint] = content
                compressed.append(message)

        return compressed, stats

    @staticmethod
    def _fingerprint(message: dict[str, Any]) -> str:
        function_name = message.get("function_name", "tool")
        content = str(message.get("content", ""))
        normalized = content.lower()
        normalized = re.sub(r"\d+", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return f"{function_name}:{normalized[:200]}"

    @staticmethod
    def _default_summary(message: dict[str, Any]) -> tuple[str, bool]:
        content = str(message.get("content", ""))
        summary = content[:140].replace("\n", " ")
        if len(content) > 140:
            summary = summary.rstrip() + "..."
        return summary, True
