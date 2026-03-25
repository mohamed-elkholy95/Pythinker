"""Tests for dynamic_toolset — ToolCategory, ToolInfo, ToolsetConfig, DynamicToolsetManager.

Covers:
  - ToolCategory enum members
  - ToolInfo dataclass defaults
  - ToolsetConfig defaults and always_include set
  - DynamicToolsetManager: register_tools, detect_task_type, _detect_category,
    _extract_keywords, get_tools_for_task, _keyword_search, search_tools,
    record_tool_usage, get_stats
  - TASK_PATTERNS / TASK_TO_CATEGORIES constants
  - Compiled regex pattern helpers
"""

from __future__ import annotations

from app.domain.services.tools.dynamic_toolset import (
    TASK_PATTERNS,
    TASK_TO_CATEGORIES,
    TOOL_CATEGORY_PATTERNS,
    DynamicToolsetManager,
    ToolCategory,
    ToolInfo,
    ToolsetConfig,
    _get_compiled_category_patterns,
    _get_compiled_task_patterns,
)


def _tool_schema(name: str, description: str = "A tool") -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {}}}


# ---------------------------------------------------------------------------
# ToolCategory enum
# ---------------------------------------------------------------------------


class TestToolCategory:
    """ToolCategory enum values."""

    def test_all_members(self) -> None:
        expected = {"file", "browser", "search", "shell", "message", "mcp", "code", "plan", "automation", "system"}
        assert {c.value for c in ToolCategory} == expected


# ---------------------------------------------------------------------------
# ToolInfo dataclass
# ---------------------------------------------------------------------------


class TestToolInfo:
    """ToolInfo defaults."""

    def test_defaults(self) -> None:
        ti = ToolInfo(name="search", description="search the web", category=ToolCategory.SEARCH, schema={})
        assert ti.usage_count == 0
        assert ti.last_used is None
        assert ti.average_duration_ms == 0
        assert ti.keywords == set()


# ---------------------------------------------------------------------------
# ToolsetConfig
# ---------------------------------------------------------------------------


class TestToolsetConfig:
    """ToolsetConfig defaults."""

    def test_defaults(self) -> None:
        cfg = ToolsetConfig()
        assert cfg.enabled is True
        assert cfg.max_tools_per_request == 20
        assert len(cfg.always_include) >= 1

    def test_custom_max_tools(self) -> None:
        cfg = ToolsetConfig(max_tools_per_request=5)
        assert cfg.max_tools_per_request == 5


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """TASK_PATTERNS and TASK_TO_CATEGORIES constants."""

    def test_task_patterns_keys(self) -> None:
        expected = {
            "research",
            "coding",
            "file_management",
            "web_browsing",
            "analysis",
            "communication",
            "automation",
            "delegation",
            "skills",
        }
        assert set(TASK_PATTERNS.keys()) == expected

    def test_task_to_categories_keys(self) -> None:
        for key in TASK_TO_CATEGORIES:
            assert all(isinstance(c, ToolCategory) for c in TASK_TO_CATEGORIES[key])

    def test_tool_category_patterns_keys(self) -> None:
        for cat in TOOL_CATEGORY_PATTERNS:
            assert isinstance(cat, ToolCategory)


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------


class TestCompiledPatterns:
    """Pre-compiled regex pattern helpers."""

    def test_compiled_task_patterns(self) -> None:
        patterns = _get_compiled_task_patterns()
        assert "research" in patterns
        assert len(patterns["research"]) > 0

    def test_compiled_category_patterns(self) -> None:
        patterns = _get_compiled_category_patterns()
        assert ToolCategory.FILE in patterns


# ---------------------------------------------------------------------------
# DynamicToolsetManager — register and detect
# ---------------------------------------------------------------------------


