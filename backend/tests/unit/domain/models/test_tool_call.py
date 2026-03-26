"""Tests for ToolCall models (app.domain.models.tool_call).

Covers ToolCallStatus enum, ToolCallEnvelope creation, status transitions
(mark_started, mark_completed, mark_failed, mark_blocked), duration
calculation, result truncation, and to_log_dict serialization.
"""

import time

from app.domain.models.tool_call import ToolCallEnvelope, ToolCallStatus

# ── ToolCallStatus ───────────────────────────────────────────────────


class TestToolCallStatus:
    """Tests for ToolCallStatus enum."""

    def test_all_values(self) -> None:
        assert ToolCallStatus.PENDING == "pending"
        assert ToolCallStatus.RUNNING == "running"
        assert ToolCallStatus.COMPLETED == "completed"
        assert ToolCallStatus.FAILED == "failed"
        assert ToolCallStatus.BLOCKED == "blocked"

    def test_is_string_enum(self) -> None:
        assert isinstance(ToolCallStatus.PENDING, str)

    def test_all_unique(self) -> None:
        values = [s.value for s in ToolCallStatus]
        assert len(values) == len(set(values))


# ── ToolCallEnvelope creation ────────────────────────────────────────


class TestToolCallEnvelopeCreation:
    """Tests for ToolCallEnvelope construction."""

    def test_minimal_creation(self) -> None:
        env = ToolCallEnvelope(
            tool_call_id="tc-1",
            tool_name="browser",
            function_name="navigate",
        )
        assert env.tool_call_id == "tc-1"
        assert env.tool_name == "browser"
        assert env.function_name == "navigate"
        assert env.arguments == {}
        assert env.status == ToolCallStatus.PENDING
        assert env.started_at is None
        assert env.completed_at is None
        assert env.duration_ms is None
        assert env.success is None
        assert env.error is None
        assert env.result_summary is None

    def test_full_creation(self) -> None:
        env = ToolCallEnvelope(
            tool_call_id="tc-2",
            tool_name="shell",
            function_name="execute",
            arguments={"command": "ls -la"},
            status=ToolCallStatus.RUNNING,
            started_at=1000.0,
        )
        assert env.arguments == {"command": "ls -la"}
        assert env.status == ToolCallStatus.RUNNING
        assert env.started_at == 1000.0


# ── Status transitions ───────────────────────────────────────────────


class TestToolCallStatusTransitions:
    """Tests for ToolCallEnvelope status transition methods."""

    def _make_envelope(self) -> ToolCallEnvelope:
        return ToolCallEnvelope(
            tool_call_id="tc-1",
            tool_name="browser",
            function_name="navigate",
        )

    def test_mark_started(self) -> None:
        env = self._make_envelope()
        before = time.time()
        env.mark_started()
        after = time.time()
        assert env.status == ToolCallStatus.RUNNING
        assert env.started_at is not None
        assert before <= env.started_at <= after

    def test_mark_completed_success(self) -> None:
        env = self._make_envelope()
        env.mark_started()
        env.mark_completed(success=True, message="Page loaded")
        assert env.status == ToolCallStatus.COMPLETED
        assert env.success is True
        assert env.completed_at is not None
        assert env.duration_ms is not None
        assert env.duration_ms >= 0
        assert env.result_summary == "Page loaded"

    def test_mark_completed_failure(self) -> None:
        env = self._make_envelope()
        env.mark_started()
        env.mark_completed(success=False, message="404 not found")
        assert env.status == ToolCallStatus.COMPLETED
        assert env.success is False
        assert env.result_summary == "404 not found"

    def test_mark_completed_no_message(self) -> None:
        env = self._make_envelope()
        env.mark_started()
        env.mark_completed(success=True)
        assert env.result_summary is None

    def test_mark_completed_truncates_long_message(self) -> None:
        env = self._make_envelope()
        env.mark_started()
        long_msg = "x" * 500
        env.mark_completed(success=True, message=long_msg)
        assert env.result_summary is not None
        assert len(env.result_summary) == 200

    def test_mark_completed_without_started(self) -> None:
        env = self._make_envelope()
        env.mark_completed(success=True)
        assert env.status == ToolCallStatus.COMPLETED
        assert env.duration_ms is None  # no started_at, so no duration

    def test_mark_failed(self) -> None:
        env = self._make_envelope()
        env.mark_started()
        env.mark_failed("Connection timeout")
        assert env.status == ToolCallStatus.FAILED
        assert env.success is False
        assert env.error == "Connection timeout"
        assert env.completed_at is not None
        assert env.duration_ms is not None
        assert env.duration_ms >= 0

    def test_mark_failed_truncates_long_error(self) -> None:
        env = self._make_envelope()
        env.mark_started()
        long_err = "e" * 1000
        env.mark_failed(long_err)
        assert env.error is not None
        assert len(env.error) == 500

    def test_mark_failed_without_started(self) -> None:
        env = self._make_envelope()
        env.mark_failed("error")
        assert env.status == ToolCallStatus.FAILED
        assert env.duration_ms is None

    def test_mark_blocked(self) -> None:
        env = self._make_envelope()
        env.mark_blocked("Security: path traversal detected")
        assert env.status == ToolCallStatus.BLOCKED
        assert env.success is False
        assert env.error == "Security: path traversal detected"

    def test_duration_calculation(self) -> None:
        env = self._make_envelope()
        env.started_at = 100.0
        env.mark_completed(success=True)
        assert env.duration_ms is not None
        # completed_at should be close to now, so duration should be > 0
        assert env.duration_ms > 0


# ── to_log_dict ──────────────────────────────────────────────────────


class TestToolCallLogDict:
    """Tests for to_log_dict serialization."""

    def test_pending_log_dict(self) -> None:
        env = ToolCallEnvelope(
            tool_call_id="tc-1",
            tool_name="browser",
            function_name="navigate",
        )
        d = env.to_log_dict()
        assert d["tool_call_id"] == "tc-1"
        assert d["tool_name"] == "browser"
        assert d["function_name"] == "navigate"
        assert d["status"] == "pending"
        assert "duration_ms" not in d
        assert "success" not in d
        assert "error" not in d

    def test_completed_log_dict(self) -> None:
        env = ToolCallEnvelope(
            tool_call_id="tc-1",
            tool_name="browser",
            function_name="navigate",
        )
        env.mark_started()
        env.mark_completed(success=True)
        d = env.to_log_dict()
        assert d["status"] == "completed"
        assert d["success"] is True
        assert "duration_ms" in d

    def test_failed_log_dict(self) -> None:
        env = ToolCallEnvelope(
            tool_call_id="tc-1",
            tool_name="shell",
            function_name="execute",
        )
        env.mark_started()
        env.mark_failed("Command failed")
        d = env.to_log_dict()
        assert d["status"] == "failed"
        assert d["success"] is False
        assert d["error"] == "Command failed"
        assert "duration_ms" in d

    def test_blocked_log_dict(self) -> None:
        env = ToolCallEnvelope(
            tool_call_id="tc-1",
            tool_name="file",
            function_name="write",
        )
        env.mark_blocked("Forbidden path")
        d = env.to_log_dict()
        assert d["status"] == "blocked"
        assert d["success"] is False
        assert d["error"] == "Forbidden path"
