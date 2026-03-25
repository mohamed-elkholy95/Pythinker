"""Tests for PromptAdapter — dynamic prompt adaptation based on execution context."""

from app.domain.services.agents.prompt_adapter import (
    ContextType,
    ExecutionContext,
    PromptAdapter,
)

# ── ExecutionContext ────────────────────────────────────────────────


class TestExecutionContext:
    def test_defaults(self):
        ctx = ExecutionContext()
        assert ctx.recent_tools == []
        assert ctx.recent_errors == []
        assert ctx.iteration_count == 0
        assert ctx.primary_context == ContextType.GENERAL

    def test_custom_values(self):
        ctx = ExecutionContext(
            recent_tools=["search"],
            iteration_count=5,
            primary_context=ContextType.BROWSER,
        )
        assert ctx.recent_tools == ["search"]
        assert ctx.iteration_count == 5


# ── Tool Tracking ──────────────────────────────────────────────────


class TestToolTracking:
    def test_tracks_tool_usage(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        assert "browser_navigate" in adapter.get_context().recent_tools

    def test_tracks_multiple_tools(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("shell_exec")
        assert len(adapter.get_context().recent_tools) == 2

    def test_bounded_at_max_recent_tools(self):
        adapter = PromptAdapter(max_recent_tools=3)
        for i in range(5):
            adapter.track_tool_use(f"tool_{i}")
        assert len(adapter.get_context().recent_tools) == 3
        assert adapter.get_context().recent_tools[0] == "tool_2"

    def test_tracks_errors(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="Command failed")
        assert len(adapter.get_context().recent_errors) == 1
        assert "shell_exec" in adapter.get_context().recent_errors[0]

    def test_errors_bounded_at_5(self):
        adapter = PromptAdapter()
        for i in range(7):
            adapter.track_tool_use("tool", success=False, error=f"error {i}")
        assert len(adapter.get_context().recent_errors) == 5

    def test_success_does_not_add_error(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("search", success=True)
        assert len(adapter.get_context().recent_errors) == 0


# ── Context Inference ──────────────────────────────────────────────


class TestContextInference:
    def test_browser_context_from_browser_tools(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("browser_click")
        adapter.track_tool_use("browser_view")
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_shell_context_from_shell_tools(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec")
        adapter.track_tool_use("shell_run")
        assert adapter.get_context().primary_context == ContextType.SHELL

    def test_file_context_from_file_tools(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_read")
        adapter.track_tool_use("file_write")
        assert adapter.get_context().primary_context == ContextType.FILE

    def test_search_context_from_search_tools(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("info_search_web")
        assert adapter.get_context().primary_context == ContextType.SEARCH

    def test_general_context_for_unknown_tools(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("unknown_tool_xyz")
        assert adapter.get_context().primary_context == ContextType.GENERAL

    def test_most_common_context_wins(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("browser_click")
        adapter.track_tool_use("shell_exec")
        # 2 browser > 1 shell
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_mcp_prefix_stripped(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("mcp_browser_navigate")
        adapter.track_tool_use("mcp_browser_click")
        # After stripping "mcp_", should match browser context
        ctx = adapter.get_context().primary_context
        assert ctx == ContextType.BROWSER

    def test_empty_tools_returns_general(self):
        adapter = PromptAdapter()
        assert adapter.get_context().primary_context == ContextType.GENERAL


# ── Iteration Tracking ─────────────────────────────────────────────


class TestIteration:
    def test_increment_iteration(self):
        adapter = PromptAdapter()
        adapter.increment_iteration()
        assert adapter.get_context().iteration_count == 1

    def test_multiple_increments(self):
        adapter = PromptAdapter()
        for _ in range(15):
            adapter.increment_iteration()
        assert adapter.get_context().iteration_count == 15

    def test_iteration_property_alias(self):
        adapter = PromptAdapter()
        adapter._iteration = 7
        assert adapter.get_context().iteration_count == 7
        assert adapter._iteration == 7


# ── Context Prompt Generation ──────────────────────────────────────


class TestGetContextPrompt:
    def test_returns_none_for_general_context_no_errors(self):
        adapter = PromptAdapter()
        assert adapter.get_context_prompt() is None

    def test_returns_browser_guidance(self):
        adapter = PromptAdapter()
        for _ in range(3):
            adapter.track_tool_use("browser_navigate")
        prompt = adapter.get_context_prompt()
        # Only returns guidance at iteration_count % 5 == 0
        # iteration_count is still 0, so 0 % 5 == 0 → should inject
        assert prompt is not None
        assert "Browser" in prompt or "scroll" in prompt.lower()

    def test_includes_error_summary(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="Permission denied")
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "Permission denied" in prompt

    def test_iteration_10_warning(self):
        adapter = PromptAdapter()
        for _ in range(10):
            adapter.increment_iteration()
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "10 iterations" in prompt

    def test_iteration_20_warning(self):
        adapter = PromptAdapter()
        for _ in range(20):
            adapter.increment_iteration()
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "20 iterations" in prompt

    def test_iteration_30_warning(self):
        adapter = PromptAdapter()
        for _ in range(30):
            adapter.increment_iteration()
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "30 iterations" in prompt


# ── Prompt Adaptation ──────────────────────────────────────────────


class TestAdaptPrompt:
    def test_returns_base_when_no_context(self):
        adapter = PromptAdapter()
        result = adapter.adapt_prompt("Do the task")
        assert result == "Do the task"

    def test_appends_context_guidance(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="Timeout")
        result = adapter.adapt_prompt("Run command")
        assert "Run command" in result
        assert "Context Guidance" in result
        assert "Timeout" in result

    def test_context_separator(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_read", success=False, error="Not found")
        result = adapter.adapt_prompt("Base")
        assert "---" in result


# ── should_inject_guidance ─────────────────────────────────────────


class TestShouldInjectGuidance:
    def test_true_when_errors(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("x", success=False, error="boom")
        assert adapter.should_inject_guidance() is True

    def test_true_at_iteration_thresholds(self):
        for threshold in [10, 20, 30]:
            adapter = PromptAdapter()
            for _ in range(threshold):
                adapter.increment_iteration()
            assert adapter.should_inject_guidance() is True

    def test_false_at_non_threshold_iterations(self):
        adapter = PromptAdapter()
        for _ in range(7):
            adapter.increment_iteration()
        assert adapter.should_inject_guidance() is False

    def test_periodic_injection_for_specialized_context(self):
        adapter = PromptAdapter()
        for _ in range(3):
            adapter.track_tool_use("browser_navigate")
        # iteration_count=0 → 0 % 5 == 0 → True
        assert adapter.should_inject_guidance() is True
        # advance to 3 → 3 % 5 != 0
        for _ in range(3):
            adapter.increment_iteration()
        assert adapter.should_inject_guidance() is False


# ── Reset ──────────────────────────────────────────────────────────


class TestReset:
    def test_reset_clears_everything(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("x", success=False, error="err")
        adapter.increment_iteration()
        adapter.reset()
        ctx = adapter.get_context()
        assert ctx.recent_tools == []
        assert ctx.recent_errors == []
        assert ctx.iteration_count == 0
        assert ctx.primary_context == ContextType.GENERAL


# ── Stats ──────────────────────────────────────────────────────────


class TestStats:
    def test_stats_structure(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("info_search_web")
        adapter.increment_iteration()
        stats = adapter.get_stats()
        assert stats["iteration_count"] == 1
        assert stats["recent_tools_count"] == 1
        assert stats["recent_errors_count"] == 0
        assert stats["primary_context"] == "search"
