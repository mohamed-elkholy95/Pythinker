"""
Multi-language code execution engine.

Provides a high-level interface for executing code in multiple languages
(Python, JavaScript, Bash) with features like dynamic package installation,
isolated execution directories, artifact collection, and resource limits.
"""

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from importlib import import_module
from typing import Any

from app.core.config import get_settings
from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.security_critic import RiskLevel, SecurityCritic
from app.domain.services.tools.base import BaseTool, tool

logger = logging.getLogger(__name__)


def _record_security_gate_block(risk_level: str, pattern_type: str) -> None:
    """Record a security gate block metric without static infra-layer imports."""
    try:
        metrics = import_module("app.infrastructure.observability.prometheus_metrics")
        metrics.record_security_gate_block(risk_level=risk_level, pattern_type=pattern_type)
    except Exception:
        logger.debug("Failed to record security_gate_block metric", exc_info=True)


def _record_security_gate_override(override_reason: str) -> None:
    """Record a security gate override metric without static infra-layer imports."""
    try:
        metrics = import_module("app.infrastructure.observability.prometheus_metrics")
        metrics.record_security_gate_override(override_reason=override_reason)
    except Exception:
        logger.debug("Failed to record security_gate_override metric", exc_info=True)


class Language(str, Enum):
    """Supported programming languages."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    BASH = "bash"
    SQL = "sql"


# Language configuration mapping
LANGUAGE_CONFIG: dict[str, dict[str, Any]] = {
    Language.PYTHON: {
        "interpreter": "python3",
        "package_manager": "pip3",
        "install_cmd": "pip3 install --quiet --disable-pip-version-check",
        "file_extension": ".py",
        "run_cmd": "python3",
        "timeout_default": 300,
        "shebang": "#!/usr/bin/env python3",
    },
    Language.JAVASCRIPT: {
        "interpreter": "node",
        "package_manager": "npm",
        "install_cmd": "npm install --silent",
        "file_extension": ".js",
        "run_cmd": "node",
        "timeout_default": 300,
        "shebang": "#!/usr/bin/env node",
    },
    Language.BASH: {
        "interpreter": "bash",
        "package_manager": None,
        "install_cmd": None,
        "file_extension": ".sh",
        "run_cmd": "bash",
        "timeout_default": 120,
        "shebang": "#!/bin/bash",
    },
    Language.SQL: {
        "interpreter": "sqlite3",
        "package_manager": None,
        "install_cmd": None,
        "file_extension": ".sql",
        "run_cmd": "sqlite3",
        "timeout_default": 60,
        "shebang": None,
    },
}


@dataclass
class ExecutionResult:
    """Result of code execution."""

    success: bool
    output: str
    error: str | None = None
    return_code: int = 0
    execution_time_ms: int | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    packages_installed: list[str] = field(default_factory=list)
    working_directory: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "return_code": self.return_code,
            "execution_time_ms": self.execution_time_ms,
            "artifacts": self.artifacts,
            "packages_installed": self.packages_installed,
            "working_directory": self.working_directory,
        }


@dataclass
class Artifact:
    """A file artifact produced by code execution."""

    filename: str
    path: str
    size_bytes: int
    created_at: datetime = field(default_factory=datetime.now)
    content_preview: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "filename": self.filename,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat(),
            "content_preview": self.content_preview,
        }


class CodeExecutorTool(BaseTool):
    """
    Multi-language code execution tool.

    Supports Python, JavaScript, and Bash execution with:
    - Dynamic package installation (pip for Python, npm for JavaScript)
    - Isolated workspace directories per session
    - Artifact collection
    - Configurable timeouts and resource limits
    - Environment variable injection
    """

    name: str = "code_executor"

    def __init__(
        self,
        sandbox: Sandbox,
        session_id: str | None = None,
        max_observe: int | None = None,
        security_critic: SecurityCritic | None = None,
    ):
        """
        Initialize Code Executor tool.

        Args:
            sandbox: Sandbox service for code execution
            session_id: Session identifier for workspace isolation
            max_observe: Optional custom observation limit
            security_critic: Optional security critic for code review before execution
        """
        super().__init__(max_observe=max_observe)
        self.sandbox = sandbox
        self.session_id = session_id or str(uuid.uuid4())
        self._workspace_base = "/workspace"
        self._workspace_path = f"{self._workspace_base}/{self.session_id}"
        self._initialized = False
        self._workspace_init_lock = asyncio.Lock()
        self.security_critic = security_critic or SecurityCritic()

    async def _ensure_workspace(self) -> None:
        """Ensure workspace directory exists."""
        if self._initialized:
            return

        async with self._workspace_init_lock:
            if self._initialized:
                return

            # Create workspace directory
            result = await self.sandbox.exec_command(self.session_id, "/", f"mkdir -p {self._workspace_path}")

            if not result.success:
                logger.warning(f"Failed to create workspace: {result.message}")

            self._initialized = True
            logger.debug(f"Workspace initialized at {self._workspace_path}")

    async def _install_packages(
        self,
        language: Language,
        packages: list[str],
    ) -> tuple[bool, list[str], str]:
        """
        Install packages for the specified language.

        Args:
            language: Programming language
            packages: List of packages to install

        Returns:
            Tuple of (success, installed_packages, output)
        """
        if not packages:
            return True, [], ""

        config = LANGUAGE_CONFIG.get(language)
        if not config or not config.get("install_cmd"):
            return True, [], "No package manager available for this language"

        install_cmd = config["install_cmd"]
        installed = []
        outputs = []

        for package in packages:
            # Sanitize package name (basic security check)
            if not self._is_safe_package_name(package):
                outputs.append(f"Skipping unsafe package name: {package}")
                continue

            cmd = f"{install_cmd} {package}"
            result = await self.sandbox.exec_command(self.session_id, self._workspace_path, cmd)

            if result.success:
                installed.append(package)
                outputs.append(f"Installed: {package}")
            else:
                outputs.append(f"Failed to install {package}: {result.message}")

        success = len(installed) == len(packages) or len(installed) > 0
        return success, installed, "\n".join(outputs)

    def _is_safe_package_name(self, package: str) -> bool:
        """Basic validation of package name to prevent command injection."""
        # Allow alphanumeric, dash, underscore, dot, and version specifiers
        import re

        pattern = r"^[a-zA-Z0-9_\-\.]+([<>=!]+[a-zA-Z0-9_\-\.]+)?$"
        return bool(re.match(pattern, package))

    async def _collect_artifacts(self) -> list[Artifact]:
        """
        Collect artifacts from the workspace directory.

        Returns:
            List of Artifact objects
        """
        artifacts = []

        # List files in workspace
        result = await self.sandbox.file_list(self._workspace_path)
        if not result.success:
            return artifacts

        # Parse file list from result
        if isinstance(result.message, str):
            # Try to parse as file listing
            lines = result.message.strip().split("\n")
            for line in lines:
                if line.strip():
                    # Skip directories, get file info
                    parts = line.split()
                    if len(parts) >= 1:
                        filename = parts[-1]
                        if filename not in [".", ".."] and not filename.startswith("."):
                            file_path = f"{self._workspace_path}/{filename}"
                            # Get file size
                            size_result = await self.sandbox.exec_command(
                                self.session_id,
                                self._workspace_path,
                                f"stat -f%z '{filename}' 2>/dev/null || stat -c%s '{filename}' 2>/dev/null || echo 0",
                            )
                            size = 0
                            if size_result.success and size_result.message:
                                with contextlib.suppress(ValueError):
                                    size = int(size_result.message.strip())

                            # Get content preview for text files
                            preview = None
                            if size < 10000:  # Only preview small files
                                preview_result = await self.sandbox.file_read(file_path, end_line=10)
                                if preview_result.success:
                                    preview = preview_result.message[:500] if preview_result.message else None

                            artifacts.append(
                                Artifact(
                                    filename=filename,
                                    path=file_path,
                                    size_bytes=size,
                                    content_preview=preview,
                                )
                            )

        return artifacts

    @tool(
        name="code_execute",
        description="Execute code in a specified programming language. Supports Python, JavaScript (Node.js), Bash, and SQL (SQLite). Can install packages before execution and returns any generated artifacts.",
        parameters={
            "language": {
                "type": "string",
                "description": "Programming language to use",
                "enum": ["python", "javascript", "bash", "sql"],
            },
            "code": {"type": "string", "description": "The code to execute"},
            "packages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of packages to install before execution (e.g., ['requests', 'pandas'])",
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds (default: 300 for Python/JS, 120 for Bash)",
            },
            "env_vars": {"type": "object", "description": "Environment variables to set during execution"},
            "working_dir": {
                "type": "string",
                "description": "Working directory for execution (defaults to session workspace)",
            },
        },
        required=["language", "code"],
    )
    async def code_execute(
        self,
        language: str,
        code: str,
        packages: list[str] | None = None,
        timeout: int | None = None,  # noqa: ASYNC109
        env_vars: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> ToolResult:
        """
        Execute code in the specified language.

        Args:
            language: Programming language (python, javascript, bash)
            code: Code to execute
            packages: Optional packages to install before execution
            timeout: Execution timeout in seconds
            env_vars: Optional environment variables
            working_dir: Working directory (defaults to session workspace)

        Returns:
            ToolResult with execution output and artifacts
        """
        start_time = datetime.now()

        # Validate language
        try:
            lang = Language(language.lower())
        except ValueError:
            return ToolResult(
                success=False, message=f"Unsupported language: {language}. Supported: python, javascript, bash, sql"
            )

        # Mandatory security gate before execution
        review = await self.security_critic.review_code(code, language)
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
                    message=f"Code execution blocked by security review: {issues_str}",
                )

        # Get language config
        config = LANGUAGE_CONFIG[lang]

        # Ensure workspace exists
        await self._ensure_workspace()

        # Use default timeout if not specified
        if timeout is None:
            timeout = config["timeout_default"]

        # Set working directory
        work_dir = working_dir or self._workspace_path

        # Install packages if specified
        packages_installed = []
        if packages:
            pkg_success, packages_installed, pkg_output = await self._install_packages(lang, packages)
            if not pkg_success and not packages_installed:
                return ToolResult(success=False, message=f"Failed to install packages:\n{pkg_output}")
            logger.info(f"Installed packages: {packages_installed}")

        # Generate unique filename for the code
        file_id = str(uuid.uuid4())[:8]
        file_ext = config["file_extension"]
        code_file = f"exec_{file_id}{file_ext}"
        code_path = f"{work_dir}/{code_file}"

        # Add shebang if applicable
        if config.get("shebang") and not code.startswith("#!"):
            code = f"{config['shebang']}\n{code}"

        # Write code to file
        write_result = await self.sandbox.file_write(code_path, code)
        if not write_result.success:
            return ToolResult(success=False, message=f"Failed to write code file: {write_result.message}")

        # Build execution command
        run_cmd = config["run_cmd"]

        # Build environment prefix if env_vars specified
        env_prefix = ""
        if env_vars:
            env_parts = [f"{k}='{v}'" for k, v in env_vars.items()]
            env_prefix = " ".join(env_parts) + " "

        # Execute the code
        if lang == Language.BASH:
            # Make bash script executable
            await self.sandbox.exec_command(self.session_id, work_dir, f"chmod +x {code_file}")
            exec_cmd = f"{env_prefix}./{code_file}"
        elif lang == Language.SQL:
            # SQL execution with sqlite3
            exec_cmd = f"{env_prefix}{run_cmd} < {code_file}"
        else:
            exec_cmd = f"{env_prefix}{run_cmd} {code_file}"

        # Execute with timeout
        exec_result = await self.sandbox.exec_command(self.session_id, work_dir, f"timeout {timeout}s {exec_cmd} 2>&1")

        # Calculate execution time
        execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        # Clean up code file
        await self.sandbox.file_delete(code_path)

        # Collect artifacts
        artifacts = await self._collect_artifacts()
        artifact_dicts = [a.to_dict() for a in artifacts]

        # Build result
        result = ExecutionResult(
            success=exec_result.success,
            output=exec_result.message or "",
            return_code=0 if exec_result.success else 1,
            execution_time_ms=execution_time_ms,
            artifacts=artifact_dicts,
            packages_installed=packages_installed,
            working_directory=work_dir,
        )

        # Build message
        message_parts = []

        if packages_installed:
            message_parts.append(f"📦 Packages installed: {', '.join(packages_installed)}")

        message_parts.append(f"⏱️ Execution time: {execution_time_ms}ms")

        if exec_result.message:
            message_parts.append(f"\n📤 Output:\n{exec_result.message}")

        if artifacts:
            message_parts.append(f"\n📁 Artifacts ({len(artifacts)} files):")
            message_parts.extend(
                f"  - {artifact.filename} ({artifact.size_bytes} bytes)" for artifact in artifacts[:5]
            )  # Show first 5
            if len(artifacts) > 5:
                message_parts.append(f"  ... and {len(artifacts) - 5} more files")

        return ToolResult(success=exec_result.success, message="\n".join(message_parts), data=result.to_dict())

    @tool(
        name="code_execute_python",
        description="Execute Python code with optional package installation. Shortcut for code_execute with language='python'.",
        parameters={
            "code": {"type": "string", "description": "Python code to execute"},
            "packages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Python packages to install via pip (e.g., ['requests', 'pandas'])",
            },
            "timeout": {"type": "integer", "description": "Execution timeout in seconds (default: 300)"},
        },
        required=["code"],
    )
    async def code_execute_python(
        self,
        code: str,
        packages: list[str] | None = None,
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> ToolResult:
        """
        Execute Python code.

        Args:
            code: Python code to execute
            packages: Optional packages to install
            timeout: Execution timeout in seconds

        Returns:
            ToolResult with execution output
        """
        return await self.code_execute(
            language="python",
            code=code,
            packages=packages,
            timeout=timeout,
        )

    @tool(
        name="code_execute_javascript",
        description="Execute JavaScript (Node.js) code with optional npm package installation.",
        parameters={
            "code": {"type": "string", "description": "JavaScript code to execute"},
            "packages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "NPM packages to install (e.g., ['axios', 'lodash'])",
            },
            "timeout": {"type": "integer", "description": "Execution timeout in seconds (default: 300)"},
        },
        required=["code"],
    )
    async def code_execute_javascript(
        self,
        code: str,
        packages: list[str] | None = None,
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> ToolResult:
        """
        Execute JavaScript code.

        Args:
            code: JavaScript code to execute
            packages: Optional npm packages to install
            timeout: Execution timeout in seconds

        Returns:
            ToolResult with execution output
        """
        return await self.code_execute(
            language="javascript",
            code=code,
            packages=packages,
            timeout=timeout,
        )

    @tool(
        name="code_list_artifacts",
        description="List all artifacts (files) in the current session's workspace directory.",
        parameters={},
        required=[],
    )
    async def code_list_artifacts(self) -> ToolResult:
        """
        List all artifacts in the workspace.

        Returns:
            ToolResult with list of artifacts
        """
        await self._ensure_workspace()

        artifacts = await self._collect_artifacts()

        if not artifacts:
            return ToolResult(
                success=True,
                message="No artifacts found in workspace.",
                data={"artifacts": [], "workspace": self._workspace_path},
            )

        message_parts = [f"📁 Workspace: {self._workspace_path}", ""]
        message_parts.extend(f"  {artifact.filename} ({artifact.size_bytes} bytes)" for artifact in artifacts)

        return ToolResult(
            success=True,
            message="\n".join(message_parts),
            data={
                "artifacts": [a.to_dict() for a in artifacts],
                "workspace": self._workspace_path,
            },
        )

    @tool(
        name="code_read_artifact",
        description="Read the contents of an artifact file from the workspace.",
        parameters={"filename": {"type": "string", "description": "Name of the artifact file to read"}},
        required=["filename"],
    )
    async def code_read_artifact(self, filename: str) -> ToolResult:
        """
        Read an artifact file.

        Args:
            filename: Name of the file to read

        Returns:
            ToolResult with file contents
        """
        await self._ensure_workspace()

        file_path = f"{self._workspace_path}/{filename}"

        result = await self.sandbox.file_read(file_path)

        if not result.success:
            return ToolResult(success=False, message=f"Failed to read artifact: {result.message}")

        content = ""
        resolved_path = file_path
        if isinstance(result.data, dict):
            content = result.data.get("content") or ""
            resolved_path = result.data.get("file") or file_path
        elif isinstance(result.message, str):
            # Fallback for legacy sandbox responses that put content in message.
            content = result.message

        return ToolResult(
            success=True,
            message=f"📄 Contents of {filename}:\n\n{content}",
            data={"filename": filename, "content": content, "path": resolved_path},
        )

    @tool(
        name="code_cleanup_workspace",
        description="Clean up the session workspace by removing all files.",
        parameters={"confirm": {"type": "boolean", "description": "Confirm cleanup operation (must be true)"}},
        required=["confirm"],
    )
    async def code_cleanup_workspace(self, confirm: bool = False) -> ToolResult:
        """
        Clean up the workspace directory.

        Args:
            confirm: Must be True to confirm cleanup

        Returns:
            ToolResult with cleanup status
        """
        if not confirm:
            return ToolResult(success=False, message="Cleanup not confirmed. Set confirm=true to proceed.")

        await self._ensure_workspace()

        # Remove all files in workspace
        result = await self.sandbox.exec_command(
            self.session_id,
            self._workspace_path,
            "rm -rf ./* 2>/dev/null; rm -rf ./.[!.]* 2>/dev/null; echo 'Cleanup complete'",
        )

        if result.success:
            return ToolResult(success=True, message=f"🧹 Workspace cleaned: {self._workspace_path}")
        return ToolResult(success=False, message=f"Cleanup failed: {result.message}")

    @tool(
        name="code_save_artifact",
        description="Save content to a file in the workspace as an artifact.",
        parameters={
            "filename": {"type": "string", "description": "Name for the artifact file"},
            "content": {"type": "string", "description": "Content to save to the file"},
        },
        required=["filename", "content"],
    )
    async def code_save_artifact(
        self,
        filename: str,
        content: str,
    ) -> ToolResult:
        """
        Save content as an artifact file.

        Args:
            filename: Name for the file
            content: Content to save

        Returns:
            ToolResult with save status
        """
        await self._ensure_workspace()

        file_path = f"{self._workspace_path}/{filename}"

        result = await self.sandbox.file_write(file_path, content)

        if result.success:
            return ToolResult(
                success=True,
                message=f"💾 Saved artifact: {filename} ({len(content)} bytes)",
                data={"filename": filename, "path": file_path, "size": len(content)},
            )
        return ToolResult(success=False, message=f"Failed to save artifact: {result.message}")
