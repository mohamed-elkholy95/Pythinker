# backend/tests/domain/services/agents/test_semantic_validation.py
"""Tests for semantic parameter validation in HallucinationDetector.

These tests verify that the validate_parameter_semantics method correctly
identifies dangerous or inappropriate parameter values that are syntactically
valid but semantically problematic.
"""

import pytest

from app.domain.services.agents.hallucination_detector import (
    ToolHallucinationDetector,
    ToolValidationResult,
)


@pytest.fixture
def detector() -> ToolHallucinationDetector:
    """Create a hallucination detector with common tools."""
    return ToolHallucinationDetector(
        available_tools=[
            "file_write",
            "file_read",
            "shell_exec",
            "browser_goto",
            "execute_command",
            "run_terminal_cmd",
        ]
    )


class TestSemanticValidationFileWrite:
    """Tests for file_write semantic validation."""

    def test_safe_file_path_passes(self, detector: ToolHallucinationDetector) -> None:
        """Safe file paths should pass validation."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="file",
            param_value="/home/user/documents/report.txt",
        )

        assert result.is_valid is True
        assert result.error_message is None

    def test_etc_path_fails(self, detector: ToolHallucinationDetector) -> None:
        """Writing to /etc/ should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="file",
            param_value="/etc/passwd",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"
        assert "/etc/" in result.error_message

    def test_usr_path_fails(self, detector: ToolHallucinationDetector) -> None:
        """Writing to /usr/ should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="file",
            param_value="/usr/bin/python",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_bin_path_fails(self, detector: ToolHallucinationDetector) -> None:
        """Writing to /bin/ should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="path",
            param_value="/bin/sh",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_env_file_fails(self, detector: ToolHallucinationDetector) -> None:
        """Writing to .env files should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="file",
            param_value="/app/config/.env",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_ssh_directory_fails(self, detector: ToolHallucinationDetector) -> None:
        """Writing to .ssh directory should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="file",
            param_value="/home/user/.ssh/authorized_keys",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_aws_credentials_fails(self, detector: ToolHallucinationDetector) -> None:
        """Writing to .aws directory should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="path",
            param_value="/home/user/.aws/credentials",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"


class TestSemanticValidationShellExec:
    """Tests for shell_exec semantic validation."""

    def test_safe_command_passes(self, detector: ToolHallucinationDetector) -> None:
        """Safe commands should pass validation."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="ls -la /home/user",
        )

        assert result.is_valid is True

    def test_rm_rf_root_fails(self, detector: ToolHallucinationDetector) -> None:
        """rm -rf / should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="rm -rf /",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"
        assert "rm" in result.error_message.lower()

    def test_rm_rf_wildcard_fails(self, detector: ToolHallucinationDetector) -> None:
        """rm -rf * should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="rm -rf *",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_sudo_command_fails(self, detector: ToolHallucinationDetector) -> None:
        """sudo commands should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="sudo apt-get install something",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_chmod_777_fails(self, detector: ToolHallucinationDetector) -> None:
        """chmod 777 should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="chmod 777 /var/www/html",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_device_write_fails(self, detector: ToolHallucinationDetector) -> None:
        """Writing to /dev/ should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="echo 'test' > /dev/sda",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_mkfs_fails(self, detector: ToolHallucinationDetector) -> None:
        """mkfs commands should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="mkfs.ext4 /dev/sda1",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_dd_to_device_fails(self, detector: ToolHallucinationDetector) -> None:
        """dd to device should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="dd if=/dev/zero of=/dev/sda",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"


class TestSemanticValidationBrowserGoto:
    """Tests for browser_goto semantic validation."""

    def test_safe_url_passes(self, detector: ToolHallucinationDetector) -> None:
        """Safe URLs should pass validation."""
        result = detector.validate_parameter_semantics(
            function_name="browser_goto",
            param_name="url",
            param_value="https://example.com/page",
        )

        assert result.is_valid is True

    def test_file_protocol_fails(self, detector: ToolHallucinationDetector) -> None:
        """file:// protocol should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="browser_goto",
            param_name="url",
            param_value="file:///etc/passwd",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_localhost_admin_fails(self, detector: ToolHallucinationDetector) -> None:
        """localhost admin URLs should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="browser_goto",
            param_name="url",
            param_value="http://localhost:8080/admin/dashboard",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_127_admin_fails(self, detector: ToolHallucinationDetector) -> None:
        """127.0.0.1 admin URLs should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="browser_goto",
            param_name="url",
            param_value="http://127.0.0.1:3000/admin",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_bind_all_interfaces_fails(self, detector: ToolHallucinationDetector) -> None:
        """0.0.0.0 URLs should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="browser_goto",
            param_name="url",
            param_value="http://0.0.0.0:8000/api",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"


class TestSemanticValidationExecuteCommand:
    """Tests for execute_command semantic validation."""

    def test_safe_command_passes(self, detector: ToolHallucinationDetector) -> None:
        """Safe commands should pass validation."""
        result = detector.validate_parameter_semantics(
            function_name="execute_command",
            param_name="command",
            param_value="python script.py",
        )

        assert result.is_valid is True

    def test_dangerous_rm_fails(self, detector: ToolHallucinationDetector) -> None:
        """Dangerous rm should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="execute_command",
            param_name="command",
            param_value="rm -rf /home/*",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"


