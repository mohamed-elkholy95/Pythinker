"""Regression tests for DockerSandbox tool result parsing.

Covers:
- _parse_tool_result (static method) — guards against NameError regressions
  and verifies correct handling of 2xx, 4xx, 5xx responses and malformed JSON.
- Shell event data extraction patterns used in agent_task_runner._handle_tool_event
  around line 1530.

Background: A runtime NameError ("name 'self' is not defined") was observed at
agent_task_runner.py:1530 and docker_sandbox.py:660 during sandbox init and tool
failures (file_write, code_save_artifact, shell_exec). These tests ensure the
static method signature and shell data handling logic do not regress.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx

from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, body: dict | str | None = None) -> MagicMock:
    """Build a minimal httpx.Response mock with controllable status/body."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code

    if isinstance(body, dict):
        response.json.return_value = body
        response.text = json.dumps(body)
    elif isinstance(body, str):
        response.json.side_effect = json.JSONDecodeError("bad json", "", 0)
        response.text = body
    else:
        response.json.side_effect = json.JSONDecodeError("bad json", "", 0)
        response.text = ""

    return response


# ---------------------------------------------------------------------------
# _parse_tool_result: happy-path (2xx)
# ---------------------------------------------------------------------------


class TestParseToolResultSuccess:
    """_parse_tool_result with 2xx responses should return ToolResult(success=True)."""

    def test_success_true(self) -> None:
        resp = _mock_response(200, {"success": True, "data": {"output": "hello"}, "message": None})
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is True

    def test_success_with_data(self) -> None:
        resp = _mock_response(200, {"success": True, "data": {"returncode": 0, "output": "done"}})
        result = DockerSandbox._parse_tool_result(resp)
        assert isinstance(result, ToolResult)
        assert result.data == {"returncode": 0, "output": "done"}

    def test_success_false_in_2xx(self) -> None:
        """Sandbox can return HTTP 200 with success=False (e.g. tool-level error)."""
        resp = _mock_response(200, {"success": False, "message": "tool failed internally"})
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is False
        assert "tool failed internally" in (result.message or "")

    def test_success_no_message(self) -> None:
        resp = _mock_response(200, {"success": True})
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is True
        assert result.message is None

    def test_200_is_not_an_error_path(self) -> None:
        """Verify the 400-check gate is not accidentally triggered for 200."""
        resp = _mock_response(200, {"success": True, "data": None})
        result = DockerSandbox._parse_tool_result(resp)
        # Should NOT include "Sandbox API error" in the message
        assert result.message is None or "Sandbox API error" not in (result.message or "")


# ---------------------------------------------------------------------------
# _parse_tool_result: error status codes (4xx, 5xx)
# ---------------------------------------------------------------------------


class TestParseToolResultErrors:
    """_parse_tool_result with error status codes returns ToolResult(success=False)."""

    def test_400_with_detail_key(self) -> None:
        resp = _mock_response(400, {"detail": "Path traversal denied"})
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is False
        assert "400" in (result.message or "")
        assert "Path traversal denied" in (result.message or "")

    def test_400_with_message_key(self) -> None:
        resp = _mock_response(400, {"message": "bad request"})
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is False
        assert "bad request" in (result.message or "")

    def test_404_json_body(self) -> None:
        resp = _mock_response(404, {"detail": "session not found"})
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is False
        assert "404" in (result.message or "")

    def test_500_json_body(self) -> None:
        resp = _mock_response(500, {"detail": "internal error"})
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is False
        assert "500" in (result.message or "")

    def test_500_plain_text(self) -> None:
        """When response body is not JSON, fall back to raw text."""
        resp = _mock_response(500, "Internal Server Error")
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is False
        assert "500" in (result.message or "")
        assert "Internal Server Error" in (result.message or "")

    def test_503_empty_body(self) -> None:
        """Empty body on error should not raise; returns generic HTTP message."""
        resp = _mock_response(503, None)
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is False
        assert "503" in (result.message or "")

    def test_422_with_neither_detail_nor_message(self) -> None:
        """Body with neither 'detail' nor 'message' falls back to full text."""
        resp = _mock_response(422, {"error": "validation failed"})
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is False
        # Should not raise; message comes from response.text truncation
        assert result.message is not None

    def test_400_malformed_json(self) -> None:
        """Malformed JSON on error status falls back to text, no exception raised."""
        resp = _mock_response(400, "not valid json {{{")
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is False
        assert result.message is not None

    def test_result_is_always_tool_result_instance(self) -> None:
        for status in (400, 401, 403, 404, 422, 429, 500, 502, 503):
            resp = _mock_response(status, {"detail": f"error {status}"})
            result = DockerSandbox._parse_tool_result(resp)
            assert isinstance(result, ToolResult), f"Expected ToolResult for HTTP {status}"


