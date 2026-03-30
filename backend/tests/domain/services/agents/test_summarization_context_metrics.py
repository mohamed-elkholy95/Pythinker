"""Tests for summarization-context metrics recording.

Verifies that ExecutionAgent.summarize() and BaseAgent.set_metrics()
emit the expected Prometheus-compatible metric calls when a real
MetricsPort is injected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.domain.models.memory import ConversationMemory

# ---------------------------------------------------------------------------
# Fake MetricsPort — records every call for assertion
# ---------------------------------------------------------------------------


@dataclass
class _MetricCall:
    """A single recorded metric call."""

    method: str
    name: str
    value: float | None = None
    labels: dict[str, str] | None = None


class _FakeMetrics:
    """In-memory MetricsPort implementation for testing."""

    def __init__(self) -> None:
        self.calls: list[_MetricCall] = []

    def record_event(self, event_type: str, labels: dict[str, str] | None = None) -> None:
        self.calls.append(_MetricCall("record_event", event_type, labels=labels))

    def increment(self, name: str, labels: dict[str, str] | None = None) -> None:
        self.calls.append(_MetricCall("increment", name, labels=labels))

    def record_counter(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        self.calls.append(_MetricCall("record_counter", name, value=value, labels=labels))

    def record_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        self.calls.append(_MetricCall("record_gauge", name, value=value, labels=labels))

    def record_histogram(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        self.calls.append(_MetricCall("record_histogram", name, value=value, labels=labels))

    def record_reward_hacking_signal(self, signal_type: str, severity: str) -> None:
        self.calls.append(_MetricCall("record_reward_hacking_signal", signal_type, labels={"severity": severity}))

    def record_plan_verification(self, status: str) -> None:
        self.calls.append(_MetricCall("record_plan_verification", status))

    def record_failure_prediction(self, prediction: str, confidence: float) -> None:
        self.calls.append(_MetricCall("record_failure_prediction", prediction, value=confidence))

    def record_error(self, error_type: str, message: str) -> None:
        self.calls.append(_MetricCall("record_error", error_type))

    def find_calls(self, method: str, name: str) -> list[_MetricCall]:
        return [c for c in self.calls if c.method == method and c.name == name]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_agent() -> Any:
    """Create a minimal ExecutionAgent-like object for metric assertions."""
    from app.domain.services.agents.execution import ExecutionAgent

    agent = ExecutionAgent.__new__(ExecutionAgent)
    agent._user_request = "test request"
    agent._research_depth = "STANDARD"
    agent._collected_sources = []
    agent._response_policy = None
    agent._artifact_references = []
    agent._set_response_generator_artifact_references = MagicMock()
    agent.memory = ConversationMemory()
    agent.memory.add_message({"role": "system", "content": "SYSTEM"})
    return agent


# ---------------------------------------------------------------------------
# Test 1: summarize() records context presence counter
# ---------------------------------------------------------------------------


class TestSummarizeContextCounter:
    """Verify summarization_context_total counter is recorded."""

    @pytest.mark.asyncio
    async def test_counter_with_context(self) -> None:
        """When summarization_context is provided, counter labels has_context=true."""
        fake = _FakeMetrics()
        from app.domain.services.agents import execution as _mod

        _original = _mod._metrics
        _mod._metrics = fake
        try:
            agent = _make_minimal_agent()

            # Short-circuit summarize after metrics are recorded
            class _StopError(Exception):
                pass

            async def _raise(msgs: list[dict]) -> None:
                raise _StopError

            agent._add_to_memory = _raise  # type: ignore[assignment]

            with pytest.raises(_StopError):
                async for _ in agent.summarize(
                    summarization_context="## Deliverables\nreport.md",
                    all_steps_completed=True,
                ):
                    pass

            calls = fake.find_calls("record_counter", "pythinker_summarization_context_total")
            assert len(calls) >= 1, f"Expected at least 1 counter call, got {len(calls)}"
            assert calls[0].labels == {"has_context": "true"}
        finally:
            _mod._metrics = _original

    @pytest.mark.asyncio
    async def test_counter_without_context(self) -> None:
        """When summarization_context is None, counter labels has_context=false."""
        fake = _FakeMetrics()
        from app.domain.services.agents import execution as _mod

        _original = _mod._metrics
        _mod._metrics = fake
        try:
            agent = _make_minimal_agent()

            class _StopError(Exception):
                pass

            async def _raise(msgs: list[dict]) -> None:
                raise _StopError

            agent._add_to_memory = _raise  # type: ignore[assignment]

            with pytest.raises(_StopError):
                async for _ in agent.summarize(
                    summarization_context=None,
                    all_steps_completed=True,
                ):
                    pass

            calls = fake.find_calls("record_counter", "pythinker_summarization_context_total")
            assert len(calls) >= 1
            assert calls[0].labels == {"has_context": "false"}
        finally:
            _mod._metrics = _original


# ---------------------------------------------------------------------------
# Test 2: summarize() records context size histogram
# ---------------------------------------------------------------------------


class TestSummarizeContextSizeHistogram:
    """Verify summarization_context_size_bytes histogram is recorded."""

    @pytest.mark.asyncio
    async def test_histogram_records_size(self) -> None:
        """Histogram records the byte length of the summarization_context string."""
        fake = _FakeMetrics()
        from app.domain.services.agents import execution as _mod

        _original = _mod._metrics
        _mod._metrics = fake
        try:
            agent = _make_minimal_agent()

            class _StopError(Exception):
                pass

            async def _raise(msgs: list[dict]) -> None:
                raise _StopError

            agent._add_to_memory = _raise  # type: ignore[assignment]

            ctx = "x" * 500
            with pytest.raises(_StopError):
                async for _ in agent.summarize(
                    summarization_context=ctx,
                    all_steps_completed=True,
                ):
                    pass

            calls = fake.find_calls("record_histogram", "pythinker_summarization_context_size_bytes")
            assert len(calls) >= 1
            assert calls[0].value == 500.0
            assert calls[0].labels == {"source": "flow"}
        finally:
            _mod._metrics = _original

    @pytest.mark.asyncio
    async def test_no_histogram_when_no_context(self) -> None:
        """Histogram is NOT recorded when summarization_context is None."""
        fake = _FakeMetrics()
        from app.domain.services.agents import execution as _mod

        _original = _mod._metrics
        _mod._metrics = fake
        try:
            agent = _make_minimal_agent()

            class _StopError(Exception):
                pass

            async def _raise(msgs: list[dict]) -> None:
                raise _StopError

            agent._add_to_memory = _raise  # type: ignore[assignment]

            with pytest.raises(_StopError):
                async for _ in agent.summarize(
                    summarization_context=None,
                    all_steps_completed=True,
                ):
                    pass

            calls = fake.find_calls("record_histogram", "pythinker_summarization_context_size_bytes")
            assert len(calls) == 0, "Histogram should not be recorded when context is None"
        finally:
            _mod._metrics = _original


# ---------------------------------------------------------------------------
# Test 3: BaseAgent.set_metrics replaces _metrics
# ---------------------------------------------------------------------------


class TestBaseAgentSetMetrics:
    """Verify BaseAgent.set_metrics() injects the metrics port."""

    def test_set_metrics_replaces_null(self) -> None:
        from app.domain.external.observability import NullMetrics, get_null_metrics
        from app.domain.services.agents.base import BaseAgent

        # Minimal mock base agent
        agent = BaseAgent.__new__(BaseAgent)
        agent._metrics = get_null_metrics()
        assert isinstance(agent._metrics, NullMetrics)

        fake = _FakeMetrics()
        agent.set_metrics(fake)

        assert agent._metrics is fake, "set_metrics should replace _metrics"


# ---------------------------------------------------------------------------
# Test 4: PlanActFlow._build_summarization_context output shape
# ---------------------------------------------------------------------------


class TestBuildSummarizationContextIntegration:
    """Integration: _build_summarization_context produces content that
    would trigger the histogram metric."""

    def test_combined_context_size(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        workspace = "report.md  (1234 bytes)\nchart.png  (5678 bytes)"
        attachments = [
            {"filename": "report.md", "storage_key": "reports/report.md"},
            {"filename": "data.csv", "storage_key": "data/data.csv"},
        ]

        context = PlanActFlow._build_summarization_context(
            workspace_listing=workspace,
            attachments=attachments,
        )

        assert len(context) > 0
        # Verify workspace deliverables section present
        assert "Workspace Deliverables" in context
        assert "report.md" in context
        # Verify artifact manifest section present
        assert "Deliverables" in context
        assert "data.csv" in context
        # Verify size is meaningful (should be tracked by histogram)
        assert len(context) > 50

    def test_empty_context_when_nothing_provided(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        context = PlanActFlow._build_summarization_context(
            workspace_listing=None,
            attachments=None,
        )
        assert context == ""
