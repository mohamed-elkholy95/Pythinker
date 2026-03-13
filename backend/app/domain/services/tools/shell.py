import logging
from importlib import import_module

from app.core.config import get_settings
from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.security_critic import RiskLevel, SecurityCritic
from app.domain.services.tools.base import BaseTool, tool

# Maximum shell output size in characters to prevent context window exhaustion
MAX_SHELL_OUTPUT_CHARS = 50_000
CMD_BEGIN = "[CMD_BEGIN]"
CMD_END = "[CMD_END]"
_KNOWN_PLACEHOLDER_SESSION_IDS = {
    "00000000-0000-0000-0000-000000000000",
    "550e8400-e29b-41d4-a716-446655440000",
}

logger = logging.getLogger(__name__)


def _record_security_gate_block(risk_level: str, pattern_type: str) -> None:
    """Record a security gate block metric without static infra-layer imports."""
    try:
        metrics = import_module("app.core.prometheus_metrics")
        metrics.record_security_gate_block(risk_level=risk_level, pattern_type=pattern_type)
    except Exception:
        logger.debug("Failed to record security_gate_block metric", exc_info=True)


def _record_security_gate_override(override_reason: str) -> None:
    """Record a security gate override metric without static infra-layer imports."""
    try:
        metrics = import_module("app.core.prometheus_metrics")
        metrics.record_security_gate_override(override_reason=override_reason)
    except Exception:
        logger.debug("Failed to record security_gate_override metric", exc_info=True)


