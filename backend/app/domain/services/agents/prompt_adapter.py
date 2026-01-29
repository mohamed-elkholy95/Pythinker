"""
Dynamic prompt adaptation based on execution context.

Injects context-specific guidance into prompts based on recent tool usage,
error states, and iteration count.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ContextType(str, Enum):
    """Types of execution context"""
    BROWSER = "browser"
    SHELL = "shell"
    FILE = "file"
    SEARCH = "search"
    MCP = "mcp"
    MESSAGE = "message"
    GENERAL = "general"


@dataclass
class ExecutionContext:
    """Tracks current execution context"""
    recent_tools: list[str] = field(default_factory=list)
    recent_errors: list[str] = field(default_factory=list)
    iteration_count: int = 0
    primary_context: ContextType = ContextType.GENERAL
    metadata: dict[str, Any] = field(default_factory=dict)


class PromptAdapter:
    """
    Adapts prompts based on execution context.

    Analyzes recent tool usage and error patterns to inject
    helpful guidance into prompts.
    """

    # Tool to context mapping
    TOOL_CONTEXTS = {
        "browser_view": ContextType.BROWSER,
        "browser_navigate": ContextType.BROWSER,
        "browser_click": ContextType.BROWSER,
        "browser_scroll": ContextType.BROWSER,
        "browser_input": ContextType.BROWSER,
        "shell_exec": ContextType.SHELL,
        "shell_run": ContextType.SHELL,
        "file_read": ContextType.FILE,
        "file_write": ContextType.FILE,
        "file_list": ContextType.FILE,
        "search_web": ContextType.SEARCH,
        "message_ask_user": ContextType.MESSAGE,
    }

    # Context-specific guidance
    CONTEXT_GUIDANCE = {
        ContextType.BROWSER: """
Browser Context Tips:
- Elements may not be visible without scrolling - use browser_scroll if elements are not found
- Wait for dynamic content to load before interacting
- Use specific CSS selectors when possible for reliability
- If an element is not clickable, it may be obscured by another element
- Consider using keyboard navigation for complex interactions
""",
        ContextType.SHELL: """
Shell Context Tips:
- Use non-interactive flags (-y, --yes, --no-input) for commands that might prompt
- Long-running commands should use timeout or background execution
- Check command exit codes to verify success
- Use absolute paths when possible for reliability
- Escape special characters in arguments properly
""",
        ContextType.FILE: """
File Context Tips:
- Always check if a file exists before reading
- Use appropriate encodings for text files
- Be careful with file permissions
- Consider file size before reading entire files
- Use relative paths from the working directory when appropriate
""",
        ContextType.SEARCH: """
