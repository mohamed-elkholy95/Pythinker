"""
Tests for the prompt adapter module.
"""

import pytest
from app.domain.services.agents.prompt_adapter import (
    PromptAdapter,
    ContextType,
    ExecutionContext,
)


class TestContextType:
    """Tests for ContextType enum"""

    def test_context_types_exist(self):
        """Verify all expected context types exist"""
        expected_types = [
            "BROWSER",
            "SHELL",
            "FILE",
            "SEARCH",
            "MCP",
            "MESSAGE",
            "GENERAL",
        ]
        for ctx_type in expected_types:
            assert hasattr(ContextType, ctx_type)


class TestExecutionContext:
    """Tests for ExecutionContext dataclass"""

    def test_default_initialization(self):
        """Test default context initialization"""
        ctx = ExecutionContext()
        assert ctx.recent_tools == []
        assert ctx.recent_errors == []
        assert ctx.iteration_count == 0
        assert ctx.primary_context == ContextType.GENERAL


class TestPromptAdapter:
    """Tests for PromptAdapter class"""

    def test_initialization(self):
        """Test adapter initialization"""
        adapter = PromptAdapter()
        assert adapter._context.primary_context == ContextType.GENERAL

    def test_track_browser_tool(self):
        """Test tracking browser tool sets browser context"""
        adapter = PromptAdapter()

        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("browser_view")
        adapter.track_tool_use("browser_click")

        assert adapter._context.primary_context == ContextType.BROWSER

    def test_track_shell_tool(self):
        """Test tracking shell tool sets shell context"""
        adapter = PromptAdapter()

        adapter.track_tool_use("shell_exec")
        adapter.track_tool_use("shell_exec")

        assert adapter._context.primary_context == ContextType.SHELL

    def test_track_file_tool(self):
        """Test tracking file tool sets file context"""
        adapter = PromptAdapter()

        adapter.track_tool_use("file_read")
        adapter.track_tool_use("file_write")

        assert adapter._context.primary_context == ContextType.FILE

    def test_track_tool_with_error(self):
        """Test tracking tool failure records error"""
        adapter = PromptAdapter()

        adapter.track_tool_use("shell_exec", success=False, error="Command failed")

        assert len(adapter._context.recent_errors) == 1
        assert "shell_exec" in adapter._context.recent_errors[0]

    def test_increment_iteration(self):
        """Test iteration counter increment"""
        adapter = PromptAdapter()

        adapter.increment_iteration()
        adapter.increment_iteration()

        assert adapter._context.iteration_count == 2

    def test_get_context_prompt_browser(self):
        """Test getting context prompt for browser context"""
        adapter = PromptAdapter()

        # Set browser context
        for _ in range(5):
            adapter.track_tool_use("browser_navigate")

        adapter._context.iteration_count = 5  # Make it inject guidance

        prompt = adapter.get_context_prompt()

        assert prompt is not None
        assert "Browser" in prompt or "scroll" in prompt.lower()

    def test_get_context_prompt_shell(self):
        """Test getting context prompt for shell context"""
        adapter = PromptAdapter()

        for _ in range(5):
            adapter.track_tool_use("shell_exec")

        adapter._context.iteration_count = 5

        prompt = adapter.get_context_prompt()

        assert prompt is not None
        assert "Shell" in prompt or "non-interactive" in prompt.lower()

    def test_get_context_prompt_with_errors(self):
        """Test context prompt includes recent errors"""
        adapter = PromptAdapter()

        adapter.track_tool_use("shell_exec", success=False, error="Permission denied")

        prompt = adapter.get_context_prompt()

        assert prompt is not None
        assert "Recent Errors" in prompt

    def test_adapt_prompt_basic(self):
        """Test adapting a basic prompt"""
        adapter = PromptAdapter()
        base_prompt = "Execute the task."

        # No context to inject
        adapted = adapter.adapt_prompt(base_prompt)
        assert adapted == base_prompt

    def test_adapt_prompt_with_guidance(self):
        """Test adapting prompt with context guidance"""
        adapter = PromptAdapter()

        # Add error to trigger guidance injection
        adapter.track_tool_use("shell_exec", success=False, error="Error occurred")

        base_prompt = "Execute the task."
        adapted = adapter.adapt_prompt(base_prompt)

        assert "Execute the task." in adapted
        assert "Context Guidance" in adapted

    def test_should_inject_guidance_with_errors(self):
        """Test guidance injection triggered by errors"""
        adapter = PromptAdapter()

        adapter.track_tool_use("shell_exec", success=False, error="Failed")

        assert adapter.should_inject_guidance() is True

    def test_should_inject_guidance_at_threshold(self):
        """Test guidance injection at iteration thresholds"""
        adapter = PromptAdapter()

        # Get to iteration 10
        for _ in range(10):
            adapter.increment_iteration()

        assert adapter.should_inject_guidance() is True

    def test_reset(self):
        """Test adapter reset"""
        adapter = PromptAdapter()

        # Add some state
        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("shell_exec", success=False, error="Error")
        adapter.increment_iteration()

        # Reset
        adapter.reset()

        assert adapter._context.recent_tools == []
        assert adapter._context.recent_errors == []
        assert adapter._context.iteration_count == 0
        assert adapter._context.primary_context == ContextType.GENERAL

    def test_get_context(self):
        """Test getting current context"""
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_view")

        context = adapter.get_context()
        assert isinstance(context, ExecutionContext)
        assert len(context.recent_tools) == 1

    def test_get_stats(self):
        """Test getting adapter statistics"""
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec")
        adapter.increment_iteration()

        stats = adapter.get_stats()

        assert stats["iteration_count"] == 1
        assert stats["recent_tools_count"] == 1
        assert "primary_context" in stats

    def test_recent_tools_limit(self):
        """Test that recent tools respects max limit"""
        adapter = PromptAdapter(max_recent_tools=5)

        for i in range(10):
            adapter.track_tool_use(f"tool_{i}")

        assert len(adapter._context.recent_tools) == 5

    def test_recent_errors_limit(self):
        """Test that recent errors are bounded"""
        adapter = PromptAdapter()

        for i in range(10):
            adapter.track_tool_use(f"tool_{i}", success=False, error=f"Error {i}")

        assert len(adapter._context.recent_errors) == 5  # Max 5 errors
