"""Regression tests for bounded in-memory trace retention.

These tests verify that NoOpLLMTracer and Tracer never grow their
internal trace lists beyond a fixed maximum, preventing unbounded
memory growth in long-running processes.

TDD: written BEFORE the bounded-deque implementation is in place.
"""

import pytest

from app.infrastructure.observability.llm_tracer import LLMTrace, NoOpLLMTracer
from app.infrastructure.observability.tracer import Tracer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _add_llm_traces(tracer: NoOpLLMTracer, count: int) -> None:
    """Push *count* LLM traces into the tracer."""
    for i in range(count):
        await tracer.trace_llm_call(
            name=f"call_{i}",
            model="gpt-4o-mini",
            input_messages=[{"role": "user", "content": f"msg {i}"}],
            output=f"response {i}",
            prompt_tokens=10,
            completion_tokens=5,
        )


async def _add_tool_traces(tracer: NoOpLLMTracer, count: int) -> None:
    """Push *count* tool traces into the tracer."""
    for i in range(count):
        await tracer.trace_tool_call(
            tool_name="search",
            function_name=f"fn_{i}",
            arguments={"q": f"query {i}"},
            result=f"result {i}",
        )


def _add_completed_traces(tracer: Tracer, count: int) -> None:
    """Drive *count* traces through the Tracer context manager so they land in
    _completed_traces."""
    for i in range(count):
        with tracer.trace(f"trace_{i}", agent_id="agent-test"):
            pass  # root span ends immediately


# ---------------------------------------------------------------------------
# NoOpLLMTracer — LLM trace retention
# ---------------------------------------------------------------------------


class TestNoOpLLMTracerRetention:
    """Verify that LLM trace history stays within its configured limit."""

    @pytest.mark.asyncio
    async def test_llm_traces_do_not_exceed_max_history(self) -> None:
        """Adding 200 traces when max is 100 must not retain more than 100."""
        tracer = NoOpLLMTracer(max_history=100)
        await _add_llm_traces(tracer, 200)

        assert len(tracer._traces) <= 100, (
            f"Expected at most 100 LLM traces, got {len(tracer._traces)}"
        )

    @pytest.mark.asyncio
    async def test_llm_traces_exactly_at_limit(self) -> None:
        """Adding exactly max_history traces should keep all of them."""
        tracer = NoOpLLMTracer(max_history=50)
        await _add_llm_traces(tracer, 50)

        assert len(tracer._traces) == 50

    @pytest.mark.asyncio
    async def test_llm_traces_never_spike_above_limit(self) -> None:
        """After each individual append the count must remain at or below max."""
        tracer = NoOpLLMTracer(max_history=10)
        for i in range(30):
            await tracer.trace_llm_call(
                name=f"call_{i}",
                model="gpt-4o-mini",
                input_messages=[],
                output="",
            )
            assert len(tracer._traces) <= 10, (
                f"Trace list spiked to {len(tracer._traces)} after insert {i}"
            )

    @pytest.mark.asyncio
    async def test_oldest_llm_traces_are_dropped(self) -> None:
        """When capacity is full, the oldest traces must be evicted first."""
        tracer = NoOpLLMTracer(max_history=5)
        for i in range(10):
            await tracer.trace_llm_call(
                name=f"call_{i}",
                model="gpt-4o-mini",
                input_messages=[],
                output=f"out_{i}",
            )

        # Only the 5 most-recent should survive
        retained_names = {t.name for t in tracer._traces}
        for expected in [f"call_{i}" for i in range(5, 10)]:
            assert expected in retained_names, (
                f"Recent trace '{expected}' was evicted; retained: {retained_names}"
            )

    # ------------------------------------------------------------------
    # Tool-trace retention
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_tool_traces_do_not_exceed_max_history(self) -> None:
        """Adding 200 tool traces when max is 100 must not retain more than 100."""
        tracer = NoOpLLMTracer(max_history=100)
        await _add_tool_traces(tracer, 200)

        assert len(tracer._tool_traces) <= 100, (
            f"Expected at most 100 tool traces, got {len(tracer._tool_traces)}"
        )

    @pytest.mark.asyncio
    async def test_tool_traces_never_spike_above_limit(self) -> None:
        """After each individual append the tool-trace count must stay at or below max."""
        tracer = NoOpLLMTracer(max_history=10)
        for i in range(30):
            await tracer.trace_tool_call(
                tool_name="search",
                function_name=f"fn_{i}",
                arguments={},
                result="",
            )
            assert len(tracer._tool_traces) <= 10, (
                f"Tool-trace list spiked to {len(tracer._tool_traces)} after insert {i}"
            )

    # ------------------------------------------------------------------
    # Default limit sanity check
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_default_max_history_is_bounded(self) -> None:
        """The default NoOpLLMTracer must have a finite max_history."""
        tracer = NoOpLLMTracer()
        assert hasattr(tracer, "_max_history"), "NoOpLLMTracer must expose _max_history"
        assert isinstance(tracer._max_history, int), "_max_history must be an int"
        assert tracer._max_history > 0, "_max_history must be positive"
        assert tracer._max_history <= 1000, (
            f"Default _max_history={tracer._max_history} is too large; "
            "consider capping at 1000 or less"
        )

    # ------------------------------------------------------------------
    # Constructor accepts max_history
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_constructor_accepts_max_history_param(self) -> None:
        """NoOpLLMTracer must accept max_history as a constructor parameter."""
        tracer = NoOpLLMTracer(max_history=42)
        assert tracer._max_history == 42