class TestSemanticValidationRunTerminalCmd:
    """Tests for run_terminal_cmd semantic validation."""

    def test_safe_command_passes(self, detector: ToolHallucinationDetector) -> None:
        """Safe commands should pass validation."""
        result = detector.validate_parameter_semantics(
            function_name="run_terminal_cmd",
            param_name="command",
            param_value="cat /var/log/app.log",
        )

        assert result.is_valid is True

    def test_fork_bomb_fails(self, detector: ToolHallucinationDetector) -> None:
        """Fork bomb pattern should fail validation."""
        result = detector.validate_parameter_semantics(
            function_name="run_terminal_cmd",
            param_name="command",
            param_value=":;(){ :|:& };:",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"


class TestSemanticValidationWithContext:
    """Tests for semantic validation with task context."""

    def test_context_included_in_error(self, detector: ToolHallucinationDetector) -> None:
        """Task context should be included in error message."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="file",
            param_value="/etc/hosts",
            context="creating a user report",
        )

        assert result.is_valid is False
        assert "creating a user report" in result.error_message

    def test_context_included_in_suggestions(self, detector: ToolHallucinationDetector) -> None:
        """Task context should be referenced in suggestions."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="sudo reboot",
            context="generating sales report",
        )

        assert result.is_valid is False
        assert len(result.suggestions) > 0
        # Suggestions should mention confirming the action
        assert any("confirm" in s.lower() for s in result.suggestions)


class TestSemanticValidationUnknownFunction:
    """Tests for unknown function handling."""

    def test_unknown_function_passes(self, detector: ToolHallucinationDetector) -> None:
        """Unknown functions should pass (no patterns to check)."""
        result = detector.validate_parameter_semantics(
            function_name="unknown_function",
            param_name="some_param",
            param_value="any value",
        )

        assert result.is_valid is True

    def test_unknown_param_passes(self, detector: ToolHallucinationDetector) -> None:
        """Unknown parameters should pass (no patterns to check)."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="unknown_param",
            param_value="/etc/passwd",
        )

        assert result.is_valid is True


class TestSemanticValidationEdgeCases:
    """Edge cases for semantic validation."""

    def test_none_value_handled(self, detector: ToolHallucinationDetector) -> None:
        """None values should be handled gracefully."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="file",
            param_value=None,
        )

        assert result.is_valid is True  # "None" string doesn't match patterns

    def test_numeric_value_handled(self, detector: ToolHallucinationDetector) -> None:
        """Numeric values should be handled gracefully."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="file",
            param_value=12345,
        )

        assert result.is_valid is True

    def test_empty_string_passes(self, detector: ToolHallucinationDetector) -> None:
        """Empty strings should pass validation."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="",
        )

        assert result.is_valid is True

    def test_case_insensitive_matching(self, detector: ToolHallucinationDetector) -> None:
        """Pattern matching should be case insensitive."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="SUDO apt-get update",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_partial_path_match(self, detector: ToolHallucinationDetector) -> None:
        """Patterns should match anywhere in the path."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="path",
            param_value="/home/user/.ssh/known_hosts",
        )

        assert result.is_valid is False
        assert result.error_type == "semantic_violation"


class TestToolValidationResultStructure:
    """Tests for ToolValidationResult structure."""

    def test_valid_result_structure(self, detector: ToolHallucinationDetector) -> None:
        """Valid results should have correct structure."""
        result = detector.validate_parameter_semantics(
            function_name="file_write",
            param_name="file",
            param_value="/tmp/safe.txt",
        )

        assert isinstance(result, ToolValidationResult)
        assert result.is_valid is True
        assert result.error_message is None
        assert result.error_type is None
        assert result.suggestions == []

    def test_invalid_result_structure(self, detector: ToolHallucinationDetector) -> None:
        """Invalid results should have correct structure with details."""
        result = detector.validate_parameter_semantics(
            function_name="shell_exec",
            param_name="command",
            param_value="sudo rm -rf /",
        )

        assert isinstance(result, ToolValidationResult)
        assert result.is_valid is False
        assert result.error_message is not None
        assert result.error_type == "semantic_violation"
        assert isinstance(result.suggestions, list)
        assert len(result.suggestions) > 0