class TestDynamicToolsetManagerRegister:
    """DynamicToolsetManager.register_tools."""

    def test_register_tools(self) -> None:
        mgr = DynamicToolsetManager()
        tools = [
            _tool_schema("file_read", "Read a file from disk"),
            _tool_schema("browser_navigate", "Navigate to a URL"),
            _tool_schema("search_web", "Search the web"),
        ]
        mgr.register_tools(tools)
        assert len(mgr._tools) == 3
        assert "file_read" in mgr._tools
        assert "browser_navigate" in mgr._tools

    def test_register_empty_name_skipped(self) -> None:
        mgr = DynamicToolsetManager()
        mgr.register_tools([{"type": "function", "function": {"name": "", "description": "x"}}])
        assert len(mgr._tools) == 0

    def test_detect_category_file(self) -> None:
        mgr = DynamicToolsetManager()
        assert mgr._detect_category("file_read") == ToolCategory.FILE

    def test_detect_category_browser(self) -> None:
        mgr = DynamicToolsetManager()
        assert mgr._detect_category("browser_navigate") == ToolCategory.BROWSER

    def test_detect_category_search(self) -> None:
        mgr = DynamicToolsetManager()
        assert mgr._detect_category("search_web") == ToolCategory.SEARCH

    def test_detect_category_shell(self) -> None:
        mgr = DynamicToolsetManager()
        assert mgr._detect_category("shell_execute") == ToolCategory.SHELL

    def test_detect_category_mcp(self) -> None:
        mgr = DynamicToolsetManager()
        assert mgr._detect_category("mcp_docker_run") == ToolCategory.MCP

    def test_detect_category_unknown(self) -> None:
        mgr = DynamicToolsetManager()
        assert mgr._detect_category("zzzz_unknown") == ToolCategory.SYSTEM

    def test_extract_keywords(self) -> None:
        mgr = DynamicToolsetManager()
        kws = mgr._extract_keywords("file_read", "Read a file from the filesystem")
        assert "file" in kws
        assert "read" in kws
        assert "filesystem" in kws


# ---------------------------------------------------------------------------
# DynamicToolsetManager — detect_task_type
# ---------------------------------------------------------------------------


class TestDetectTaskType:
    """DynamicToolsetManager.detect_task_type."""

    def setup_method(self) -> None:
        self.mgr = DynamicToolsetManager()

    def test_research_task(self) -> None:
        types = self.mgr.detect_task_type("Research the best Python web frameworks")
        assert "research" in types

    def test_coding_task(self) -> None:
        types = self.mgr.detect_task_type("Implement a REST API class")
        assert "coding" in types

    def test_file_management_task(self) -> None:
        types = self.mgr.detect_task_type("Read the file and create a directory")
        assert "file_management" in types

    def test_web_browsing_task(self) -> None:
        types = self.mgr.detect_task_type("Browse this website and take a screenshot")
        assert "web_browsing" in types

    def test_analysis_task(self) -> None:
        types = self.mgr.detect_task_type("Analyze the data and create a chart")
        assert "analysis" in types

    def test_communication_task(self) -> None:
        types = self.mgr.detect_task_type("Ask the user for clarification")
        assert "communication" in types

    def test_automation_task(self) -> None:
        types = self.mgr.detect_task_type("Schedule a daily cron job")
        assert "automation" in types

    def test_delegation_task(self) -> None:
        types = self.mgr.detect_task_type("Spawn a background subtask")
        assert "delegation" in types

    def test_general_fallback(self) -> None:
        types = self.mgr.detect_task_type("Do something unrecognizable xyz")
        assert "general" in types

    def test_multi_type(self) -> None:
        types = self.mgr.detect_task_type("Research and implement a solution, then browse results")
        assert "research" in types
        assert "coding" in types


# ---------------------------------------------------------------------------
# DynamicToolsetManager — get_tools_for_task
# ---------------------------------------------------------------------------


