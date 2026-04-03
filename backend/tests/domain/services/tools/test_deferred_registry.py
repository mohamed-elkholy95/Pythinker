"""Tests for DeferredToolRegistry and ToolSearchTool."""

from __future__ import annotations

import pytest

from app.domain.services.tools.base import BaseTool, ToolDefaults, tool
from app.domain.services.tools.deferred_registry import DeferredToolRegistry
from app.domain.services.tools.tool_search import ToolSearchTool

# ── DeferredToolRegistry ────────────────────────────────────────────────────


class TestDeferredToolRegistry:
    def _registry(self) -> DeferredToolRegistry:
        r = DeferredToolRegistry()
        r.register("canvas_draw", "Draw on canvas", "canvas", lambda: object())
        r.register("slides_add", "Add a slide", "slides", lambda: object())
        return r

    def test_register_increments_generation(self):
        r = DeferredToolRegistry()
        g0 = r.generation
        r.register("tool_a", "desc", "cat", lambda: None)
        assert r.generation == g0 + 1

    def test_deregister_increments_generation(self):
        r = DeferredToolRegistry()
        r.register("tool_a", "desc", "cat", lambda: None)
        g1 = r.generation
        r.deregister("tool_a")
        assert r.generation == g1 + 1

    def test_deregister_nonexistent_returns_false(self):
        r = DeferredToolRegistry()
        assert r.deregister("nonexistent") is False

    def test_contains(self):
        r = self._registry()
        assert "canvas_draw" in r
        assert "unknown" not in r

    def test_len(self):
        r = self._registry()
        assert len(r) == 2

    def test_instantiate_calls_factory(self):
        sentinel = object()
        r = DeferredToolRegistry()
        r.register("my_tool", "desc", "cat", lambda: sentinel)
        assert r.instantiate("my_tool") is sentinel

    def test_instantiate_unknown_returns_none(self):
        r = DeferredToolRegistry()
        assert r.instantiate("nonexistent") is None

    def test_search_by_name(self):
        r = self._registry()
        results = r.search("canvas")
        assert len(results) == 1
        assert results[0].name == "canvas_draw"

    def test_search_by_description(self):
        r = self._registry()
        results = r.search("slide")
        assert any(e.name == "slides_add" for e in results)

    def test_search_case_insensitive(self):
        r = self._registry()
        results = r.search("CANVAS")
        assert len(results) == 1

    def test_search_no_match(self):
        r = self._registry()
        assert r.search("totally_unknown_xyz") == []

    def test_all_entries(self):
        r = self._registry()
        names = {e.name for e in r.all_entries()}
        assert names == {"canvas_draw", "slides_add"}

    def test_replace_existing_entry(self):
        r = DeferredToolRegistry()
        r.register("tool_a", "old desc", "cat", lambda: None)
        r.register("tool_a", "new desc", "cat", lambda: None)
        assert len(r) == 1
        assert r.all_entries()[0].description == "new desc"


# ── ToolSearchTool ──────────────────────────────────────────────────────────


def _make_active_tool() -> BaseTool:
    class FileTool(BaseTool):
        name = "file"

        @tool(
            name="file_read",
            description="Read a file from the filesystem",
            parameters={},
            required=[],
            is_read_only=True,
            is_concurrency_safe=True,
        )
        async def file_read(self):
            pass

        @tool(
            name="file_write",
            description="Write content to a file",
            parameters={},
            required=[],
            is_destructive=True,
        )
        async def file_write(self):
            pass

    return FileTool(defaults=ToolDefaults(category="file"))


class TestToolSearchTool:
    @pytest.mark.asyncio
    async def test_search_finds_active_tool(self):
        search = ToolSearchTool(active_tools=[_make_active_tool()])
        result = await search.tool_search(query="file")
        assert result.success is True
        data = result.data or {}
        names = [r["name"] for r in data.get("results", [])]
        assert "file_read" in names
        assert "file_write" in names

    @pytest.mark.asyncio
    async def test_search_finds_deferred_tool(self):
        registry = DeferredToolRegistry()
        registry.register("canvas_draw", "Draw shapes on canvas", "canvas", lambda: None)
        search = ToolSearchTool(deferred_registry=registry)
        result = await search.tool_search(query="canvas")
        assert result.success is True
        data = result.data or {}
        names = [r["name"] for r in data.get("results", [])]
        assert "canvas_draw" in names

    @pytest.mark.asyncio
    async def test_search_no_match_returns_empty(self):
        search = ToolSearchTool()
        result = await search.tool_search(query="totally_nonexistent_xyz_abc")
        assert result.success is True
        assert result.data["total"] == 0

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_error(self):
        search = ToolSearchTool()
        result = await search.tool_search(query="")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_category_filter(self):
        registry = DeferredToolRegistry()
        registry.register("canvas_draw", "Draw on canvas", "canvas", lambda: None)
        registry.register("file_read", "Read file", "file", lambda: None)
        search = ToolSearchTool(deferred_registry=registry)

        result = await search.tool_search(query="", category="canvas")
        # empty query doesn't match (returns error)
        assert result.success is False

        # non-empty query with category filter
        result2 = await search.tool_search(query="read", category="file")
        assert result2.success is True
        names = [r["name"] for r in result2.data["results"]]
        assert "canvas_draw" not in names
        assert "file_read" in names

    @pytest.mark.asyncio
    async def test_limit_caps_results(self):
        registry = DeferredToolRegistry()
        for i in range(30):
            registry.register(f"tool_{i}", f"Tool number {i}", "test", lambda: None)
        search = ToolSearchTool(deferred_registry=registry)
        result = await search.tool_search(query="tool", limit=5)
        assert result.success is True
        assert len(result.data["results"]) <= 5

    @pytest.mark.asyncio
    async def test_limit_capped_at_50(self):
        registry = DeferredToolRegistry()
        for i in range(60):
            registry.register(f"tool_{i}", f"Tool {i}", "test", lambda: None)
        search = ToolSearchTool(deferred_registry=registry)
        result = await search.tool_search(query="tool", limit=100)
        assert result.success is True
        assert len(result.data["results"]) <= 50

    @pytest.mark.asyncio
    async def test_cache_invalidated_on_registration(self):
        registry = DeferredToolRegistry()
        search = ToolSearchTool(deferred_registry=registry)

        # First search: empty registry
        r1 = await search.tool_search(query="new_tool")
        assert r1.data["total"] == 0

        # Register a new tool — cache should be invalidated
        registry.register("new_tool", "A brand new tool", "test", lambda: None)

        r2 = await search.tool_search(query="new_tool")
        assert r2.data["total"] == 1

    @pytest.mark.asyncio
    async def test_cache_invalidated_on_deregistration(self):
        registry = DeferredToolRegistry()
        registry.register("temp_tool", "Temporary tool", "test", lambda: None)
        search = ToolSearchTool(deferred_registry=registry)

        r1 = await search.tool_search(query="temp")
        assert r1.data["total"] == 1

        registry.deregister("temp_tool")

        r2 = await search.tool_search(query="temp")
        assert r2.data["total"] == 0

    @pytest.mark.asyncio
    async def test_update_active_tools_invalidates_cache(self):
        search = ToolSearchTool(active_tools=[_make_active_tool()])
        r1 = await search.tool_search(query="file")
        assert r1.data["total"] > 0

        # Replace with empty toolset
        search.update_active_tools([])
        r2 = await search.tool_search(query="file")
        assert r2.data["total"] == 0

    def test_tool_defaults_read_only(self):
        search = ToolSearchTool()
        assert search._defaults.is_read_only is True
        assert search._defaults.is_concurrency_safe is True
