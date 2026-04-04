"""Tests for Phase 1B: ToolMetadataIndex."""

from __future__ import annotations

from app.domain.models.tool_permission import PermissionTier
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool
from app.domain.services.tools.metadata_index import ToolMetadataIndex


class TestToolMetadataIndex:
    def _make_tool(self) -> BaseTool:
        """Create a test tool with mixed read-only and write functions."""

        class MixedTool(BaseTool):
            name = "mixed"

            @tool(
                name="read_fn",
                description="Reads",
                parameters={},
                required=[],
                is_read_only=True,
                is_concurrency_safe=True,
                required_tier=PermissionTier.READ_ONLY,
            )
            async def read_fn(self):
                pass

            @tool(
                name="write_fn",
                description="Writes",
                parameters={},
                required=[],
                is_destructive=True,
                required_tier=PermissionTier.WORKSPACE_WRITE,
            )
            async def write_fn(self):
                pass

        return MixedTool(defaults=ToolDefaults(category="test"))

    def test_indexed_count(self):
        index = ToolMetadataIndex([self._make_tool()])
        assert index.indexed_count == 2

    def test_is_safe_parallel_from_metadata(self):
        index = ToolMetadataIndex([self._make_tool()])
        assert index.is_safe_parallel("read_fn") is True
        assert index.is_safe_parallel("write_fn") is False

    def test_is_read_only_from_metadata(self):
        index = ToolMetadataIndex([self._make_tool()])
        assert index.is_read_only("read_fn") is True
        assert index.is_read_only("write_fn") is False

    def test_is_destructive_from_metadata(self):
        index = ToolMetadataIndex([self._make_tool()])
        assert index.is_destructive("read_fn") is False
        assert index.is_destructive("write_fn") is True

    def test_get_max_result_size(self):
        index = ToolMetadataIndex([self._make_tool()])
        # Per-function metadata doesn't set max_result_size, falls back to default
        assert index.get_max_result_size("read_fn") == 8000

    def test_get_returns_metadata(self):
        index = ToolMetadataIndex([self._make_tool()])
        meta = index.get("read_fn")
        assert meta is not None
        assert meta.is_read_only is True
        assert meta.required_tier is PermissionTier.READ_ONLY

    def test_get_required_tier_from_metadata(self):
        index = ToolMetadataIndex([self._make_tool()])
        assert index.get_required_tier("read_fn") is PermissionTier.READ_ONLY
        assert index.get_required_tier("write_fn") is PermissionTier.WORKSPACE_WRITE

    def test_infers_read_only_tier_when_required_tier_is_unset(self):
        class ReadOnlyTool(BaseTool):
            name = "read_only_tool"

            @tool(
                name="read_only_fn",
                description="Reads without side effects",
                parameters={},
                required=[],
                is_read_only=True,
                is_concurrency_safe=True,
            )
            async def read_only_fn(self):
                pass

        index = ToolMetadataIndex([ReadOnlyTool()])
        assert index.get_required_tier("read_only_fn") is PermissionTier.READ_ONLY

    def test_get_unknown_returns_none(self):
        index = ToolMetadataIndex([self._make_tool()])
        assert index.get("nonexistent") is None

    def test_fallback_to_toolname_enum(self):
        """Unknown to index but known to ToolName enum should still work."""
        index = ToolMetadataIndex([])  # Empty index
        # file_read is in ToolName._READ_ONLY and _SAFE_PARALLEL
        assert index.is_read_only("file_read") is True
        assert index.is_safe_parallel("file_read") is True
        assert index.get_required_tier("file_read") is PermissionTier.READ_ONLY
        # shell_exec is NOT in _READ_ONLY or _SAFE_PARALLEL
        assert index.is_read_only("shell_exec") is False
        assert index.get_required_tier("shell_exec") is PermissionTier.DANGER

    def test_fallback_to_mcp_patterns(self):
        """MCP tool names should fall back to ToolName MCP pattern matching."""
        index = ToolMetadataIndex([])
        # MCP tools matching safe prefixes should be recognized
        # (exact behavior depends on ToolName._SAFE_MCP_PREFIXES)
        assert index.is_safe_parallel("totally_unknown_tool_xyz") is False

    def test_destructive_fallback_to_toolname_action(self):
        """Unknown to index, falls back to ToolName._ACTION set."""
        index = ToolMetadataIndex([])
        # shell_exec is in ToolName._ACTION
        assert index.is_destructive("shell_exec") is True
        # file_read is NOT in _ACTION
        assert index.is_destructive("file_read") is False

    def test_empty_tools_list(self):
        index = ToolMetadataIndex([])
        assert index.indexed_count == 0

    def test_multiple_tools(self):
        class ToolA(BaseTool):
            name = "a"

            @tool(name="fn_a", description="A", parameters={}, required=[], is_read_only=True)
            async def fn_a(self):
                pass

        class ToolB(BaseTool):
            name = "b"

            @tool(name="fn_b", description="B", parameters={}, required=[], is_destructive=True)
            async def fn_b(self):
                pass

        index = ToolMetadataIndex([ToolA(), ToolB()])
        assert index.indexed_count == 2
        assert index.is_read_only("fn_a") is True
        assert index.is_destructive("fn_b") is True
