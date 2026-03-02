"""Tests for CodeExecutorTool security integration.

Tests the integration of SecurityCritic into the code execution flow,
ensuring dangerous code is blocked and safe code executes normally.
"""

from unittest.mock import AsyncMock

import pytest

from app.domain.services.agents.security_critic import RiskLevel, SecurityResult
from app.domain.services.tools.code_executor import CodeExecutorTool


@pytest.fixture
def mock_sandbox() -> AsyncMock:
    """Create a mock sandbox for testing."""
    sandbox = AsyncMock()
    sandbox.exec_command = AsyncMock(return_value=AsyncMock(success=True, message="output"))
    sandbox.file_write = AsyncMock(return_value=AsyncMock(success=True, message="written"))
    sandbox.file_read = AsyncMock(return_value=AsyncMock(success=True, message="content"))
    sandbox.file_delete = AsyncMock(return_value=AsyncMock(success=True, message="deleted"))
    sandbox.file_list = AsyncMock(return_value=AsyncMock(success=True, message=""))
    return sandbox


@pytest.fixture
def mock_security_critic() -> AsyncMock:
    """Create a mock security critic for testing."""
    critic = AsyncMock()
    critic.review_code = AsyncMock()
    return critic


class TestCodeExecutorSecurityIntegration:
    """Tests for security critic integration in CodeExecutorTool."""

    @pytest.mark.asyncio
    async def test_code_executor_uses_security_critic(
        self,
        mock_sandbox: AsyncMock,
        mock_security_critic: AsyncMock,
    ) -> None:
        """Test that code executor calls security critic before execution."""
        mock_security_critic.review_code.return_value = SecurityResult(
            safe=True,
            risk_level=RiskLevel.LOW,
            issues=[],
        )

        executor = CodeExecutorTool(
            sandbox=mock_sandbox,
            security_critic=mock_security_critic,
        )

        await executor.code_execute(code="print('hello')", language="python")

        mock_security_critic.review_code.assert_called_once()

    @pytest.mark.asyncio
    async def test_code_executor_blocks_unsafe_code(
        self,
        mock_sandbox: AsyncMock,
        mock_security_critic: AsyncMock,
    ) -> None:
        """Test that code executor blocks code flagged as unsafe."""
        mock_security_critic.review_code.return_value = SecurityResult(
            safe=False,
            risk_level=RiskLevel.CRITICAL,
            issues=["Command injection detected"],
        )

        executor = CodeExecutorTool(
            sandbox=mock_sandbox,
            security_critic=mock_security_critic,
        )

        result = await executor.code_execute(
            code="import os; os.system(user_input)",
            language="python",
        )

        # Should not execute, return security error
        assert not result.success
        assert "blocked" in result.message.lower() or "security" in result.message.lower()

        # Sandbox should not have executed the code
        mock_sandbox.file_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_executor_without_security_critic_still_works(
        self,
        mock_sandbox: AsyncMock,
    ) -> None:
        """Test that executor works when no security critic is provided."""
        executor = CodeExecutorTool(
            sandbox=mock_sandbox,
            security_critic=None,
        )

        result = await executor.code_execute(
            code="print('hello')",
            language="python",
        )

        # Should execute successfully
        assert result.success
        # Sandbox should have been called
        mock_sandbox.file_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_security_review_passes_language_correctly(
        self,
        mock_sandbox: AsyncMock,
        mock_security_critic: AsyncMock,
    ) -> None:
        """Test that the correct language is passed to security critic."""
        mock_security_critic.review_code.return_value = SecurityResult(
            safe=True,
            risk_level=RiskLevel.LOW,
            issues=[],
        )

        executor = CodeExecutorTool(
            sandbox=mock_sandbox,
            security_critic=mock_security_critic,
        )

        # Test with Python
        await executor.code_execute(code="print('hello')", language="python")
        call_args = mock_security_critic.review_code.call_args
        assert call_args[0][0] == "print('hello')"  # code
        assert call_args[0][1] == "python"  # language

        # Reset mock and test with JavaScript
        mock_security_critic.review_code.reset_mock()
        await executor.code_execute(code="console.log('hi')", language="javascript")
        call_args = mock_security_critic.review_code.call_args
        assert call_args[0][0] == "console.log('hi')"
        assert call_args[0][1] == "javascript"

    @pytest.mark.asyncio
    async def test_high_risk_but_safe_code_executes(
        self,
        mock_sandbox: AsyncMock,
        mock_security_critic: AsyncMock,
    ) -> None:
        """Test that high-risk but safe code is allowed to execute."""
        mock_security_critic.review_code.return_value = SecurityResult(
            safe=True,  # safe=True means it can execute despite high risk
            risk_level=RiskLevel.HIGH,
            issues=["Uses shell commands but in safe manner"],
            recommendations=["Monitor execution closely"],
        )

        executor = CodeExecutorTool(
            sandbox=mock_sandbox,
            security_critic=mock_security_critic,
        )

        result = await executor.code_execute(
            code="subprocess.run(['ls', '-la'])",
            language="python",
        )

        # Should execute because safe=True
        assert result.success

    @pytest.mark.asyncio
    async def test_security_issues_listed_in_message(
        self,
        mock_sandbox: AsyncMock,
        mock_security_critic: AsyncMock,
    ) -> None:
        """Test that security issues are included in the error message."""
        issues = [
            "Command injection detected",
            "Shell execution with user input",
            "Potential privilege escalation",
        ]

        mock_security_critic.review_code.return_value = SecurityResult(
            safe=False,
            risk_level=RiskLevel.CRITICAL,
            issues=issues,
        )

        executor = CodeExecutorTool(
            sandbox=mock_sandbox,
            security_critic=mock_security_critic,
        )

        result = await executor.code_execute(
            code="os.system(user_input)",
            language="python",
        )

        assert not result.success
        # All issues should be in the message
        for issue in issues:
            assert issue in result.message

    @pytest.mark.asyncio
    async def test_security_review_before_package_install(
        self,
        mock_sandbox: AsyncMock,
        mock_security_critic: AsyncMock,
    ) -> None:
        """Test that security review happens before any sandbox operations."""
        mock_security_critic.review_code.return_value = SecurityResult(
            safe=False,
            risk_level=RiskLevel.CRITICAL,
            issues=["Dangerous code"],
        )

        executor = CodeExecutorTool(
            sandbox=mock_sandbox,
            security_critic=mock_security_critic,
        )

        await executor.code_execute(
            code="dangerous_code()",
            language="python",
            packages=["requests"],  # Package that would be installed
        )

        # Security critic should be called
        mock_security_critic.review_code.assert_called_once()

        # But package installation should NOT happen (no exec_command for pip)
        # Check that file_write wasn't called (meaning we didn't get to code writing)
        mock_sandbox.file_write.assert_not_called()


