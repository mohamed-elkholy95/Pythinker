from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

# Maximum shell output size in characters to prevent context window exhaustion
MAX_SHELL_OUTPUT_CHARS = 50_000


class ShellTool(BaseTool):
    """Shell tool class, providing Shell interaction related functions"""

    name: str = "shell"

    def __init__(self, sandbox: Sandbox, max_observe: int | None = None):
        """Initialize Shell tool class

        Args:
            sandbox: Sandbox service
            max_observe: Optional custom observation limit (default: 5000)
        """
        super().__init__(max_observe=max_observe)
        self.sandbox = sandbox

    @staticmethod
    def _truncate_output(result: ToolResult) -> ToolResult:
        """Truncate large shell output to prevent context window exhaustion."""
        if result.message and len(result.message) > MAX_SHELL_OUTPUT_CHARS:
            truncated = result.message[:MAX_SHELL_OUTPUT_CHARS]
            result.message = f"{truncated}\n\n[OUTPUT TRUNCATED — {len(result.message)} chars total, showing first {MAX_SHELL_OUTPUT_CHARS}]"
        return result

    @tool(
        name="shell_exec",
        description="Execute commands in a specified shell session. Use for running code, installing packages, or managing files.",
        parameters={
            "id": {"type": "string", "description": "Unique identifier of the target shell session"},
            "exec_dir": {
                "type": "string",
                "description": "Working directory for command execution (must use absolute path)",
            },
            "command": {"type": "string", "description": "Shell command to execute"},
        },
        required=["id", "exec_dir", "command"],
    )
    async def shell_exec(self, id: str, exec_dir: str, command: str) -> ToolResult:
        """Execute Shell command

        Args:
            id: Unique identifier of the target Shell session
            exec_dir: Working directory for command execution (must use absolute path)
            command: Shell command to execute

        Returns:
            Command execution result
        """
        result = await self.sandbox.exec_command(id, exec_dir, command)
        return self._truncate_output(result)

    @tool(
        name="shell_view",
        description="View the content of a specified shell session. Use for checking command execution results or monitoring output.",
        parameters={"id": {"type": "string", "description": "Unique identifier of the target shell session"}},
        required=["id"],
    )
    async def shell_view(self, id: str) -> ToolResult:
        """View Shell session content

        Args:
            id: Unique identifier of the target Shell session

        Returns:
            Shell session content
        """
        result = await self.sandbox.view_shell(id)
        return self._truncate_output(result)

    @tool(
        name="shell_wait",
        description="Wait for the running process in a specified shell session to return. Use after running commands that require longer runtime.",
        parameters={
            "id": {"type": "string", "description": "Unique identifier of the target shell session"},
            "seconds": {"type": "integer", "description": "Wait duration in seconds"},
        },
        required=["id"],
    )
    async def shell_wait(self, id: str, seconds: int | None = None) -> ToolResult:
        """Wait for the running process in Shell session to return

        Args:
            id: Unique identifier of the target Shell session
            seconds: Wait time (seconds), capped at 300s

        Returns:
            Wait result
        """
        max_wait_seconds = 300
        if seconds is not None:
            seconds = min(seconds, max_wait_seconds)
        return await self.sandbox.wait_for_process(id, seconds)

    @tool(
        name="shell_write_to_process",
        description="Write input to a running process in a specified shell session. Use for responding to interactive command prompts.",
        parameters={
            "id": {"type": "string", "description": "Unique identifier of the target shell session"},
            "input": {"type": "string", "description": "Input content to write to the process"},
            "press_enter": {"type": "boolean", "description": "Whether to press Enter key after input"},
        },
        required=["id", "input", "press_enter"],
    )
    async def shell_write_to_process(self, id: str, input: str, press_enter: bool) -> ToolResult:
        """Write input to the running process in Shell session

        Args:
            id: Unique identifier of the target Shell session
            input: Input content to write to the process
            press_enter: Whether to press Enter key after input

        Returns:
            Write result
        """
        return await self.sandbox.write_to_process(id, input, press_enter)

    @tool(
        name="shell_kill_process",
        description="Terminate a running process in a specified shell session. Use for stopping long-running processes or handling frozen commands.",
        parameters={"id": {"type": "string", "description": "Unique identifier of the target shell session"}},
        required=["id"],
    )
    async def shell_kill_process(self, id: str) -> ToolResult:
        """Terminate the running process in Shell session

        Args:
            id: Unique identifier of the target Shell session

        Returns:
            Termination result
        """
        return await self.sandbox.kill_process(id)