# ---------------------------------------------------------------------------
# Tracer — completed-trace retention
# ---------------------------------------------------------------------------


class TestTracerCompletedRetention:
    """Verify that general Tracer._completed_traces stays within its configured limit."""

    def test_completed_traces_do_not_exceed_limit(self) -> None:
        """Driving 200 traces through a limit-100 Tracer keeps at most 100 completed."""
        tracer = Tracer(max_completed_traces=100, export_to_log=False)
        _add_completed_traces(tracer, 200)

        assert len(tracer._completed_traces) <= 100, (
            f"Expected at most 100 completed traces, got {len(tracer._completed_traces)}"
        )

    def test_completed_traces_never_spike_above_limit(self) -> None:
        """After each individual trace completion the list must stay at or below max."""
        tracer = Tracer(max_completed_traces=10, export_to_log=False)
        for i in range(30):
            with tracer.trace(f"trace_{i}"):
                pass
            assert len(tracer._completed_traces) <= 10, (
                f"Completed-trace list spiked to {len(tracer._completed_traces)} "
                f"after trace {i}"
            )

    def test_oldest_completed_traces_are_dropped(self) -> None:
        """When the completed-trace buffer is full the oldest entries are evicted."""
        tracer = Tracer(max_completed_traces=5, export_to_log=False)
        for i in range(10):
            with tracer.trace(f"trace_{i}"):
                pass

        retained_names = {tc.root_span.name for tc in tracer._completed_traces}
        for expected in [f"trace_{i}" for i in range(5, 10)]:
            assert expected in retained_names, (
                f"Recent trace '{expected}' was evicted; retained: {retained_names}"
            )

    def test_constructor_accepts_max_completed_traces(self) -> None:
        """Tracer must accept max_completed_traces as a constructor parameter."""
        tracer = Tracer(max_completed_traces=77, export_to_log=False)
        assert tracer._max_completed_traces == 77

    def test_default_max_completed_traces_is_bounded(self) -> None:
        """The default Tracer must have a finite and reasonable max_completed_traces."""
        tracer = Tracer(export_to_log=False)
        assert hasattr(tracer, "_max_completed_traces"), (
            "Tracer must expose _max_completed_traces"
        )
        assert isinstance(tracer._max_completed_traces, int)
        assert 0 < tracer._max_completed_traces <= 500

    # ------------------------------------------------------------------
    # Public API: get_all_metrics still works after pruning
    # ------------------------------------------------------------------

    def test_get_all_metrics_works_after_pruning(self) -> None:
        """get_all_metrics() must not raise after the completed-trace buffer wraps."""
        tracer = Tracer(max_completed_traces=10, export_to_log=False)
        _add_completed_traces(tracer, 50)

        result = tracer.get_all_metrics()
        assert "completed_traces" in result
        assert result["completed_traces"] <= 10


# ---------------------------------------------------------------------------
# metrics_routes — public accessor (no direct _traces access)
# ---------------------------------------------------------------------------


class TestMetricsRoutesPublicAccess:
    """Verify that the timeline endpoint iterates traces via a public method."""

    @pytest.mark.asyncio
    async def test_get_traces_public_method_exists(self) -> None:
        """NoOpLLMTracer must expose a public get_traces() method so metrics
        routes don't need to reach into _traces directly."""
        tracer = NoOpLLMTracer(max_history=20)
        await _add_llm_traces(tracer, 5)

        assert hasattr(tracer, "get_traces"), (
            "NoOpLLMTracer must expose get_traces() for metrics routes"
        )
        traces = tracer.get_traces()
        assert len(traces) == 5
        assert all(isinstance(t, LLMTrace) for t in traces)

    @pytest.mark.asyncio
    async def test_get_traces_respects_retention_limit(self) -> None:
        """get_traces() must return at most max_history items."""
        tracer = NoOpLLMTracer(max_history=10)
        await _add_llm_traces(tracer, 25)

        traces = tracer.get_traces()
        assert len(traces) <= 10