class TestCodeExecutorShortcutMethodsSecurity:
    """Test security integration with shortcut methods."""

    @pytest.mark.asyncio
    async def test_code_execute_python_uses_security(
        self,
        mock_sandbox: AsyncMock,
        mock_security_critic: AsyncMock,
    ) -> None:
        """Test that code_execute_python also uses security critic."""
        mock_security_critic.review_code.return_value = SecurityResult(
            safe=True,
            risk_level=RiskLevel.LOW,
            issues=[],
        )

        executor = CodeExecutorTool(
            sandbox=mock_sandbox,
            security_critic=mock_security_critic,
        )

        await executor.code_execute_python(code="print('hello')")

        mock_security_critic.review_code.assert_called_once()
        call_args = mock_security_critic.review_code.call_args
        assert call_args[0][1] == "python"

    @pytest.mark.asyncio
    async def test_code_execute_javascript_uses_security(
        self,
        mock_sandbox: AsyncMock,
        mock_security_critic: AsyncMock,
    ) -> None:
        """Test that code_execute_javascript also uses security critic."""
        mock_security_critic.review_code.return_value = SecurityResult(
            safe=True,
            risk_level=RiskLevel.LOW,
            issues=[],
        )

        executor = CodeExecutorTool(
            sandbox=mock_sandbox,
            security_critic=mock_security_critic,
        )

        await executor.code_execute_javascript(code="console.log('hi')")

        mock_security_critic.review_code.assert_called_once()
        call_args = mock_security_critic.review_code.call_args
        assert call_args[0][1] == "javascript"

    @pytest.mark.asyncio
    async def test_code_execute_python_strips_markdown_code_fences(
        self,
        mock_sandbox: AsyncMock,
        mock_security_critic: AsyncMock,
    ) -> None:
        """Markdown code fences should be removed before writing Python code."""
        mock_security_critic.review_code.return_value = SecurityResult(
            safe=True,
            risk_level=RiskLevel.LOW,
            issues=[],
        )

        executor = CodeExecutorTool(
            sandbox=mock_sandbox,
            security_critic=mock_security_critic,
        )

        await executor.code_execute_python(code="```python\nprint('hello')\n```")

        assert mock_sandbox.file_write.await_count >= 1
        written_code = mock_sandbox.file_write.await_args_list[0].args[1]
        assert "```" not in written_code
        assert "print('hello')" in written_code


class TestCodeExecutorReturnCodeHandling:
    """Tests for mapping sandbox returncode to tool success."""

    @pytest.mark.asyncio
    async def test_code_execute_python_marks_failure_when_returncode_non_zero(
        self,
        mock_sandbox: AsyncMock,
        mock_security_critic: AsyncMock,
    ) -> None:
        mock_security_critic.review_code.return_value = SecurityResult(
            safe=True,
            risk_level=RiskLevel.LOW,
            issues=[],
        )
        mock_sandbox.exec_command = AsyncMock(
            side_effect=[
                # Workspace init mkdir
                AsyncMock(success=True, message="ok", data={"returncode": 0}),
                # Actual python execution fails in sandbox process
                AsyncMock(
                    success=True,
                    message="Traceback (most recent call last): boom",
                    data={"returncode": 1, "output": "Traceback (most recent call last): boom"},
                ),
            ]
        )
        mock_sandbox.file_list = AsyncMock(return_value=AsyncMock(success=True, data={"entries": []}))

        executor = CodeExecutorTool(
            sandbox=mock_sandbox,
            security_critic=mock_security_critic,
        )

        result = await executor.code_execute_python(code="raise RuntimeError('boom')")

        assert result.success is False
        assert isinstance(result.data, dict)
        assert result.data["return_code"] == 1
