"""Tests for standardized tool call envelope."""

from app.domain.models.tool_call import ToolCallEnvelope, ToolCallStatus


def test_tool_call_envelope_creation():
    """ToolCallEnvelope captures tool call metadata."""
    envelope = ToolCallEnvelope(
        tool_call_id="tc-001",
        tool_name="browser",
        function_name="browser_navigate",
        arguments={"url": "https://example.com"},
    )
    assert envelope.status == ToolCallStatus.PENDING
    assert envelope.tool_call_id == "tc-001"
    assert envelope.duration_ms is None


def test_tool_call_envelope_mark_started():
    """mark_started transitions to RUNNING."""
    envelope = ToolCallEnvelope(
        tool_call_id="tc-001",
        tool_name="shell",
        function_name="shell_exec",
        arguments={"command": "ls"},
    )
    envelope.mark_started()
    assert envelope.status == ToolCallStatus.RUNNING
    assert envelope.started_at is not None


def test_tool_call_envelope_mark_completed():
    """mark_completed captures duration and result."""
    envelope = ToolCallEnvelope(
        tool_call_id="tc-001",
        tool_name="file",
        function_name="file_read",
        arguments={"path": "/workspace/test.py"},
    )
    envelope.mark_started()
    envelope.mark_completed(success=True, message="File read successfully")
    assert envelope.status == ToolCallStatus.COMPLETED
    assert envelope.duration_ms is not None
    assert envelope.duration_ms >= 0
    assert envelope.success is True


def test_tool_call_envelope_mark_failed():
    """mark_failed captures error info."""
    envelope = ToolCallEnvelope(
        tool_call_id="tc-001",
        tool_name="shell",
        function_name="shell_exec",
        arguments={"command": "rm -rf /"},
    )
    envelope.mark_started()
    envelope.mark_failed(error="Command blocked by security")
    assert envelope.status == ToolCallStatus.FAILED
    assert envelope.error == "Command blocked by security"
    assert envelope.success is False


def test_tool_call_envelope_mark_blocked():
    """mark_blocked transitions to BLOCKED."""
    envelope = ToolCallEnvelope(
        tool_call_id="tc-001",
        tool_name="shell",
        function_name="shell_exec",
        arguments={"command": "dangerous"},
    )
    envelope.mark_blocked(reason="Security policy violation")
    assert envelope.status == ToolCallStatus.BLOCKED
    assert envelope.success is False
    assert envelope.error == "Security policy violation"


def test_tool_call_envelope_to_log_dict():
    """to_log_dict returns structured logging data."""
    envelope = ToolCallEnvelope(
        tool_call_id="tc-001",
        tool_name="browser",
        function_name="browser_navigate",
    )
    envelope.mark_started()
    envelope.mark_completed(success=True, message="Page loaded")

    log_dict = envelope.to_log_dict()
    assert log_dict["tool_call_id"] == "tc-001"
    assert log_dict["tool_name"] == "browser"
    assert log_dict["function_name"] == "browser_navigate"
    assert log_dict["status"] == "completed"
    assert log_dict["success"] is True
    assert "duration_ms" in log_dict