Search Context Tips:
- Formulate specific, targeted search queries
- Consider using multiple searches with different phrasings
- Extract and verify information from multiple sources
- Be aware of recency - search results may be outdated
""",
    }

    # Iteration warnings
    ITERATION_THRESHOLDS = {
        10: "You've made 10 iterations. Consider if your approach is effective.",
        20: "20 iterations reached. Please reassess your strategy and consider asking for user input if blocked.",
        30: "30 iterations reached. This task is taking longer than expected. Summarize progress and blockers.",
    }

    def __init__(self, max_recent_tools: int = 10):
        """
        Initialize the prompt adapter.

        Args:
            max_recent_tools: Maximum number of recent tools to track
        """
        self._max_recent_tools = max_recent_tools
        self._context = ExecutionContext()

    def track_tool_use(self, tool_name: str, success: bool = True, error: str | None = None) -> None:
        """
        Track a tool usage for context analysis.

        Args:
            tool_name: Name of the tool used
            success: Whether the tool execution succeeded
            error: Error message if failed
        """
        self._context.recent_tools.append(tool_name)

        # Keep bounded
        if len(self._context.recent_tools) > self._max_recent_tools:
            self._context.recent_tools = self._context.recent_tools[-self._max_recent_tools:]

        # Track errors
        if not success and error:
            self._context.recent_errors.append(f"{tool_name}: {error[:100]}")
            if len(self._context.recent_errors) > 5:
                self._context.recent_errors = self._context.recent_errors[-5:]

        # Update primary context
        self._context.primary_context = self._infer_context()

        logger.debug(f"Tracked tool use: {tool_name}, context: {self._context.primary_context}")

    def increment_iteration(self) -> None:
        """Increment the iteration counter"""
        self._context.iteration_count += 1

    def _infer_context(self) -> ContextType:
        """Infer the primary context from recent tool usage"""
        if not self._context.recent_tools:
            return ContextType.GENERAL

        # Count context types from recent tools
        context_counts: dict[ContextType, int] = {}

        for tool in self._context.recent_tools[-5:]:  # Look at last 5 tools
            # Strip mcp_ prefix and check
            normalized_tool = tool
            for prefix in ["mcp_", "mcp"]:
                if tool.startswith(prefix):
                    normalized_tool = tool[len(prefix):]
                    break

            # Match to context
            context = self.TOOL_CONTEXTS.get(normalized_tool, ContextType.GENERAL)

            # Also check for partial matches (for MCP tools)
            if context == ContextType.GENERAL:
                for tool_pattern, ctx in self.TOOL_CONTEXTS.items():
                    if tool_pattern in normalized_tool.lower():
                        context = ctx
                        break

            context_counts[context] = context_counts.get(context, 0) + 1

        # Return most common context
        if context_counts:
            return max(context_counts.items(), key=lambda x: x[1])[0]

        return ContextType.GENERAL

    def get_context_prompt(self) -> str | None:
        """
        Get context-specific prompt additions.

        Returns:
            Context guidance string or None if not applicable
        """
        prompts = []

        # Add context-specific guidance
        if self._context.primary_context in self.CONTEXT_GUIDANCE:
            prompts.append(self.CONTEXT_GUIDANCE[self._context.primary_context])

        # Add error awareness if there are recent errors
        if self._context.recent_errors:
            error_summary = "\n".join(f"- {e}" for e in self._context.recent_errors[-3:])
            prompts.append(f"""
Recent Errors:
{error_summary}

Please be aware of these recent errors and adjust your approach accordingly.
""")

        # Add iteration warnings
        for threshold, warning in sorted(self.ITERATION_THRESHOLDS.items()):
            if self._context.iteration_count == threshold:
                prompts.append(f"\n**WARNING**: {warning}\n")
                break

        if prompts:
            return "\n".join(prompts)

        return None

    def adapt_prompt(self, base_prompt: str) -> str:
        """
        Adapt a prompt with context-specific additions.

        Args:
            base_prompt: The original prompt

        Returns:
            Adapted prompt with context additions
        """
        context_prompt = self.get_context_prompt()

        if context_prompt:
            return f"{base_prompt}\n\n---\nContext Guidance:\n{context_prompt}"

        return base_prompt

    def should_inject_guidance(self) -> bool:
        """
        Determine if guidance should be injected.

        Returns True if there's useful context to add.
        """
        # Inject if we have errors
        if self._context.recent_errors:
            return True

        # Inject at iteration thresholds
        if self._context.iteration_count in self.ITERATION_THRESHOLDS:
            return True

        # Inject if context is specialized (not general)
        if self._context.primary_context != ContextType.GENERAL:
            # Only inject occasionally, not every turn
            return self._context.iteration_count % 5 == 0

        return False

    def reset(self) -> None:
        """Reset the adapter state"""
        self._context = ExecutionContext()
        logger.debug("Prompt adapter reset")

    def get_context(self) -> ExecutionContext:
        """Get current execution context"""
        return self._context

    def get_stats(self) -> dict[str, Any]:
        """Get adapter statistics"""
        return {
            "iteration_count": self._context.iteration_count,
            "primary_context": self._context.primary_context.value,
            "recent_tools_count": len(self._context.recent_tools),
            "recent_errors_count": len(self._context.recent_errors),
        }
