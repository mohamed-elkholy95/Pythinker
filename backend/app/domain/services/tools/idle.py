from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool


class IdleTool(BaseTool):
    """Tool for signaling task completion and entering idle state"""

    name: str = "idle"

    def __init__(self):
        super().__init__(
            defaults=ToolDefaults(is_read_only=True, category="utility"),
        )

    @tool(
        name="idle",
        description="Enter idle state when all tasks are completed or user explicitly requests to stop. Use this tool to signal that the agent is ready to wait for new tasks.",
        parameters={},
        required=[],
    )
    async def idle(self) -> ToolResult:
        """Enter idle state and wait for new tasks

        Returns:
            ToolResult indicating successful transition to idle state
        """
        return ToolResult(success=True, message="Entering idle state. Waiting for new tasks.")
