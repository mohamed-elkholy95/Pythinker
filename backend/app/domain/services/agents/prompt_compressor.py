"""Smart Prompt Compression for Token Efficiency

Reduces token usage through intelligent compression:
1. Tool output summarization (long outputs -> key points)
2. Context deduplication (remove redundant info)
3. Dynamic prompt sizing (adjust based on complexity)
4. Message history pruning (keep recent + important)

Research shows aggressive context management can reduce
tokens by 40-60% without significant quality loss.
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class CompressionLevel(str, Enum):
    """Compression aggressiveness levels."""

    NONE = "none"  # No compression
    LIGHT = "light"  # Remove whitespace, trim
    MODERATE = "moderate"  # Summarize, remove redundancy
    AGGRESSIVE = "aggressive"  # Heavy summarization


@dataclass
class CompressionResult:
    """Result of compression operation."""

    original_tokens: int  # Estimated original token count
    compressed_tokens: int  # Estimated compressed token count
    compression_ratio: float  # 0-1, lower is more compressed
    content: str  # Compressed content
    items_removed: int  # Number of items/sections removed
    summary_generated: bool  # Whether summarization was applied


class PromptCompressor:
    """Compresses prompts and context to reduce token usage.

    Usage:
        compressor = PromptCompressor()

        # Compress tool output
        compressed = compressor.compress_tool_output(
            long_output,
            max_tokens=500
        )

        # Compress message history
        messages = compressor.compress_history(
            messages,
            keep_recent=5,
            max_tokens=4000
        )
    """

    # Approximate tokens per character (for estimation)
    TOKENS_PER_CHAR = 0.25

    # Patterns for content that can be safely reduced
    REDUCIBLE_PATTERNS: ClassVar[dict[str, Any]] = {
        # Repeated whitespace
        r"\n{3,}": "\n\n",
        r" {2,}": " ",
        r"\t+": " ",
        # Verbose logging patterns
        r"\[\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\]]*\]": "[timestamp]",
        r"DEBUG:.*?\n": "",
        r"INFO:.*?(?=\n[A-Z])": "",
        # Stack traces (keep first and last)
        r"(Traceback.*?\n(?:  File.*?\n)+)": lambda m: _summarize_traceback(m.group(1)),
        # Long paths
        r"/(?:home|Users)/[^/]+/": "~/",
        # UUIDs (keep first 8 chars)
        r"([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}": r"\1...",
    }

    # Content markers for importance detection
    IMPORTANT_MARKERS: ClassVar[list[str]] = [
        "error",
        "exception",
        "failed",
        "success",
        "warning",
        "result",
        "output",
        "created",
        "modified",
        "deleted",
        "important",
        "note",
        "todo",
        "fixme",
    ]

    def __init__(
        self,
        default_level: CompressionLevel = CompressionLevel.MODERATE,
        preserve_code_blocks: bool = True,
        max_list_items: int = 10,
    ):
        """Initialize the prompt compressor.

        Args:
            default_level: Default compression level
            preserve_code_blocks: Whether to preserve code blocks intact
            max_list_items: Maximum items to keep in lists
        """
        self.default_level = default_level
        self.preserve_code_blocks = preserve_code_blocks
        self.max_list_items = max_list_items

        # Compile patterns
        self._reducible_re = {re.compile(p, re.MULTILINE | re.DOTALL): r for p, r in self.REDUCIBLE_PATTERNS.items()}

        # Statistics
        self._stats = {
            "compressions": 0,
            "tokens_saved": 0,
            "avg_compression_ratio": 0.0,
        }

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        if not text:
            return 0
        return int(len(text) * self.TOKENS_PER_CHAR)

    def compress_tool_output(
        self,
        output: str,
        max_tokens: int = 500,
        tool_name: str | None = None,
        level: CompressionLevel | None = None,
    ) -> CompressionResult:
        """Compress tool output to fit within token limit.

        Args:
            output: Tool output to compress
            max_tokens: Maximum tokens for result
            tool_name: Name of the tool (for context-aware compression)
            level: Compression level (uses default if None)

        Returns:
            CompressionResult
        """
        if not output:
            return CompressionResult(
                original_tokens=0,
                compressed_tokens=0,
                compression_ratio=1.0,
                content="",
                items_removed=0,
                summary_generated=False,
            )

        level = level or self.default_level
        original_tokens = self.estimate_tokens(output)

        if original_tokens <= max_tokens:
            return CompressionResult(
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                content=output,
                items_removed=0,
                summary_generated=False,
            )

        # Apply compression based on level
        compressed = output
        items_removed = 0
        summary_generated = False

        # Light compression: remove extra whitespace
        if level in (CompressionLevel.LIGHT, CompressionLevel.MODERATE, CompressionLevel.AGGRESSIVE):
            compressed = self._apply_basic_compression(compressed)

        # Moderate compression: apply reducible patterns
        if level in (CompressionLevel.MODERATE, CompressionLevel.AGGRESSIVE):
            compressed, removed = self._apply_pattern_compression(compressed)
            items_removed += removed

        # Check if within limit
        current_tokens = self.estimate_tokens(compressed)
        if current_tokens <= max_tokens:
            return self._create_result(output, compressed, items_removed, False)

        # Aggressive compression: truncate with summary
        if level == CompressionLevel.AGGRESSIVE or current_tokens > max_tokens:
            compressed, summary_generated = self._truncate_with_summary(compressed, max_tokens, tool_name)
            items_removed += 1  # Counting the truncation

        return self._create_result(output, compressed, items_removed, summary_generated)

    def compress_history(
        self,
        messages: list[dict[str, Any]],
        keep_recent: int = 5,
        max_tokens: int = 4000,
        preserve_system: bool = True,
    ) -> list[dict[str, Any]]:
        """Compress message history to fit within token limit.

        Args:
            messages: List of message dictionaries
            keep_recent: Number of recent messages to always keep
            max_tokens: Maximum total tokens
            preserve_system: Whether to preserve system messages

        Returns:
            Compressed message list
        """
        if not messages:
            return []

        # Separate system and other messages
        system_msgs = []
        other_msgs = []

        for msg in messages:
            if preserve_system and msg.get("role") == "system":
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)

        # Calculate token budget
        system_tokens = sum(self.estimate_tokens(m.get("content", "")) for m in system_msgs)
        available_tokens = max_tokens - system_tokens

        if available_tokens <= 0:
            logger.warning("System messages exceed token budget, compressing system prompt")
            # Compress system messages
            for msg in system_msgs:
                content = msg.get("content", "")
                result = self.compress_tool_output(content, max_tokens // 2)
                msg["content"] = result.content
            system_tokens = sum(self.estimate_tokens(m.get("content", "")) for m in system_msgs)
            available_tokens = max_tokens - system_tokens

        # Always keep recent messages
        recent = other_msgs[-keep_recent:] if len(other_msgs) > keep_recent else other_msgs
        older = other_msgs[:-keep_recent] if len(other_msgs) > keep_recent else []

        # Check if recent messages fit
        recent_tokens = sum(self.estimate_tokens(m.get("content", "")) for m in recent)

        if recent_tokens > available_tokens:
            # Need to compress recent messages
            for msg in recent:
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    result = self.compress_tool_output(content, available_tokens // keep_recent)
                    msg["content"] = result.content

        # Add older messages if space permits
        remaining_tokens = available_tokens - recent_tokens
        kept_older = []

        for msg in reversed(older):  # Process from most recent
            msg_tokens = self.estimate_tokens(msg.get("content", ""))
            if msg_tokens <= remaining_tokens:
                kept_older.insert(0, msg)
                remaining_tokens -= msg_tokens
            else:
                # Try compressing
                content = msg.get("content", "")
                if self._is_important(content):
                    result = self.compress_tool_output(content, remaining_tokens)
                    if result.compressed_tokens < remaining_tokens:
                        msg["content"] = result.content
                        kept_older.insert(0, msg)
                        remaining_tokens -= result.compressed_tokens

        # Combine: system + kept_older + recent
        return system_msgs + kept_older + recent

    def compress_context(
        self,
        context: str,
        max_tokens: int = 2000,
        preserve_sections: list[str] | None = None,
    ) -> str:
        """Compress execution context.

        Args:
            context: Context string to compress
            max_tokens: Maximum tokens
            preserve_sections: Section headers to preserve

        Returns:
            Compressed context
        """
        if not context:
            return ""

        current_tokens = self.estimate_tokens(context)
        if current_tokens <= max_tokens:
            return context

        # Split into sections
        sections = re.split(r"\n(?=##?\s)", context)

        # Categorize sections by importance
        preserved = []
        compressible = []

        for section in sections:
            header_match = re.match(r"^(##?\s*)(.+)", section)
            header = header_match.group(2).lower() if header_match else ""

            if (preserve_sections and any(p in header for p in preserve_sections)) or self._is_important(section):
                preserved.append(section)
            else:
                compressible.append(section)

        # Start with preserved sections
        result = "\n".join(preserved)
        remaining_tokens = max_tokens - self.estimate_tokens(result)

        # Add compressible sections if space
        for section in compressible:
            section_tokens = self.estimate_tokens(section)
            if section_tokens <= remaining_tokens:
                result += "\n" + section
                remaining_tokens -= section_tokens
            else:
                # Summarize and add if fits
                summary = self._summarize_section(section, remaining_tokens)
                if summary:
                    result += "\n" + summary
                    remaining_tokens -= self.estimate_tokens(summary)

        return result.strip()

    def _apply_basic_compression(self, text: str) -> str:
        """Apply basic compression (whitespace removal)."""
        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Remove excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove trailing whitespace
        text = "\n".join(line.rstrip() for line in text.split("\n"))

        # Remove leading/trailing whitespace
        return text.strip()

    def _apply_pattern_compression(self, text: str) -> tuple[str, int]:
        """Apply pattern-based compression."""
        items_removed = 0

        for pattern, replacement in self._reducible_re.items():
            if callable(replacement):
                matches = pattern.findall(text)
                items_removed += len(matches)
                text = pattern.sub(replacement, text)
            else:
                count = len(pattern.findall(text))
                items_removed += count
                text = pattern.sub(replacement, text)

        return text, items_removed

    def _truncate_with_summary(
        self,
        text: str,
        max_tokens: int,
        tool_name: str | None,
    ) -> tuple[str, bool]:
        """Truncate text with a summary header."""
        max_chars = int(max_tokens / self.TOKENS_PER_CHAR)

        # Reserve space for summary header
        header_space = 100
        content_space = max_chars - header_space

        if content_space <= 0:
            return f"[Output truncated - {len(text)} chars]", True

        # Extract key parts
        lines = text.split("\n")

        # Keep first few lines (often contain important info)
        first_lines = lines[:5]
        first_content = "\n".join(first_lines)

        # Keep last few lines (often contain results)
        last_lines = lines[-3:] if len(lines) > 8 else []
        last_content = "\n".join(last_lines)

        # Build summary
        total_lines = len(lines)
        omitted = total_lines - len(first_lines) - len(last_lines)

        if len(first_content) + len(last_content) > content_space:
            # Even more aggressive truncation
            truncated = text[:content_space]
            return f"{truncated}\n\n[...{len(text) - content_space} chars omitted]", True

        if omitted > 0:
            return f"{first_content}\n\n[...{omitted} lines omitted...]\n\n{last_content}", True
        return text[:max_chars], True

    def _is_important(self, text: str) -> bool:
        """Check if text contains important markers."""
        text_lower = text.lower()
        return any(marker in text_lower for marker in self.IMPORTANT_MARKERS)

    def _summarize_section(self, section: str, max_tokens: int) -> str | None:
        """Generate a brief summary of a section."""
        max_chars = int(max_tokens / self.TOKENS_PER_CHAR)

        # Extract header if present
        header_match = re.match(r"^(##?\s*.+)\n", section)
        header = header_match.group(1) if header_match else ""

        # Get first sentence or line
        content = section[len(header) :].strip() if header else section
        first_line = content.split("\n")[0][:100]

        summary = f"{header}\n{first_line}..." if header else f"{first_line}..."

        if len(summary) <= max_chars:
            return summary
        return None

    def _create_result(
        self,
        original: str,
        compressed: str,
        items_removed: int,
        summary_generated: bool,
    ) -> CompressionResult:
        """Create a CompressionResult."""
        original_tokens = self.estimate_tokens(original)
        compressed_tokens = self.estimate_tokens(compressed)
        ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0

        # Update stats
        self._stats["compressions"] += 1
        self._stats["tokens_saved"] += original_tokens - compressed_tokens

        # Update rolling average
        n = self._stats["compressions"]
        self._stats["avg_compression_ratio"] = (self._stats["avg_compression_ratio"] * (n - 1) + ratio) / n

        return CompressionResult(
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=ratio,
            content=compressed,
            items_removed=items_removed,
            summary_generated=summary_generated,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get compression statistics."""
        return {
            **self._stats,
            "avg_ratio_pct": f"{self._stats['avg_compression_ratio']:.1%}",
        }


def _summarize_traceback(traceback: str) -> str:
    """Summarize a traceback to first and last frames."""
    lines = traceback.strip().split("\n")
    if len(lines) <= 6:
        return traceback

    # Keep header, first frame, and last frame
    header = lines[0]
    first_frame = "\n".join(lines[1:3])
    last_frame = "\n".join(lines[-2:])

    return f"{header}\n{first_frame}\n  [...{len(lines) - 5} frames...]\n{last_frame}"


# Singleton instance
_compressor: PromptCompressor | None = None


def get_prompt_compressor() -> PromptCompressor:
    """Get the global prompt compressor instance."""
    global _compressor
    if _compressor is None:
        _compressor = PromptCompressor()
    return _compressor


def compress_for_context(
    text: str,
    max_tokens: int = 1000,
    level: CompressionLevel = CompressionLevel.MODERATE,
) -> str:
    """Convenience function to compress text for context injection.

    Args:
        text: Text to compress
        max_tokens: Maximum tokens
        level: Compression level

    Returns:
        Compressed text
    """
    result = get_prompt_compressor().compress_tool_output(text, max_tokens, level=level)
    return result.content