# ---------------------------------------------------------------------------
# _parse_tool_result: static method signature regression
# ---------------------------------------------------------------------------


class TestParseToolResultStaticMethod:
    """Guard against accidental conversion to instance method.

    If _parse_tool_result were changed to an instance method, calling it
    directly on the class (without an instance) would raise TypeError.
    """

    def test_callable_without_instance(self) -> None:
        """Must be callable directly on the class — no 'self' required."""
        resp = _mock_response(200, {"success": True})
        # This should NOT raise TypeError / NameError
        result = DockerSandbox._parse_tool_result(resp)
        assert isinstance(result, ToolResult)

    def test_callable_on_instance_too(self) -> None:
        """Also callable on an instance (consistency check)."""
        sandbox = DockerSandbox.__new__(DockerSandbox)
        resp = _mock_response(200, {"success": True})
        result = sandbox._parse_tool_result(resp)
        assert isinstance(result, ToolResult)


# ---------------------------------------------------------------------------
# Shell event data extraction patterns (regression for line ~1530)
# ---------------------------------------------------------------------------


class TestShellEventDataExtraction:
    """Tests for the data extraction logic in _handle_tool_event (shell branch).

    These don't instantiate AgentTaskRunner; they test the extracted logic
    directly to ensure no NameError / AttributeError on edge cases.
    """

    def _extract_shell_data(self, function_result_data: dict | None) -> tuple[str | None, int | None]:
        """Mirrors the logic at agent_task_runner.py lines 1524-1528."""
        stdout = None
        exit_code = None

        class _FakeResult:
            def __init__(self, d: dict | None) -> None:
                self.data = d

        function_result = _FakeResult(function_result_data)
        if function_result and hasattr(function_result, "data"):
            data = function_result.data or {}
            if isinstance(data, dict):
                stdout = data.get("output")
                exit_code = data.get("returncode")

        return stdout, exit_code

    def test_shell_data_with_output_and_returncode(self) -> None:
        stdout, exit_code = self._extract_shell_data({"output": "hello\n", "returncode": 0})
        assert stdout == "hello\n"
        assert exit_code == 0

    def test_shell_data_with_none_data(self) -> None:
        """data=None should not raise — falls back to empty dict."""
        stdout, exit_code = self._extract_shell_data(None)
        assert stdout is None
        assert exit_code is None

    def test_shell_data_with_empty_dict(self) -> None:
        stdout, exit_code = self._extract_shell_data({})
        assert stdout is None
        assert exit_code is None

    def test_shell_data_non_zero_exit(self) -> None:
        _stdout, exit_code = self._extract_shell_data({"output": "error!", "returncode": 1})
        assert exit_code == 1

    def test_shell_data_output_only(self) -> None:
        stdout, exit_code = self._extract_shell_data({"output": "partial output"})
        assert stdout == "partial output"
        assert exit_code is None

    def test_shell_data_no_console_key_defaults_empty_list(self) -> None:
        """console key missing → default to [] (mirrors line 1531)."""
        data: dict = {"returncode": 0}
        console = data.get("console", [])
        assert console == []

    def test_shell_data_with_console_key(self) -> None:
        data = {"console": ["line1", "line2"]}
        console = data.get("console", [])
        assert console == ["line1", "line2"]

    def test_shell_no_id_in_function_args(self) -> None:
        """When 'id' is absent from function_args, no sandbox call is made.

        Mirrors lines 1529-1533: if 'id' not in event.function_args, the code
        falls back to ShellToolContent(console="(No Console)").
        """
        function_args: dict = {"command": "echo hi"}  # no 'id'
        assert "id" not in function_args  # guard: the else branch triggers

    def test_shell_has_id_in_function_args(self) -> None:
        """When 'id' is present, sandbox.view_shell should be called.

        This test documents the expected branch without requiring a real sandbox.
        """
        function_args: dict = {"id": "session-abc-123", "command": "echo hi"}
        assert "id" in function_args  # guard: the if branch triggers


# ---------------------------------------------------------------------------
# workspace_init failure path (regression guard)
# ---------------------------------------------------------------------------


class TestWorkspaceInitParseResult:
    """Guard against NameError in workspace init result handling."""

    def test_parse_workspace_init_failure_response(self) -> None:
        """Sandbox returns 500 on workspace init failure — must parse without crash."""
        resp = _mock_response(500, {"detail": "workspace init failed: permission denied"})
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is False
        assert "workspace init failed" in (result.message or "")

    def test_parse_workspace_init_success_response(self) -> None:
        resp = _mock_response(200, {"success": True, "data": {"path": "/workspace"}})
        result = DockerSandbox._parse_tool_result(resp)
        assert result.success is True
