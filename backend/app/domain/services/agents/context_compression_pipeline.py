"""Three-stage context compression pipeline.

Replaces scattered compaction logic in MemoryManager/SemanticCompressor/
TemporalCompressor with a unified, configurable pipeline:

1. **Summarize** — LLM-based summarization of verbose tool outputs
2. **Truncate** — Rule-based content truncation preserving structure
3. **Drop** — Priority-based message removal (lowest priority first)

Usage:
    pipeline = ContextCompressionPipeline(token_manager)
    compressed = await pipeline.compress(
        messages=messages,
        target_tokens=50000,
        preserve_recent=4,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.services.agents.token_manager import TokenManager

logger = logging.getLogger(__name__)


class CompressionStage(str, Enum):
    """Stages of the compression pipeline."""

    SUMMARIZE = "summarize"
    TRUNCATE = "truncate"
    DROP = "drop"


@dataclass
class CompressionResult:
    """Result of a compression pipeline run."""

    messages: list[dict[str, Any]]
    original_tokens: int
    final_tokens: int
    stages_applied: list[CompressionStage]
    messages_dropped: int = 0
    messages_summarized: int = 0
    messages_truncated: int = 0

    @property
    def tokens_saved(self) -> int:
        return self.original_tokens - self.final_tokens

    @property
    def compression_ratio(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return self.final_tokens / self.original_tokens


# Tool functions whose output is typically verbose and safe to summarize
_VERBOSE_TOOL_FUNCTIONS = frozenset(
    {
        "browser_view",
        "browser_navigate",
        "browser_get_content",
        "shell_exec",
        "file_read",
        "file_list",
        "file_list_directory",
        "info_search_web",
        "wide_research",
        "code_execute",
        "code_execute_python",
    }
)

# Maximum characters to preserve when summarizing tool output
_SUMMARIZE_MAX_CHARS = 500

# Maximum characters for truncation stage
_TRUNCATE_MAX_CHARS = 2000


class ContextCompressionPipeline:
    """Three-stage compression pipeline for conversation context.

    Each stage is applied only if the previous stage did not bring the
    total tokens below the target. Stages are applied in order:
    summarize → truncate → drop.
    """

    def __init__(
        self,
        token_manager: TokenManager,
        summarize_max_chars: int = _SUMMARIZE_MAX_CHARS,
        truncate_max_chars: int = _TRUNCATE_MAX_CHARS,
    ) -> None:
        self._token_manager = token_manager
        self._summarize_max_chars = summarize_max_chars
        self._truncate_max_chars = truncate_max_chars

    async def compress(
        self,
        messages: list[dict[str, Any]],
        target_tokens: int,
        preserve_recent: int = 4,
    ) -> CompressionResult:
        """Run the compression pipeline.

        Args:
            messages: Conversation messages to compress.
            target_tokens: Target token count to achieve.
            preserve_recent: Number of recent messages to preserve from
                aggressive compression.

        Returns:
            CompressionResult with the compressed messages and statistics.
        """
        original_tokens = self._token_manager.count_messages_tokens(messages)

        if original_tokens <= target_tokens:
            return CompressionResult(
                messages=messages,
                original_tokens=original_tokens,
                final_tokens=original_tokens,
                stages_applied=[],
            )

        stages_applied: list[CompressionStage] = []
        compressed = list(messages)
        msgs_summarized = 0
        msgs_truncated = 0
        msgs_dropped = 0

        # Stage 1: Summarize verbose tool outputs
        compressed, summarized = self._stage_summarize(compressed, preserve_recent)
        msgs_summarized = summarized
        current_tokens = self._token_manager.count_messages_tokens(compressed)
        if summarized > 0:
            stages_applied.append(CompressionStage.SUMMARIZE)
        if current_tokens <= target_tokens:
            return CompressionResult(
                messages=compressed,
                original_tokens=original_tokens,
                final_tokens=current_tokens,
                stages_applied=stages_applied,
                messages_summarized=msgs_summarized,
            )

        # Stage 2: Truncate long content
        compressed, truncated = self._stage_truncate(compressed, preserve_recent)
        msgs_truncated = truncated
        current_tokens = self._token_manager.count_messages_tokens(compressed)
        if truncated > 0:
            stages_applied.append(CompressionStage.TRUNCATE)
        if current_tokens <= target_tokens:
            return CompressionResult(
                messages=compressed,
                original_tokens=original_tokens,
                final_tokens=current_tokens,
                stages_applied=stages_applied,
                messages_summarized=msgs_summarized,
                messages_truncated=msgs_truncated,
            )

        # Stage 3: Drop low-priority messages
        compressed, _dropped_tokens = self._token_manager.trim_messages(
            compressed,
            preserve_recent=preserve_recent,
        )
        new_tokens = self._token_manager.count_messages_tokens(compressed)
        msgs_dropped = len(messages) - len(compressed) - msgs_summarized
        stages_applied.append(CompressionStage.DROP)

        logger.info(
            "Compression pipeline: %d→%d tokens (saved %d), stages=%s",
            original_tokens,
            new_tokens,
            original_tokens - new_tokens,
            [s.value for s in stages_applied],
        )

        return CompressionResult(
            messages=compressed,
            original_tokens=original_tokens,
            final_tokens=new_tokens,
            stages_applied=stages_applied,
            messages_dropped=msgs_dropped,
            messages_summarized=msgs_summarized,
            messages_truncated=msgs_truncated,
        )

    def _stage_summarize(
        self,
        messages: list[dict[str, Any]],
        preserve_recent: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Stage 1: Summarize verbose tool outputs.

        Replaces long tool results with compact summaries preserving
        key information (error status, result count, file names).

        Returns:
            Tuple of (modified messages, count of summarized messages).
        """
        result = []
        summarized_count = 0
        preserve_boundary = len(messages) - preserve_recent

        for i, msg in enumerate(messages):
            # Don't summarize recent messages
            if i >= preserve_boundary:
                result.append(msg)
                continue

            if msg.get("role") == "tool":
                content = msg.get("content", "")
                func_name = msg.get("name", "")

                if (
                    isinstance(content, str)
                    and len(content) > self._summarize_max_chars
                    and func_name in _VERBOSE_TOOL_FUNCTIONS
                ):
                    summary = self._extract_tool_summary(func_name, content)
                    summarized = dict(msg)
                    summarized["content"] = summary
                    result.append(summarized)
                    summarized_count += 1
                    continue

            result.append(msg)

        return result, summarized_count

    def _stage_truncate(
        self,
        messages: list[dict[str, Any]],
        preserve_recent: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Stage 2: Rule-based truncation of long content.

        Limits any non-system, non-recent message to truncate_max_chars.

        Returns:
            Tuple of (modified messages, count of truncated messages).
        """
        result = []
        truncated_count = 0
        preserve_boundary = len(messages) - preserve_recent

        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Never truncate system messages or recent messages
            if role == "system" or i >= preserve_boundary:
                result.append(msg)
                continue

            if isinstance(content, str) and len(content) > self._truncate_max_chars:
                truncated = dict(msg)
                truncated["content"] = (
                    content[: self._truncate_max_chars] + "\n\n[... content truncated for context management ...]"
                )
                result.append(truncated)
                truncated_count += 1
            else:
                result.append(msg)

        return result, truncated_count

    def _extract_tool_summary(self, func_name: str, content: str) -> str:
        """Extract a compact summary from verbose tool output."""
        lines = content.split("\n")
        total_lines = len(lines)

        # Common patterns
        has_error = any(kw in content.lower() for kw in ("error", "exception", "traceback", "failed"))
        has_success = any(kw in content.lower() for kw in ("success", "completed", "done", "ok"))

        status = "ERROR" if has_error else ("SUCCESS" if has_success else "OK")

        if func_name in ("browser_view", "browser_navigate", "browser_get_content"):
            # Extract title and URL if present
            title = ""
            url = ""
            for line in lines[:20]:
                if "title:" in line.lower():
                    title = line.strip()
                if "http" in line:
                    url = line.strip()[:200]
            return (
                f"[{func_name} summary] Status: {status}, "
                f"{total_lines} lines. {title} {url}\n"
                f"First content: {lines[0][:200] if lines else ''}"
            )

        if func_name == "shell_exec":
            # Preserve exit code and first/last lines
            first_lines = "\n".join(lines[:3])
            last_lines = "\n".join(lines[-3:]) if total_lines > 6 else ""
            return f"[{func_name} summary] Status: {status}, {total_lines} lines output.\nStart:\n{first_lines}\n" + (
                f"...\nEnd:\n{last_lines}" if last_lines else ""
            )

        if func_name in ("info_search_web", "wide_research"):
            # Count results
            result_count = content.count("http")
            return (
                f"[{func_name} summary] Status: {status}, "
                f"~{result_count} URLs found, {total_lines} lines.\n"
                f"Preview: {content[:300]}"
            )

        # Generic summarization
        return (
            f"[{func_name} summary] Status: {status}, "
            f"{total_lines} lines, ~{len(content)} chars.\n"
            f"Preview: {content[:300]}"
        )