class ShellTool(BaseTool):
    """Shell tool class, providing Shell interaction related functions"""

    name: str = "shell"

    def __init__(
        self,
        sandbox: Sandbox,
        max_observe: int | None = None,
        security_critic: SecurityCritic | None = None,
    ):
        """Initialize Shell tool class

        Args:
            sandbox: Sandbox service
            max_observe: Optional custom observation limit (default: 5000)
            security_critic: Optional security critic for command validation
        """
        super().__init__(max_observe=max_observe)
        self.sandbox = sandbox
        self.security_critic = security_critic or SecurityCritic()

    @staticmethod
    def _truncate_output(result: ToolResult) -> ToolResult:
        """Truncate large shell output to prevent context window exhaustion."""
        if result.message and len(result.message) > MAX_SHELL_OUTPUT_CHARS:
            truncated = result.message[:MAX_SHELL_OUTPUT_CHARS]
            result.message = f"{truncated}\n\n[OUTPUT TRUNCATED — {len(result.message)} chars total, showing first {MAX_SHELL_OUTPUT_CHARS}]"
        return result

    @staticmethod
    def _extract_structured_output(raw: str) -> str:
        """Extract clean output from structured markers if present.
        Falls back to raw output when markers are absent (old sandbox images).
        """
        if CMD_BEGIN not in raw:
            return raw
        blocks = []
        for block in raw.split(CMD_BEGIN):
            if not block.strip():
                continue
            if CMD_END in block:
                content, _ = block.rsplit(CMD_END, 1)
                blocks.append(content.strip())
            else:
                blocks.append(block.strip())
        return "\n".join(blocks) if blocks else raw

    @staticmethod
    def _validate_session_id(id: str, *, tool_name: str) -> ToolResult | None:
        """Validate shell session ids and block known hallucinated placeholders.

        Real session ids may be UUIDs or shorter opaque IDs (for example session keys),
        so validation intentionally avoids UUID-only checks.
        """
        session_id = (id or "").strip()
        if not session_id:
            return ToolResult(
                success=False,
                message=f"VALIDATION ERROR: Missing required parameter 'id' for {tool_name}.",
            )
        if session_id in _KNOWN_PLACEHOLDER_SESSION_IDS:
            return ToolResult(
                success=False,
                message=(
                    "VALIDATION ERROR: Placeholder session ID detected. "
                    "Use a real shell session id returned by shell_exec."
                ),
            )
        return None

    @tool(
        name="shell_exec",
        description="Execute commands in a specified shell session. Use for running code, installing packages, or managing files.",
        parameters={
            "id": {
                "type": "string",
                "description": "UUID of the shell session returned by shell_start. Must be a real session UUID, not a tool name.",
            },
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
        import asyncio

        # Default timeout for shell commands (5 minutes)
        shell_exec_timeout_seconds = 300

        validation_error = self._validate_session_id(id, tool_name="shell_exec")
        if validation_error is not None:
            return validation_error
        if not exec_dir or not exec_dir.strip():
            return ToolResult(
                success=False,
                message="VALIDATION ERROR: Missing required parameter 'exec_dir' for shell_exec.",
            )
        if not command or not command.strip():
            return ToolResult(
                success=False,
                message="VALIDATION ERROR: Missing required parameter 'command' for shell_exec.",
            )

        review = await self.security_critic.review_code(command, "bash")
        if not review.safe:
            allow_medium = get_settings().security_critic_allow_medium_risk
            if review.risk_level == RiskLevel.MEDIUM and allow_medium:
                _record_security_gate_override(override_reason="medium_risk_dev")
            else:
                _record_security_gate_block(
                    risk_level=review.risk_level.value,
                    pattern_type="static" if review.patterns_detected else "llm",
                )
                issues_str = ", ".join(review.issues) if review.issues else "Security review failed"
                return ToolResult(
                    success=False,
                    message=f"Shell command blocked by security review: {issues_str}",
                )

        try:
            result = await asyncio.wait_for(
                self.sandbox.exec_command(id, exec_dir, command),
                timeout=shell_exec_timeout_seconds,
            )
            data = result.data if isinstance(result.data, dict) else {}
            raw_return_code = data.get("returncode", data.get("return_code"))
            if isinstance(raw_return_code, int) and raw_return_code != 0:
                output = data.get("output")
                detail = result.message or (str(output) if output is not None else "")
                result = ToolResult(
                    success=False,
                    message=f"Shell command failed (return code: {raw_return_code}).\n{detail}".strip(),
                    data=result.data,
                    suggested_filename=result.suggested_filename,
                )
            if result.message:
                result.message = self._extract_structured_output(result.message)
            return self._truncate_output(result)
        except TimeoutError:
            logger.warning(
                "Shell command timed out after %ss: %s",
                shell_exec_timeout_seconds,
                command[:100],
            )
            return ToolResult(
                success=False,
                message=f"Shell command timed out after {shell_exec_timeout_seconds} seconds. "
                f"Consider breaking the command into smaller parts or using background execution.",
            )

    @tool(
        name="shell_view",
        description="View the content of a specified shell session. Use for checking command execution results or monitoring output.",
        parameters={
            "id": {
                "type": "string",
                "description": "UUID of the shell session returned by shell_start. Must be a real session UUID, not a tool name.",
            }
        },
        required=["id"],
    )
    async def shell_view(self, id: str) -> ToolResult:
        """View Shell session content

        Args:
            id: Unique identifier of the target Shell session

        Returns:
            Shell session content
        """
        validation_error = self._validate_session_id(id, tool_name="shell_view")
        if validation_error is not None:
            return validation_error
        result = await self.sandbox.view_shell(id)
        if result.message:
            result.message = self._extract_structured_output(result.message)
        return self._truncate_output(result)

    @tool(
        name="shell_wait",
        description="Wait for the running process in a specified shell session to return. Use after running commands that require longer runtime.",
        parameters={
            "id": {
                "type": "string",
                "description": "UUID of the shell session returned by shell_start. Must be a real session UUID, not a tool name.",
            },
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
        validation_error = self._validate_session_id(id, tool_name="shell_wait")
        if validation_error is not None:
            return validation_error
        max_wait_seconds = 300
        if seconds is not None:
            seconds = min(seconds, max_wait_seconds)
        return await self.sandbox.wait_for_process(id, seconds)

    @tool(
        name="shell_write_to_process",
        description="Write input to a running process in a specified shell session. Use for responding to interactive command prompts.",
        parameters={
            "id": {
                "type": "string",
                "description": "UUID of the shell session returned by shell_start. Must be a real session UUID, not a tool name.",
            },
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
        validation_error = self._validate_session_id(id, tool_name="shell_write_to_process")
        if validation_error is not None:
            return validation_error
        return await self.sandbox.write_to_process(id, input, press_enter)

    @tool(
        name="shell_kill_process",
        description="Terminate a running process in a specified shell session. Use for stopping long-running processes or handling frozen commands.",
        parameters={
            "id": {
                "type": "string",
                "description": "UUID of the shell session returned by shell_start. Must be a real session UUID, not a tool name.",
            }
        },
        required=["id"],
    )
    async def shell_kill_process(self, id: str) -> ToolResult:
        """Terminate the running process in Shell session

        Args:
            id: Unique identifier of the target Shell session

        Returns:
            Termination result
        """
        validation_error = self._validate_session_id(id, tool_name="shell_kill_process")
        if validation_error is not None:
            return validation_error
        return await self.sandbox.kill_process(id)
