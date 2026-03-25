"""Tests for FailureSnapshot model.

Covers token budget enforcement, field validators, factory methods.
"""

import pytest
from pydantic import ValidationError

from app.domain.models.failure_snapshot import FailureSnapshot


class TestFailureSnapshot:
    def test_construction(self):
        s = FailureSnapshot(
            failed_step="step_1",
            error_type="timeout",
            error_message="Connection timed out",
            retry_count=0,
        )
        assert s.failed_step == "step_1"
        assert s.error_type == "timeout"
        assert s.retry_count == 0
        assert s.context_pressure == 0.0
        assert s.tool_call_context == {}
        assert s.timestamp is not None

    def test_error_message_truncation(self):
        long_msg = "x" * 1000
        s = FailureSnapshot(
            failed_step="s",
            error_type="e",
            error_message=long_msg,
            retry_count=0,
        )
        assert len(s.error_message) <= FailureSnapshot.MAX_ERROR_MESSAGE_LENGTH + len("... [truncated]")
        assert s.error_message.endswith("... [truncated]")

    def test_error_message_not_truncated_when_short(self):
        s = FailureSnapshot(
            failed_step="s",
            error_type="e",
            error_message="short",
            retry_count=0,
        )
        assert s.error_message == "short"

    def test_negative_retry_count_rejected(self):
        with pytest.raises(ValidationError):
            FailureSnapshot(
                failed_step="s",
                error_type="e",
                error_message="m",
                retry_count=-1,
            )

    def test_context_pressure_bounds_low(self):
        with pytest.raises(ValidationError):
            FailureSnapshot(
                failed_step="s",
                error_type="e",
                error_message="m",
                retry_count=0,
                context_pressure=-0.1,
            )

    def test_context_pressure_bounds_high(self):
        with pytest.raises(ValidationError):
            FailureSnapshot(
                failed_step="s",
                error_type="e",
                error_message="m",
                retry_count=0,
                context_pressure=1.1,
            )

    def test_token_budget_enforcement_truncates_large_context(self):
        big_context = {f"key_{i}": "v" * 200 for i in range(20)}
        s = FailureSnapshot(
            failed_step="s",
            error_type="e",
            error_message="m",
            retry_count=0,
            tool_call_context=big_context,
        )
        # After budget enforcement, context should be smaller
        assert len(s.tool_call_context) <= 3

    def test_minimal_factory(self):
        s = FailureSnapshot.minimal(error_type="timeout", retry_count=2)
        assert s.failed_step == "unknown"
        assert s.error_type == "timeout"
        assert s.retry_count == 2
        assert s.context_pressure == 1.0
        assert s.tool_call_context == {}

    def test_serialization(self):
        s = FailureSnapshot(
            failed_step="s",
            error_type="e",
            error_message="m",
            retry_count=1,
        )
        data = s.model_dump()
        s2 = FailureSnapshot.model_validate(data)
        assert s2.failed_step == s.failed_step
        assert s2.retry_count == s.retry_count