class TestGetToolsForTask:
    """DynamicToolsetManager.get_tools_for_task."""

    def _setup_mgr(self) -> DynamicToolsetManager:
        mgr = DynamicToolsetManager(ToolsetConfig(max_tools_per_request=10))
        tools = [
            _tool_schema("file_read", "Read a file from disk"),
            _tool_schema("file_write", "Write a file to disk"),
            _tool_schema("browser_navigate", "Navigate to a URL"),
            _tool_schema("search_web", "Search the web for information"),
            _tool_schema("shell_execute", "Execute a shell command"),
            _tool_schema("message_ask_user", "Ask the user a question"),
            _tool_schema("mcp_tool", "An MCP tool"),
            _tool_schema("code_execute", "Execute code"),
        ]
        mgr.register_tools(tools)
        return mgr

    def test_research_gets_search_tools(self) -> None:
        mgr = self._setup_mgr()
        tools = mgr.get_tools_for_task("Research Python web frameworks")
        names = {t["function"]["name"] for t in tools}
        assert "search_web" in names

    def test_coding_gets_file_tools(self) -> None:
        mgr = self._setup_mgr()
        tools = mgr.get_tools_for_task("Implement a Python function")
        names = {t["function"]["name"] for t in tools}
        assert "file_read" in names or "file_write" in names

    def test_disabled_returns_all(self) -> None:
        mgr = self._setup_mgr()
        mgr.config.enabled = False
        tools = mgr.get_tools_for_task("anything")
        assert len(tools) == len(mgr._tools)

    def test_includes_mcp_by_default(self) -> None:
        mgr = self._setup_mgr()
        tools = mgr.get_tools_for_task("Do something general")
        names = {t["function"]["name"] for t in tools}
        assert "mcp_tool" in names

    def test_excludes_mcp_when_disabled(self) -> None:
        mgr = self._setup_mgr()
        tools = mgr.get_tools_for_task("Do something general", include_mcp=False)
        names = {t["function"]["name"] for t in tools}
        assert "mcp_tool" not in names

    def test_additional_tools(self) -> None:
        mgr = self._setup_mgr()
        tools = mgr.get_tools_for_task("Do something", additional_tools=["shell_execute"])
        names = {t["function"]["name"] for t in tools}
        assert "shell_execute" in names


# ---------------------------------------------------------------------------
# DynamicToolsetManager — search_tools
# ---------------------------------------------------------------------------


class TestSearchTools:
    """DynamicToolsetManager.search_tools."""

    def _setup_mgr(self) -> DynamicToolsetManager:
        mgr = DynamicToolsetManager()
        tools = [
            _tool_schema("file_read", "Read a file from disk"),
            _tool_schema("file_write", "Write content to a file"),
            _tool_schema("browser_navigate", "Navigate to a URL in the browser"),
            _tool_schema("search_web", "Search the web for information"),
        ]
        mgr.register_tools(tools)
        return mgr

    def test_search_by_keyword(self) -> None:
        mgr = self._setup_mgr()
        results = mgr.search_tools("file")
        assert len(results) >= 1
        names = [r[0] for r in results]
        assert "file_read" in names or "file_write" in names

    def test_search_limit(self) -> None:
        mgr = self._setup_mgr()
        results = mgr.search_tools("file", limit=1)
        assert len(results) <= 1

    def test_search_by_category(self) -> None:
        mgr = self._setup_mgr()
        results = mgr.search_tools("navigate", category=ToolCategory.BROWSER)
        assert all(mgr._tools[r[0]].category == ToolCategory.BROWSER for r in results if r[0] in mgr._tools)

    def test_search_returns_scores(self) -> None:
        mgr = self._setup_mgr()
        results = mgr.search_tools("file read")
        if results:
            assert results[0][1] > 0  # Score should be positive


# ---------------------------------------------------------------------------
# DynamicToolsetManager — record_tool_usage
# ---------------------------------------------------------------------------


class TestRecordToolUsage:
    """DynamicToolsetManager.record_tool_usage."""

    def test_record_usage(self) -> None:
        mgr = DynamicToolsetManager()
        mgr.register_tools([_tool_schema("file_read", "Read")])
        mgr.record_tool_usage("file_read", success=True, duration_ms=100)
        info = mgr._tools["file_read"]
        assert info.usage_count == 1
        assert info.last_used is not None
        assert info.average_duration_ms == 100

    def test_record_usage_moving_average(self) -> None:
        mgr = DynamicToolsetManager()
        mgr.register_tools([_tool_schema("file_read", "Read")])
        mgr.record_tool_usage("file_read", duration_ms=100)
        mgr.record_tool_usage("file_read", duration_ms=200)
        info = mgr._tools["file_read"]
        assert info.usage_count == 2
        # First: 100, second: 100*0.8 + 200*0.2 = 120
        assert abs(info.average_duration_ms - 120) < 1

    def test_record_unknown_tool(self) -> None:
        mgr = DynamicToolsetManager()
        mgr.record_tool_usage("nonexistent")  # Should not raise


# ---------------------------------------------------------------------------
# DynamicToolsetManager — get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    """DynamicToolsetManager.get_stats."""

    def test_stats(self) -> None:
        mgr = DynamicToolsetManager()
        mgr.register_tools(
            [
                _tool_schema("file_read", "Read"),
                _tool_schema("browser_nav", "Navigate"),
            ]
        )
        stats = mgr.get_stats()
        assert stats["total_tools"] == 2
        assert "categories" in stats
