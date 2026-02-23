"""Tool Efficiency Monitor for Detecting Analysis Paralysis

Monitors tool usage patterns to detect read-without-write imbalance:
- Multiple consecutive reads without corresponding writes
- Excessive browsing/searching without action
- Repeated information gathering without progress

Injects nudge messages to guide agent toward action.

Expected impact: 50%+ reduction in analysis paralysis patterns.

Context7 validated: Dataclass pattern, sliding window monitoring.
"""

import logging
from collections import deque
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass
class EfficiencySignal:
    """Signal indicating efficiency status.

    Context7 validated: Dataclass for simple data containers.
    """

    is_balanced: bool
    read_count: int
    action_count: int
    nudge_message: str | None = None
    confidence: float = 1.0
    hard_stop: bool = False  # When True, search tools should be blocked


class ToolEfficiencyMonitor:
    """Monitors tool usage for read-without-write imbalance.

    Tracks sliding window of recent tool calls and detects patterns:
    - 5+ consecutive reads without writes → nudge to take action
    - 6+ consecutive reads → hard stop

    Context7 validated: Sliding window pattern, threshold-based detection.
    """

    # Tool classification
    READ_TOOLS: ClassVar[set[str]] = {
        # File read operations
        "file_read",
        "file_list",
        "file_list_directory",
        "file_search",
        "file_find",
        "file_find_by_name",
        "file_find_in_content",
        "file_view",
        # Browser read operations
        "browser_view",
        "browser_get_content",
        "browser_navigate",
        "browser_screenshot",
        "browser_agent_extract",
        # Search operations
        "info_search_web",
        "search",
        "wide_research",
        # Code read operations
        "code_list_artifacts",
        "code_read_artifact",
        # Workspace read operations
        "workspace_info",
        "workspace_tree",
        # Shell read operations
        "shell_view",
        # MCP read operations (pattern-based)
        "mcp_list_resources",
        "mcp_read_resource",
    }

    ACTION_TOOLS: ClassVar[set[str]] = {
        # File write operations
        "file_write",
        "file_create",
        "file_delete",
        "file_rename",
        "file_move",
        # Browser action operations
        "browser_click",
        "browser_input",
        "browser_agent",  # Autonomous browser agent
        # Code execution
        "code_execute",
        "code_create_artifact",
        "code_update_artifact",
        # Shell execution
        "shell_exec",
        # User interaction
        "message_ask_user",
        "message_notify_user",
        # Export operations
        "export",
    }

    def __init__(
        self,
        window_size: int = 10,
        read_threshold: int = 5,
        strong_threshold: int = 6,
    ):
        """Initialize tool efficiency monitor.

        Args:
            window_size: Number of recent tool calls to track
            read_threshold: Consecutive reads before nudge
            strong_threshold: Consecutive reads before strong nudge

        Context7 validated: Constructor with sensible defaults.
        """
        self.window_size = window_size
        self.read_threshold = read_threshold
        self.strong_threshold = strong_threshold

        # Sliding window of recent tool calls
        self._recent_tools: deque[str] = deque(maxlen=window_size)

        # Consecutive read counter
        self._consecutive_reads = 0

    def record(self, tool_name: str) -> None:
        """Record a tool call and update counters.

        Args:
            tool_name: Name of the tool that was called

        Context7 validated: Simple state update pattern.
        """
        self._recent_tools.append(tool_name)

        # Update consecutive read counter
        if self._is_read_tool(tool_name):
            self._consecutive_reads += 1
        elif self._is_action_tool(tool_name):
            # Action resets the counter
            self._consecutive_reads = 0

    def check_efficiency(self) -> EfficiencySignal:
        """Check if tool usage is balanced.

        Returns:
            EfficiencySignal with nudge message if imbalanced

        Context7 validated: Threshold-based pattern detection.
        """
        # Count reads and actions in recent window
        read_count = sum(1 for tool in self._recent_tools if self._is_read_tool(tool))
        action_count = sum(1 for tool in self._recent_tools if self._is_action_tool(tool))

        # Check for consecutive reads
        if self._consecutive_reads >= self.strong_threshold:
            return EfficiencySignal(
                is_balanced=False,
                read_count=read_count,
                action_count=action_count,
                nudge_message=(
                    f"⛔ HARD STOP — WRITE NOW: You have performed {self._consecutive_reads} consecutive "
                    f"search/read operations without writing a single file or taking any action. "
                    f"Search tools are now temporarily disabled.\n\n"
                    f"You MUST immediately:\n"
                    f"1. Use `file_write` to save your findings to disk\n"
                    f"2. Synthesize what you already know into the output\n"
                    f"3. Do NOT search again — you have enough information\n\n"
                    f"Continuing to search without writing is analysis paralysis. Write now."
                ),
                confidence=0.95,
                hard_stop=True,
            )

        if self._consecutive_reads >= self.read_threshold:
            return EfficiencySignal(
                is_balanced=False,
                read_count=read_count,
                action_count=action_count,
                nudge_message=(
                    f"⚠️ STOP SEARCHING — START WRITING: {self._consecutive_reads} consecutive reads "
                    f"with no output produced. You likely have enough information already.\n"
                    f"Do NOT search again. Use `file_write` to save your findings now and make progress."
                ),
                confidence=0.75,
            )

        # Balanced - no nudge needed
        return EfficiencySignal(
            is_balanced=True,
            read_count=read_count,
            action_count=action_count,
            nudge_message=None,
        )

    def reset(self) -> None:
        """Reset all counters and clear history.

        Context7 validated: State reset pattern.
        """
        self._recent_tools.clear()
        self._consecutive_reads = 0

    def _is_read_tool(self, tool_name: str) -> bool:
        """Check if tool is a read operation.

        Args:
            tool_name: Tool name to check

        Returns:
            True if tool is a read operation
        """
        # Direct match in READ_TOOLS
        if tool_name in self.READ_TOOLS:
            return True

        # Pattern-based matching for MCP tools
        return bool(tool_name.startswith(("mcp_get_", "mcp_list_", "mcp_search_", "mcp_read_", "mcp_fetch_")))

    def _is_action_tool(self, tool_name: str) -> bool:
        """Check if tool is an action operation.

        Args:
            tool_name: Tool name to check

        Returns:
            True if tool is an action operation
        """
        # Direct match in ACTION_TOOLS
        if tool_name in self.ACTION_TOOLS:
            return True

        # Pattern-based matching for MCP tools
        return bool(tool_name.startswith(("mcp_create_", "mcp_update_", "mcp_delete_", "mcp_write_", "mcp_execute_")))


# Singleton instance
_efficiency_monitor: ToolEfficiencyMonitor | None = None


def get_efficiency_monitor(
    window_size: int = 10,
    read_threshold: int = 5,
    strong_threshold: int = 6,
) -> ToolEfficiencyMonitor:
    """Get or create the global tool efficiency monitor.

    Args:
        window_size: Number of recent tool calls to track
        read_threshold: Consecutive reads before nudge

    Returns:
        ToolEfficiencyMonitor instance

    Context7 validated: Singleton factory pattern.
    """
    global _efficiency_monitor
    if _efficiency_monitor is None:
        _efficiency_monitor = ToolEfficiencyMonitor(
            window_size=window_size,
            read_threshold=read_threshold,
            strong_threshold=strong_threshold,
        )
    return _efficiency_monitor
