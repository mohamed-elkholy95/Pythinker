"""Tests for recovery domain models.

Covers RecoveryReason, RecoveryStrategy enums, RecoveryDecision,
RecoveryAttempt, RecoveryBudgetExhaustedError, MalformedResponseError.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.models.recovery import (
    MalformedResponseError,
    RecoveryAttempt,
    RecoveryBudgetExhaustedError,
    RecoveryDecision,
    RecoveryReason,
    RecoveryStrategy,
)


class TestRecoveryReason:
    def test_json_parsing_failed(self):
        assert RecoveryReason.JSON_PARSING_FAILED == "json_parsing_failed"

    def test_refusal_detected(self):
        assert RecoveryReason.REFUSAL_DETECTED == "refusal_detected"

    def test_empty_response(self):
        assert RecoveryReason.EMPTY_RESPONSE == "empty_response"

    def test_null_response(self):
        assert RecoveryReason.NULL_RESPONSE == "null_response"

    def test_malformed_tool_call(self):
        assert RecoveryReason.MALFORMED_TOOL_CALL == "malformed_tool_call"

    def test_validation_error(self):
        assert RecoveryReason.VALIDATION_ERROR == "validation_error"

    def test_member_count(self):
        assert len(RecoveryReason) == 6


class TestRecoveryStrategy:
    def test_rollback_retry(self):
        assert RecoveryStrategy.ROLLBACK_RETRY == "rollback_retry"

    def test_simplified_prompt(self):
        assert RecoveryStrategy.SIMPLIFIED_PROMPT == "simplified_prompt"

    def test_fallback_response(self):
        assert RecoveryStrategy.FALLBACK_RESPONSE == "fallback_response"

    def test_terminal_error(self):
        assert RecoveryStrategy.TERMINAL_ERROR == "terminal_error"

    def test_member_count(self):
        assert len(RecoveryStrategy) == 4


class TestRecoveryDecision:
    def test_construction(self):
        d = RecoveryDecision(
            should_recover=True,
            recovery_reason=RecoveryReason.JSON_PARSING_FAILED,
            strategy=RecoveryStrategy.ROLLBACK_RETRY,
            retry_count=1,
            message="Retrying with rollback",
        )
        assert d.should_recover is True
        assert d.retry_count == 1

    def test_negative_retry_count_rejected(self):
        with pytest.raises(ValidationError):
            RecoveryDecision(
                should_recover=False,
                recovery_reason=RecoveryReason.EMPTY_RESPONSE,
                strategy=RecoveryStrategy.TERMINAL_ERROR,
                retry_count=-1,
                message="fail",
            )


class TestRecoveryAttempt:
    def test_construction(self):
        now = datetime.now(UTC)
        a = RecoveryAttempt(
            attempt_number=1,
            recovery_reason=RecoveryReason.REFUSAL_DETECTED,
            strategy_used=RecoveryStrategy.SIMPLIFIED_PROMPT,
            start_time=now,
        )
        assert a.attempt_number == 1
        assert a.end_time is None
        assert a.success is None

    def test_completed_attempt(self):
        now = datetime.now(UTC)
        a = RecoveryAttempt(
            attempt_number=2,
            recovery_reason=RecoveryReason.EMPTY_RESPONSE,
            strategy_used=RecoveryStrategy.FALLBACK_RESPONSE,
            start_time=now,
            end_time=now,
            success=True,
        )
        assert a.success is True

    def test_failed_attempt(self):
        now = datetime.now(UTC)
        a = RecoveryAttempt(
            attempt_number=3,
            recovery_reason=RecoveryReason.VALIDATION_ERROR,
            strategy_used=RecoveryStrategy.ROLLBACK_RETRY,
            start_time=now,
            end_time=now,
            success=False,
            error_message="Still malformed",
        )
        assert a.success is False
        assert a.error_message == "Still malformed"

    def test_attempt_number_zero_rejected(self):
        with pytest.raises(ValidationError):
            RecoveryAttempt(
                attempt_number=0,
                recovery_reason=RecoveryReason.EMPTY_RESPONSE,
                strategy_used=RecoveryStrategy.TERMINAL_ERROR,
                start_time=datetime.now(UTC),
            )


class TestRecoveryBudgetExhaustedError:
    def test_construction(self):
        err = RecoveryBudgetExhaustedError(
            attempt_count=3,
            max_retries=3,
            recovery_reason=RecoveryReason.JSON_PARSING_FAILED,
        )
        assert err.attempt_count == 3
        assert err.max_retries == 3
        assert err.recovery_reason == RecoveryReason.JSON_PARSING_FAILED
        assert err.cooldown_seconds == 60  # default

    def test_custom_cooldown(self):
        err = RecoveryBudgetExhaustedError(
            attempt_count=5,
            max_retries=5,
            recovery_reason=RecoveryReason.REFUSAL_DETECTED,
            cooldown_seconds=120,
        )
        assert err.cooldown_seconds == 120

    def test_message_format(self):
        err = RecoveryBudgetExhaustedError(
            attempt_count=3,
            max_retries=3,
            recovery_reason=RecoveryReason.EMPTY_RESPONSE,
        )
        msg = str(err)
        assert "3 attempts" in msg
        assert "max: 3" in msg
        assert "empty_response" in msg

    def test_is_exception(self):
        err = RecoveryBudgetExhaustedError(
            attempt_count=1,
            max_retries=1,
            recovery_reason=RecoveryReason.NULL_RESPONSE,
        )
        assert isinstance(err, Exception)


class TestMalformedResponseError:
    def test_construction(self):
        err = MalformedResponseError(
            response_text="bad json {",
            detection_reason=RecoveryReason.JSON_PARSING_FAILED,
        )
        assert err.response_text == "bad json {"
        assert err.detection_reason == RecoveryReason.JSON_PARSING_FAILED
        assert err.raw_error is None

    def test_with_raw_error(self):
        raw = ValueError("bad")
        err = MalformedResponseError(
            response_text="bad",
            detection_reason=RecoveryReason.MALFORMED_TOOL_CALL,
            raw_error=raw,
        )
        assert err.raw_error is raw

    def test_message_format(self):
        err = MalformedResponseError(
            response_text="x" * 200,
            detection_reason=RecoveryReason.VALIDATION_ERROR,
        )
        msg = str(err)
        assert "validation_error" in msg
        assert len(msg) < 300  # Truncated

    def test_is_exception(self):
        err = MalformedResponseError(
            response_text="bad",
            detection_reason=RecoveryReason.NULL_RESPONSE,
        )
        assert isinstance(err, Exception)
