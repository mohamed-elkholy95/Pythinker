"""Tests for tool event handler."""

from app.domain.models.event import ToolEvent, ToolStatus
from app.domain.services.tool_event_handler import ToolEventHandler


class TestToolEventHandlerActionMetadata:
    """Test tool event action metadata extraction."""

    def test_handle_shell_event_extracts_command_and_cwd(self) -> None:
        """Should extract command and cwd for shell events."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="shell",
            function_name="execute",
            function_args={"command": "ls -la", "exec_dir": "/home"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.action_type == "run"
        assert event.command == "ls -la"
        assert event.cwd == "/home"

    def test_handle_shell_event_with_missing_exec_dir(self) -> None:
        """Should handle shell event without exec_dir."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="shell",
            function_name="execute",
            function_args={"command": "pwd"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.action_type == "run"
        assert event.command == "pwd"
        assert event.cwd is None

    def test_handle_code_executor_event_with_code(self) -> None:
        """Should extract code for code_executor events."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="code_executor",
            function_name="execute",
            function_args={"code": "print('hello')"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.action_type == "run"
        assert event.command == "print('hello')"

    def test_handle_code_executor_event_with_command(self) -> None:
        """Should fall back to command if code is not present."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="code_executor",
            function_name="execute",
            function_args={"command": "python script.py"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.action_type == "run"
        assert event.command == "python script.py"

    def test_handle_file_read_event(self) -> None:
        """Should extract file path and set read action for file_read."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="file",
            function_name="file_read",
            function_args={"file": "/path/to/file.txt"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.file_path == "/path/to/file.txt"
        assert event.action_type == "read"

    def test_handle_file_write_event(self) -> None:
        """Should extract file path and set write action for file_write."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="file",
            function_name="file_write",
            function_args={"file": "/path/to/output.txt", "content": "hello"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.file_path == "/path/to/output.txt"
        assert event.action_type == "write"

    def test_handle_file_str_replace_event(self) -> None:
        """Should extract file path and set edit action for file_str_replace."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="file",
            function_name="file_str_replace",
            function_args={"file": "/path/to/file.py", "old": "foo", "new": "bar"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.file_path == "/path/to/file.py"
        assert event.action_type == "edit"

    def test_handle_file_unknown_function_defaults_to_edit(self) -> None:
        """Should default to edit action for unknown file functions."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="file",
            function_name="file_unknown",
            function_args={"file": "/path/to/file.txt"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.file_path == "/path/to/file.txt"
        assert event.action_type == "edit"

    def test_handle_browser_event(self) -> None:
        """Should set browse action for browser events."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
            function_args={"url": "https://example.com"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.action_type == "browse"

    def test_handle_browser_agent_event(self) -> None:
        """Should set browse action for browser_agent events."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="browser_agent",
            function_name="execute_task",
            function_args={"task": "Find information"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.action_type == "browse"

    def test_handle_search_event(self) -> None:
        """Should set browse action for search events."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="search",
            function_name="web_search",
            function_args={"query": "python tutorials"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.action_type == "browse"

    def test_handle_mcp_event(self) -> None:
        """Should set call_tool action for mcp events."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="mcp",
            function_name="call_tool",
            function_args={"server": "test", "tool": "some_tool"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.action_type == "call_tool"

    def test_handle_unknown_tool_no_action(self) -> None:
        """Should not set action_type for unknown tools."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="unknown_tool",
            function_name="do_something",
            function_args={},
            status=ToolStatus.CALLED,
        )

        handler.enrich_action_metadata(event)

        assert event.action_type is None


class TestToolEventHandlerObservationType:
    """Test observation type extraction for CALLED status."""

    def test_shell_observation_type(self) -> None:
        """Should set run observation type for shell."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="shell",
            function_name="execute",
            function_args={"command": "ls"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_observation_metadata(event)

        assert event.observation_type == "run"

    def test_file_observation_type(self) -> None:
        """Should set edit observation type for file."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="file",
            function_name="file_write",
            function_args={"file": "/test.txt"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_observation_metadata(event)

        assert event.observation_type == "edit"

    def test_code_executor_observation_type(self) -> None:
        """Should set run observation type for code_executor."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="code_executor",
            function_name="execute",
            function_args={"code": "print(1)"},
            status=ToolStatus.CALLED,
        )

        handler.enrich_observation_metadata(event)

        assert event.observation_type == "run"


class TestToolEventHandlerNeedsFileCache:
    """Test file cache detection for write operations."""

    def test_file_write_needs_cache(self) -> None:
        """Should detect file_write needs caching."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="file",
            function_name="file_write",
            function_args={"file": "/path/to/file.txt"},
            status=ToolStatus.CALLING,
        )

        assert handler.needs_file_cache(event) is True

    def test_file_str_replace_needs_cache(self) -> None:
        """Should detect file_str_replace needs caching."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="file",
            function_name="file_str_replace",
            function_args={"file": "/path/to/file.txt"},
            status=ToolStatus.CALLING,
        )

        assert handler.needs_file_cache(event) is True

    def test_file_read_does_not_need_cache(self) -> None:
        """Should not cache for file_read."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="file",
            function_name="file_read",
            function_args={"file": "/path/to/file.txt"},
            status=ToolStatus.CALLING,
        )

        assert handler.needs_file_cache(event) is False

    def test_shell_does_not_need_cache(self) -> None:
        """Should not cache for shell events."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="shell",
            function_name="execute",
            function_args={"command": "ls"},
            status=ToolStatus.CALLING,
        )

        assert handler.needs_file_cache(event) is False


class TestToolEventHandlerNeedsPreviewContent:
    """Test preview content detection for streaming."""

    def test_file_write_needs_preview(self) -> None:
        """Should detect file_write needs preview content."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="file",
            function_name="file_write",
            function_args={"file": "/path/to/file.txt", "content": "hello world"},
            status=ToolStatus.CALLING,
        )

        assert handler.needs_preview_content(event) is True

    def test_file_read_does_not_need_preview(self) -> None:
        """Should not need preview for file_read."""
        handler = ToolEventHandler()
        event = ToolEvent(
            tool_call_id="test-123",
            tool_name="file",
            function_name="file_read",
            function_args={"file": "/path/to/file.txt"},
            status=ToolStatus.CALLING,
        )

        assert handler.needs_preview_content(event) is False
