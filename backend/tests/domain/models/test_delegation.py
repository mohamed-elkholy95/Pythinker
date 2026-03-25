"""Tests for delegation domain models."""

import pytest

from app.domain.models.delegation import (
    DelegateRequest,
    DelegateResult,
    DelegateRole,
    DelegateStatus,
)


class TestDelegateRole:
    def test_values(self) -> None:
        expected = {"researcher", "executor", "coder", "browser", "analyst", "writer"}
        assert {r.value for r in DelegateRole} == expected


class TestDelegateStatus:
    def test_values(self) -> None:
        expected = {"started", "running", "completed", "failed", "timed_out", "rejected"}
        assert {s.value for s in DelegateStatus} == expected


class TestDelegateRequest:
    def test_defaults(self) -> None:
        r = DelegateRequest(task="Search for data", role=DelegateRole.RESEARCHER)
        assert r.timeout_seconds == 900
        assert r.max_turns == 50
        assert r.label == ""
        assert r.search_types is None

    def test_custom_values(self) -> None:
        r = DelegateRequest(
            task="Write a report",
            role=DelegateRole.WRITER,
            label="Report Task",
            timeout_seconds=300,
            max_turns=10,
        )
        assert r.role == DelegateRole.WRITER
        assert r.timeout_seconds == 300

    def test_timeout_min(self) -> None:
        with pytest.raises(ValueError):
            DelegateRequest(task="x", role=DelegateRole.CODER, timeout_seconds=10)

    def test_timeout_max(self) -> None:
        with pytest.raises(ValueError):
            DelegateRequest(task="x", role=DelegateRole.CODER, timeout_seconds=5000)


class TestDelegateResult:
    def test_success(self) -> None:
        r = DelegateResult(task_id="abc123", status=DelegateStatus.COMPLETED, result="Done!")
        assert r.error is None

    def test_failure(self) -> None:
        r = DelegateResult(status=DelegateStatus.FAILED, error="Timeout")
        assert r.task_id == ""
        assert r.result is None

    def test_rejected(self) -> None:
        r = DelegateResult(status=DelegateStatus.REJECTED, error="Max concurrency reached")
        assert r.error == "Max concurrency reached"
