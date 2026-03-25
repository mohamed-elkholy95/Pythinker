"""Tests for ToolCallEnvelope lifecycle and logging."""

import time

from app.domain.models.tool_call import ToolCallEnvelope, ToolCallStatus


class TestToolCallStatus:
    def test_values(self) -> None:
        expected = {"pending", "running", "completed", "failed", "blocked"}
        assert {s.value for s in ToolCallStatus} == expected


class TestToolCallEnvelope:
    def _make(self) -> ToolCallEnvelope:
        return ToolCallEnvelope(
            tool_call_id="tc-1",
            tool_name="search",
            function_name="web_search",
            arguments={"query": "test"},
        )

    def test_defaults(self) -> None:
        e = self._make()
        assert e.status == ToolCallStatus.PENDING
        assert e.started_at is None
        assert e.success is None
        assert e.error is None

    def test_mark_started(self) -> None:
        e = self._make()
        e.mark_started()
        assert e.status == ToolCallStatus.RUNNING
        assert e.started_at is not None
        assert e.started_at <= time.time()

    def test_mark_completed_success(self) -> None:
        e = self._make()
        e.mark_started()
        e.mark_completed(success=True, message="Found 5 results")
        assert e.status == ToolCallStatus.COMPLETED
        assert e.success is True
        assert e.completed_at is not None
        assert e.duration_ms is not None
        assert e.duration_ms >= 0
        assert e.result_summary == "Found 5 results"

    def test_mark_completed_truncates_message(self) -> None:
        e = self._make()
        e.mark_started()
        long_msg = "x" * 500
        e.mark_completed(success=True, message=long_msg)
        assert len(e.result_summary) == 200

    def test_mark_completed_no_message(self) -> None:
        e = self._make()
        e.mark_started()
        e.mark_completed(success=True)
        assert e.result_summary is None

    def test_mark_completed_without_started_at(self) -> None:
        e = self._make()
        e.mark_completed(success=True)
        assert e.duration_ms is None
        assert e.completed_at is not None

    def test_mark_failed(self) -> None:
        e = self._make()
        e.mark_started()
        e.mark_failed("Connection timeout")
        assert e.status == ToolCallStatus.FAILED
        assert e.success is False
        assert e.error == "Connection timeout"
        assert e.duration_ms is not None

    def test_mark_failed_truncates_error(self) -> None:
        e = self._make()
        e.mark_started()
        e.mark_failed("e" * 1000)
        assert len(e.error) == 500

    def test_mark_failed_without_started_at(self) -> None:
        e = self._make()
        e.mark_failed("boom")
        assert e.duration_ms is None

    def test_mark_blocked(self) -> None:
        e = self._make()
        e.mark_blocked("Security risk detected")
        assert e.status == ToolCallStatus.BLOCKED
        assert e.success is False
        assert e.error == "Security risk detected"

    def test_to_log_dict_minimal(self) -> None:
        e = self._make()
        d = e.to_log_dict()
        assert d["tool_call_id"] == "tc-1"
        assert d["tool_name"] == "search"
        assert d["function_name"] == "web_search"
        assert d["status"] == "pending"
        assert "duration_ms" not in d
        assert "success" not in d
        assert "error" not in d

    def test_to_log_dict_completed(self) -> None:
        e = self._make()
        e.mark_started()
        e.mark_completed(success=True, message="ok")
        d = e.to_log_dict()
        assert d["status"] == "completed"
        assert d["success"] is True
        assert "duration_ms" in d

    def test_to_log_dict_failed(self) -> None:
        e = self._make()
        e.mark_started()
        e.mark_failed("oops")
        d = e.to_log_dict()
        assert d["error"] == "oops"
        assert d["success"] is False
