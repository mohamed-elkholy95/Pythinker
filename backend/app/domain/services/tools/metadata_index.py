"""Metadata index for runtime tool classification lookups.

Built from registered BaseTool instances at startup. Provides O(1) lookups by
function name for metadata properties (is_read_only, is_concurrency_safe, etc.).

Falls back to ToolName enum for tool names not covered by any BaseTool instance
(e.g. MCP dynamic tools, legacy aliases).
"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING

from app.domain.models.tool_name import ToolName
from app.domain.services.tools.base import ToolDefaults

if TYPE_CHECKING:
    from app.domain.services.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolMetadataIndex:
    """O(1) metadata lookup by function name, built from BaseTool instances.

    Usage:
        index = ToolMetadataIndex(tool_instances)
        index.is_safe_parallel("file_read")   # True (from BaseTool metadata)
        index.is_safe_parallel("mcp__s__get")  # True (ToolName MCP fallback)
        index.is_read_only("shell_exec")       # False
    """

    def __init__(self, tools: list[BaseTool]) -> None:
        self._index: dict[str, ToolDefaults] = {}
        for tool_instance in tools:
            for _, method in inspect.getmembers(tool_instance, inspect.ismethod):
                fn_name = getattr(method, "_function_name", None)
                if fn_name is None:
                    continue
                # Per-function metadata takes priority over instance defaults
                meta = getattr(method, "_tool_metadata", tool_instance._defaults)
                self._index[fn_name] = meta

    def get(self, function_name: str) -> ToolDefaults | None:
        """Get metadata for a function name, or None if not indexed."""
        return self._index.get(function_name)

    def is_safe_parallel(self, function_name: str) -> bool:
        """Check if a tool function is safe for parallel execution.

        Priority: indexed metadata > ToolName enum > ToolName MCP patterns > False.
        """
        meta = self._index.get(function_name)
        if meta is not None:
            return meta.is_concurrency_safe

        # Fallback: ToolName enum
        try:
            return ToolName(function_name).is_safe_parallel
        except ValueError:
            pass

        # Fallback: MCP pattern matching
        return ToolName.is_safe_mcp_tool(function_name)

    def is_read_only(self, function_name: str) -> bool:
        """Check if a tool function is read-only.

        Priority: indexed metadata > ToolName enum > ToolName MCP patterns > False.
        """
        meta = self._index.get(function_name)
        if meta is not None:
            return meta.is_read_only

        # Fallback: ToolName enum
        try:
            return ToolName(function_name).is_read_only
        except ValueError:
            pass

        return ToolName.is_safe_mcp_tool(function_name)

    def is_destructive(self, function_name: str) -> bool:
        """Check if a tool function is destructive."""
        meta = self._index.get(function_name)
        if meta is not None:
            return meta.is_destructive

        # Fallback: ToolName enum action set (conservative)
        try:
            return ToolName(function_name).is_action
        except ValueError:
            return False

    def get_max_result_size(self, function_name: str) -> int:
        """Get the max result size for a function, defaulting to 8000."""
        meta = self._index.get(function_name)
        if meta is not None:
            return meta.max_result_size_chars
        return ToolDefaults().max_result_size_chars

    @property
    def indexed_count(self) -> int:
        """Number of function names in the index."""
        return len(self._index)
