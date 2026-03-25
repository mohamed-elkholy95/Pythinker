"""Tests for ToolCallEnvelope and ToolCallStatus.

Covers lifecycle transitions, timing, logging dict, and edge cases.
"""

import time

from app.domain.models.tool_call import ToolCallEnvelope, ToolCallStatus


class TestToolCallStatus:
    def test_pending(self):
        assert ToolCallStatus.PENDING == "pending"

    def test_running(self):
        assert ToolCallStatus.RUNNING == "running"

    def test_completed(self):
        assert ToolCallStatus.COMPLETED == "completed"

    def test_failed(self):
        assert ToolCallStatus.FAILED == "failed"

    def test_blocked(self):
        assert ToolCallStatus.BLOCKED == "blocked"

    def test_member_count(self):
        assert len(ToolCallStatus) == 5


class TestToolCallEnvelope:
    def _make_envelope(self, **kwargs):
        defaults = {
            "tool_call_id": "tc-1",
            "tool_name": "browser",
            "function_name": "navigate",
        }
        defaults.update(kwargs)
        return ToolCallEnvelope(**defaults)

    def test_default_status_is_pending(self):
        e = self._make_envelope()
        assert e.status == ToolCallStatus.PENDING

    def test_default_optional_fields(self):
        e = self._make_envelope()
        assert e.arguments == {}
        assert e.started_at is None
        assert e.completed_at is None
        assert e.duration_ms is None
        assert e.success is None
        assert e.error is None
        assert e.result_summary is None

    def test_mark_started(self):
        e = self._make_envelope()
        e.mark_started()
        assert e.status == ToolCallStatus.RUNNING
        assert e.started_at is not None
        assert e.started_at <= time.time()

    def test_mark_completed_success(self):
        e = self._make_envelope()
        e.mark_started()
        e.mark_completed(success=True, message="Done")
        assert e.status == ToolCallStatus.COMPLETED
        assert e.success is True
        assert e.result_summary == "Done"
        assert e.completed_at is not None
        assert e.duration_ms is not None
        assert e.duration_ms >= 0

    def test_mark_completed_failure(self):
        e = self._make_envelope()
        e.mark_started()
        e.mark_completed(success=False, message="Error occurred")
        assert e.success is False
        assert e.result_summary == "Error occurred"

    def test_mark_completed_truncates_long_message(self):
        e = self._make_envelope()
        e.mark_started()
        long_msg = "x" * 500
        e.mark_completed(success=True, message=long_msg)
        assert len(e.result_summary) == 200

    def test_mark_completed_none_message(self):
        e = self._make_envelope()
        e.mark_started()
        e.mark_completed(success=True, message=None)
        assert e.result_summary is None

    def test_mark_completed_without_start(self):
        e = self._make_envelope()
        e.mark_completed(success=True)
        assert e.status == ToolCallStatus.COMPLETED
        assert e.duration_ms is None  # No start time

    def test_mark_failed(self):
        e = self._make_envelope()
        e.mark_started()
        e.mark_failed(error="Connection timeout")
        assert e.status == ToolCallStatus.FAILED
        assert e.success is False
        assert e.error == "Connection timeout"
        assert e.duration_ms is not None

    def test_mark_failed_truncates_long_error(self):
        e = self._make_envelope()
        e.mark_failed(error="e" * 1000)
        assert len(e.error) == 500

    def test_mark_failed_without_start(self):
        e = self._make_envelope()
        e.mark_failed(error="err")
        assert e.duration_ms is None

    def test_mark_blocked(self):
        e = self._make_envelope()
        e.mark_blocked(reason="Security policy")
        assert e.status == ToolCallStatus.BLOCKED
        assert e.success is False
        assert e.error == "Security policy"

    def test_to_log_dict_minimal(self):
        e = self._make_envelope()
        d = e.to_log_dict()
        assert d["tool_call_id"] == "tc-1"
        assert d["tool_name"] == "browser"
        assert d["function_name"] == "navigate"
        assert d["status"] == "pending"
        assert "duration_ms" not in d
        assert "success" not in d
        assert "error" not in d

    def test_to_log_dict_after_completion(self):
        e = self._make_envelope()
        e.mark_started()
        e.mark_completed(success=True)
        d = e.to_log_dict()
        assert "duration_ms" in d
        assert d["success"] is True

    def test_to_log_dict_after_failure(self):
        e = self._make_envelope()
        e.mark_failed(error="timeout")
        d = e.to_log_dict()
        assert d["error"] == "timeout"
        assert d["success"] is False

    def test_arguments_field(self):
        e = self._make_envelope(arguments={"url": "https://example.com"})
        assert e.arguments["url"] == "https://example.com"
