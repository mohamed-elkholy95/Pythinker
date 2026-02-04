"""Tests for tracing port abstraction."""

from app.domain.external.tracing import (
    NullSpan,
    NullTracer,
    SpanKind,
    get_tracer,
    set_tracer,
)


class TestTracerPort:
    """Test TracerPort interface and implementations."""

    def test_null_tracer_start_span_returns_context_manager(self) -> None:
        """NullTracer.start_span should return a working context manager."""
        tracer = NullTracer()

        with tracer.start_span("test_span", SpanKind.INTERNAL) as span:
            assert span is not None

    def test_null_tracer_span_set_attribute_no_op(self) -> None:
        """NullTracer span should accept attributes without error."""
        tracer = NullTracer()

        with tracer.start_span("test_span", SpanKind.INTERNAL) as span:
            span.set_attribute("key", "value")  # Should not raise

    def test_null_tracer_span_record_exception_no_op(self) -> None:
        """NullTracer span should accept exceptions without error."""
        tracer = NullTracer()

        with tracer.start_span("test_span", SpanKind.INTERNAL) as span:
            span.record_exception(ValueError("test"))  # Should not raise

    def test_null_tracer_trace_returns_context_manager(self) -> None:
        """NullTracer.trace should return a working context manager."""
        tracer = NullTracer()

        with tracer.trace("test_trace", agent_id="agent-1") as trace_ctx:
            assert trace_ctx is not None

    def test_null_tracer_trace_context_has_span_method(self) -> None:
        """NullTracer trace context should support nested span creation."""
        tracer = NullTracer()

        with tracer.trace("test_trace") as trace_ctx, trace_ctx.span("nested_span", SpanKind.CLIENT) as span:
            assert span is not None
            span.set_attribute("nested.key", "nested.value")


class TestSpanKind:
    """Test SpanKind enum."""

    def test_span_kind_values(self) -> None:
        """SpanKind should have expected values."""
        assert SpanKind.INTERNAL is not None
        assert SpanKind.CLIENT is not None
        assert SpanKind.SERVER is not None

    def test_span_kind_all_values(self) -> None:
        """SpanKind should have all expected enum members."""
        # Standard OpenTelemetry kinds
        expected_kinds = {"INTERNAL", "CLIENT", "SERVER", "PRODUCER", "CONSUMER"}
        # Domain-specific span kinds for agent workflows
        expected_kinds.update(
            {"PLAN_CREATE", "PLAN_UPDATE", "AGENT_STEP", "FLOW_STATE", "LLM_CALL", "TOOL_EXECUTION", "ERROR_RECOVERY"}
        )
        actual_kinds = {kind.name for kind in SpanKind}
        assert expected_kinds == actual_kinds

    def test_span_kind_domain_specific_values(self) -> None:
        """SpanKind should have domain-specific span kinds for agent workflows."""
        assert SpanKind.PLAN_CREATE is not None
        assert SpanKind.PLAN_UPDATE is not None
        assert SpanKind.AGENT_STEP is not None
        assert SpanKind.FLOW_STATE is not None
        assert SpanKind.LLM_CALL is not None
        assert SpanKind.TOOL_EXECUTION is not None
        assert SpanKind.ERROR_RECOVERY is not None


class TestNullSpan:
    """Test NullSpan implementation."""

    def test_set_attribute_is_no_op(self) -> None:
        """set_attribute should not raise."""
        span = NullSpan()
        span.set_attribute("key", "value")
        span.set_attribute("number", 42)
        span.set_attribute("list", [1, 2, 3])

    def test_record_exception_is_no_op(self) -> None:
        """record_exception should not raise."""
        span = NullSpan()
        span.record_exception(ValueError("test error"))
        span.record_exception(RuntimeError("another error"))

    def test_set_status_is_no_op(self) -> None:
        """set_status should not raise."""
        span = NullSpan()
        span.set_status("ok")
        span.set_status("error", "Something went wrong")


class TestTracerSingleton:
    """Test tracer singleton management."""

    def test_get_tracer_returns_tracer(self) -> None:
        """get_tracer should return a TracerPort implementation."""
        tracer = get_tracer()
        assert tracer is not None

    def test_set_tracer_updates_singleton(self) -> None:
        """set_tracer should update the global tracer instance."""
        original = get_tracer()
        custom_tracer = NullTracer()
        set_tracer(custom_tracer)

        assert get_tracer() is custom_tracer

        # Restore original
        set_tracer(original)

    def test_default_tracer_is_null_tracer(self) -> None:
        """Default tracer should be a NullTracer instance."""
        # Reset to default state
        from app.domain.external import tracing

        tracing._tracer = NullTracer()

        tracer = get_tracer()
        assert isinstance(tracer, NullTracer)
