from __future__ import annotations

from app.domain.models.structured_output import (
    ErrorCategory,
    OutputTier,
    StopReason,
    StructuredContentFilterError,
    StructuredOutputResult,
    StructuredOutputStrategy,
    StructuredRefusalError,
    StructuredTruncationError,
)


def test_structured_output_exceptions_expose_stop_reason() -> None:
    refusal = StructuredRefusalError("refused")
    truncated = StructuredTruncationError("truncated")
    filtered = StructuredContentFilterError("filtered")

    assert refusal.stop_reason == StopReason.REFUSAL
    assert truncated.stop_reason == StopReason.TRUNCATED
    assert filtered.stop_reason == StopReason.CONTENT_FILTER


def test_structured_output_result_defaults() -> None:
    result = StructuredOutputResult[dict](
        parsed=None,
        strategy_used=StructuredOutputStrategy.UNSUPPORTED,
        stop_reason=StopReason.UNSUPPORTED,
        refusal_message=None,
        error_type=ErrorCategory.UNSUPPORTED,
        attempts=1,
        latency_ms=1.0,
        request_id="req-1",
        tier=OutputTier.A,
    )

    assert result.strategy_used == StructuredOutputStrategy.UNSUPPORTED
    assert result.stop_reason == StopReason.UNSUPPORTED
    assert result.tier == OutputTier.A
