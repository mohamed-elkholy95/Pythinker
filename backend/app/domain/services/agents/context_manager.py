"""Context retention system for execution continuity across steps.

Solves the problem where ExecutionAgent loses context between steps,
requiring re-reading of files created in previous steps.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class FileContext:
    """Context for a file that was created or read"""
    path: str
    operation: str  # "created", "read", "modified"
    timestamp: datetime
    size_bytes: int | None = None
    content_summary: str | None = None  # Brief description
    is_deliverable: bool = False


@dataclass
class ToolContext:
    """Context from tool execution"""
    tool_name: str
    timestamp: datetime
    summary: str  # Brief result summary
    key_findings: list[str] = field(default_factory=list)
    urls_visited: list[str] = field(default_factory=list)
    files_affected: list[str] = field(default_factory=list)


@dataclass
class WorkingContext:
    """Accumulated context during execution"""
    files: dict[str, FileContext] = field(default_factory=dict)  # path -> context
    tools: list[ToolContext] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)  # Important discoveries
    deliverables: list[str] = field(default_factory=list)  # Completed deliverables
    total_tokens: int = 0  # Estimated context size


class ContextManager:
    """Manages working context across execution steps.

    Features:
    - Tracks files created/read to avoid re-reading
    - Stores key findings from research/browsing
    - Generates token-aware context summaries
    - Prioritizes recent and important context
    """

    def __init__(self, max_context_tokens: int = 8000):
        self._context = WorkingContext()
        self._max_tokens = max_context_tokens
        self._token_per_char = 0.25  # Conservative estimate

    def track_file_operation(
        self,
        path: str,
        operation: str,
        size_bytes: int | None = None,
        content_summary: str | None = None,
        is_deliverable: bool = False,
    ):
        """Track file creation/read/modification"""
        self._context.files[path] = FileContext(
            path=path,
            operation=operation,
            timestamp=datetime.now(UTC),
            size_bytes=size_bytes,
            content_summary=content_summary,
            is_deliverable=is_deliverable,
        )
        logger.debug(f"Tracked file {operation}: {path}")

    def track_tool_execution(
        self,
        tool_name: str,
        summary: str,
        key_findings: list[str] = None,
        urls_visited: list[str] = None,
        files_affected: list[str] = None,
    ):
        """Track tool execution results"""
        self._context.tools.append(ToolContext(
            tool_name=tool_name,
            timestamp=datetime.now(UTC),
            summary=summary,
            key_findings=key_findings or [],
            urls_visited=urls_visited or [],
            files_affected=files_affected or [],
        ))
        logger.debug(f"Tracked tool execution: {tool_name}")

    def add_key_fact(self, fact: str):
        """Add important discovery/fact"""
        if fact not in self._context.key_facts:
            self._context.key_facts.append(fact)

    def mark_deliverable_complete(self, deliverable_path: str):
        """Mark a deliverable as completed"""
        if deliverable_path not in self._context.deliverables:
            self._context.deliverables.append(deliverable_path)
            # Also mark in files context
            if deliverable_path in self._context.files:
                self._context.files[deliverable_path].is_deliverable = True

    def get_context_summary(self, max_tokens: int | None = None) -> str:
        """Generate token-aware context summary for prompt injection.

        Prioritizes:
        1. Deliverables (most important)
        2. Recent tool executions
        3. Key facts
        4. File operations
        """
        max_tokens = max_tokens or self._max_tokens

        sections = []

        # 1. Deliverables (highest priority)
        if self._context.deliverables:
            sections.append("## Completed Deliverables")
            for path in self._context.deliverables:
                sections.append(f"- {path}")
            sections.append("")

        # 2. Files context
        if self._context.files:
            sections.append("## Working Files")
            # Prioritize deliverables and recently modified
            sorted_files = sorted(
                self._context.files.values(),
                key=lambda f: (f.is_deliverable, f.timestamp),
                reverse=True
            )
            for file_ctx in sorted_files[:20]:  # Limit to 20 most important
                summary = file_ctx.content_summary or "No summary"
                sections.append(f"- {file_ctx.path} ({file_ctx.operation}): {summary}")
            sections.append("")

        # 3. Key facts
        if self._context.key_facts:
            sections.append("## Key Findings")
            for fact in self._context.key_facts[-10:]:  # Last 10 facts
                sections.append(f"- {fact}")
            sections.append("")

        # 4. Recent tool executions
        if self._context.tools:
            sections.append("## Recent Actions")
            for tool_ctx in self._context.tools[-5:]:  # Last 5 tools
                sections.append(f"- {tool_ctx.tool_name}: {tool_ctx.summary}")
            sections.append("")

        full_summary = "\n".join(sections)

        # Token limit enforcement (truncate if needed)
        estimated_tokens = int(len(full_summary) * self._token_per_char)
        if estimated_tokens > max_tokens:
            # Truncate proportionally
            char_limit = int(max_tokens / self._token_per_char)
            full_summary = full_summary[:char_limit] + "\n... (truncated)"

        return full_summary

    def get_files_created(self) -> list[str]:
        """Get list of files created in this session"""
        return [
            path for path, ctx in self._context.files.items()
            if ctx.operation == "created"
        ]

    def get_deliverables(self) -> list[str]:
        """Get list of completed deliverables"""
        return self._context.deliverables.copy()

    def clear(self):
        """Clear all context (use at task boundaries)"""
        self._context = WorkingContext()
        logger.info("Context cleared")
