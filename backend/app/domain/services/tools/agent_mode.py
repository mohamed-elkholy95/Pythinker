"""
Agent Mode Tool
Provides functionality to switch from Discuss mode to Agent mode for complex tasks.
"""
import logging
from typing import Optional
from app.domain.services.tools.base import tool, BaseTool
from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


class AgentModeTool(BaseTool):
    """Tool for switching between agent modes"""

    name: str = "agent_mode"

    def __init__(self):
        """Initialize agent mode tool"""
        super().__init__()
        self._mode_switch_requested = False
        self._task_description: Optional[str] = None

    @property
    def mode_switch_requested(self) -> bool:
        """Check if a mode switch has been requested"""
        return self._mode_switch_requested

    @property
    def task_description(self) -> Optional[str]:
        """Get the task description for Agent mode"""
        return self._task_description

    def reset(self) -> None:
        """Reset the mode switch state"""
        self._mode_switch_requested = False
        self._task_description = None

    @tool(
        name="agent_start_task",
        description="""IMMEDIATELY switch to Agent Mode for complex tasks. Call this tool directly without asking the user.

AUTOMATIC ACTIVATION - Call immediately when the request involves:
- Research reports, comparisons, or analysis
- Multi-step task execution
- Code writing or execution
- File creation or manipulation
- Browser automation
- Data extraction or processing
- Any task requiring planning

CRITICAL: Do NOT ask for permission. Do NOT explain the switch. Just call this tool immediately.
The user expects seamless handling of complex tasks without friction.

Agent Mode will:
1. Create a detailed plan with steps
2. Execute each step autonomously
3. Deliver results with files if needed""",
        parameters={
            "task": {
                "type": "string",
                "description": "Clear, comprehensive description of what the user wants accomplished"
            },
            "reason": {
                "type": "string",
                "description": "Brief internal note (not shown to user)"
            }
        },
        required=["task"]
    )
    async def agent_start_task(
        self,
        task: str,
        reason: Optional[str] = None
    ) -> ToolResult:
        """
        Request a switch to Agent Mode for complex task execution.

        Args:
            task: Description of the task to execute
            reason: Optional explanation for the mode switch

        Returns:
            ToolResult indicating the mode switch request
        """
        self._mode_switch_requested = True
        self._task_description = task

        logger.info(f"Mode switch to Agent requested. Task: {task[:100]}...")
        if reason:
            logger.debug(f"Reason: {reason}")

        return ToolResult(
            success=True,
            message=f"Switching to Agent Mode to handle: {task}",
            data={
                "mode": "agent",
                "task": task,
                "reason": reason
            }
        )
