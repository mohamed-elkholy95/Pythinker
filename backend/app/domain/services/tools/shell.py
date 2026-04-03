from __future__ import annotations

import logging
from importlib import import_module
from typing import TYPE_CHECKING

from app.domain.external.sandbox import Sandbox

if TYPE_CHECKING:
    from app.domain.external.config import DomainConfig
import uuid
from dataclasses import dataclass, field

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.security_critic import RiskLevel, SecurityCritic
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool
from app.domain.services.tools.shell_classifier import ShellCommandClassifier
from app.domain.services.tools.timeout_policy import TimeoutPolicy

# Maximum shell output size in characters to prevent context window exhaustion
MAX_SHELL_OUTPUT_CHARS = 50_000
CMD_BEGIN = "[CMD_BEGIN]"
CMD_END = "[CMD_END]"
_BG_OUTPUT_DIR = "/tmp/pythinker_bg"


@dataclass
class _BackgroundJob:
    """Tracks a background shell job within a session."""

    job_id: str
    session_id: str
    exec_dir: str
    command: str
    pid: int | None = None
    output_file: str = field(init=False)

    def __post_init__(self) -> None:
        self.output_file = f"{_BG_OUTPUT_DIR}/{self.job_id}.out"


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
        config: DomainConfig | None = None,
    ):
        """Initialize Shell tool class

        Args:
            sandbox: Sandbox service
            max_observe: Optional custom observation limit (default: 5000)
            security_critic: Optional security critic for command validation
            config: Optional DomainConfig for dependency injection (falls back to get_settings)
        """
        super().__init__(
            max_observe=max_observe,
            defaults=ToolDefaults(
                is_destructive=True,
                max_result_size_chars=30_000,
                category="shell",
            ),
        )
        self._config = config
        self.sandbox = sandbox
        self.security_critic = security_critic or SecurityCritic()
        self._classifier = ShellCommandClassifier()
        self._timeout_policy = TimeoutPolicy()
        self._bg_jobs: dict[str, _BackgroundJob] = {}  # job_id → job

    def _get_config(self) -> DomainConfig:
        """Return the injected DomainConfig, falling back to get_settings lazily."""
        if self._config is not None:
            return self._config
        from app.core.config import get_settings

        return get_settings()

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

        # Classify command to pick the right timeout tier
        classification = self._classifier.classify(command)
        tier = self._timeout_policy.get_tier(classification)
        shell_exec_timeout_seconds = tier.hard_seconds

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

        review = await self.security_critic.review_code(
            command, "bash", context=f"classification:{classification.value}"
        )
        if not review.safe:
            allow_medium = self._get_config().security_critic_allow_medium_risk
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

    @tool(
        name="shell_exec_background",
        description=(
            "Start a long-running shell command in the background and return immediately. "
            "Returns a job_id to track progress with shell_poll_background. "
            "Use for commands that take minutes (builds, servers, long downloads)."
        ),
        parameters={
            "id": {
                "type": "string",
                "description": "UUID of the shell session returned by shell_start.",
            },
            "exec_dir": {
                "type": "string",
                "description": "Working directory for command execution (absolute path).",
            },
            "command": {"type": "string", "description": "Shell command to run in the background."},
        },
        required=["id", "exec_dir", "command"],
        is_destructive=True,
    )
    async def shell_exec_background(self, id: str, exec_dir: str, command: str) -> ToolResult:
        """Start a shell command in the background.

        Uses nohup + output redirection so the command survives shell session resets.
        Returns a job_id immediately; use shell_poll_background to check status.
        """
        validation_error = self._validate_session_id(id, tool_name="shell_exec_background")
        if validation_error is not None:
            return validation_error
        if not exec_dir or not exec_dir.strip():
            return ToolResult(success=False, message="VALIDATION ERROR: Missing 'exec_dir' for shell_exec_background.")
        if not command or not command.strip():
            return ToolResult(success=False, message="VALIDATION ERROR: Missing 'command' for shell_exec_background.")

        review = await self.security_critic.review_code(command, "bash", context="background")
        if not review.safe:
            allow_medium = self._get_config().security_critic_allow_medium_risk
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
                    message=f"Background command blocked by security review: {issues_str}",
                )

        job_id = str(uuid.uuid4())[:8]
        job = _BackgroundJob(job_id=job_id, session_id=id, exec_dir=exec_dir, command=command)

        # Ensure output dir exists, start command with nohup, capture PID
        launch_cmd = f"mkdir -p {_BG_OUTPUT_DIR} && nohup bash -c {command!r} > {job.output_file} 2>&1 & echo $!"

        import asyncio

        try:
            result = await asyncio.wait_for(
                self.sandbox.exec_command(id, exec_dir, launch_cmd),
                timeout=15,
            )
        except TimeoutError:
            return ToolResult(success=False, message="Timed out launching background command.")

        if not result.success:
            return ToolResult(success=False, message=f"Failed to start background command: {result.message}")

        # Parse PID from output
        raw_output = (result.message or "").strip()
        pid: int | None = None
        for line in reversed(raw_output.splitlines()):
            line = line.strip()
            if line.isdigit():
                pid = int(line)
                break

        job.pid = pid
        self._bg_jobs[job_id] = job

        return ToolResult(
            success=True,
            message=f"Background job started. job_id={job_id} pid={pid} output={job.output_file}",
            data={"job_id": job_id, "pid": pid, "output_file": job.output_file},
        )

    @tool(
        name="shell_poll_background",
        description=(
            "Poll the status of a background job started with shell_exec_background. "
            "Returns current output and whether the process is still running."
        ),
        parameters={
            "id": {
                "type": "string",
                "description": "UUID of the shell session to use for polling.",
            },
            "job_id": {
                "type": "string",
                "description": "Job ID returned by shell_exec_background.",
            },
            "tail_lines": {
                "type": "integer",
                "description": "Number of output lines to return (default 50, max 200).",
            },
        },
        required=["id", "job_id"],
        is_read_only=True,
        is_concurrency_safe=True,
    )
    async def shell_poll_background(self, id: str, job_id: str, tail_lines: int = 50) -> ToolResult:
        """Poll a background job's output and running status.

        Reads the job's output file and checks whether the PID is still alive.
        Returns the last N lines of output plus a 'running' flag.
        """
        validation_error = self._validate_session_id(id, tool_name="shell_poll_background")
        if validation_error is not None:
            return validation_error

        job = self._bg_jobs.get(job_id)
        if job is None:
            return ToolResult(
                success=False,
                message=f"Unknown job_id '{job_id}'. Use shell_exec_background to start a job first.",
            )

        tail_lines = min(max(1, tail_lines), 200)

        import asyncio

        # Check if process is still running (kill -0 sends no signal, just checks existence)
        running = False
        if job.pid is not None:
            check_cmd = f"kill -0 {job.pid} 2>/dev/null && echo running || echo stopped"
            try:
                check_result = await asyncio.wait_for(
                    self.sandbox.exec_command(id, "/tmp", check_cmd),
                    timeout=10,
                )
                running = "running" in (check_result.message or "")
            except TimeoutError:
                running = False

        # Read last N lines of output
        read_cmd = f"tail -n {tail_lines} {job.output_file} 2>/dev/null || echo '[no output yet]'"
        try:
            output_result = await asyncio.wait_for(
                self.sandbox.exec_command(id, "/tmp", read_cmd),
                timeout=10,
            )
            output = self._extract_structured_output(output_result.message or "")
        except TimeoutError:
            output = "[timed out reading output]"

        status = "running" if running else "completed"
        return ToolResult(
            success=True,
            message=f"[job_id={job_id} status={status} pid={job.pid}]\n{output}",
            data={"job_id": job_id, "pid": job.pid, "status": status, "output": output},
        )
