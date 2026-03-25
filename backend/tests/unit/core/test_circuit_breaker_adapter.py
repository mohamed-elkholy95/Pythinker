"""Tests for tool circuit breaker adapter."""

import pytest

from app.core.circuit_breaker_registry import CircuitBreakerRegistry
from app.infrastructure.adapters.circuit_breaker_adapter import ToolCircuitBreakerAdapter


@pytest.fixture(autouse=True)
def _clean_registry():
    """Clear circuit breaker registry between tests to avoid cross-contamination."""
    yield
    # Reset all breakers after each test
    for name in list(CircuitBreakerRegistry._breakers.keys()):
        if name.startswith("tool:test_"):
            CircuitBreakerRegistry._breakers.pop(name, None)


@pytest.mark.unit
class TestToolCircuitBreakerAdapter:
    """Tests for ToolCircuitBreakerAdapter."""

    def test_can_execute_initially_true(self) -> None:
        adapter = ToolCircuitBreakerAdapter()
        assert adapter.can_execute("test_search_fresh") is True

    def test_record_success(self) -> None:
        adapter = ToolCircuitBreakerAdapter()
        adapter.record_success("test_success_tool")
        assert adapter.can_execute("test_success_tool") is True

    def test_failure_opens_circuit_due_to_failure_rate(self) -> None:
        adapter = ToolCircuitBreakerAdapter()
        # A single failure with no successes yields 100% failure rate,
        # which exceeds the default failure_rate_threshold.
        adapter.record_failure("test_rate_tool")
        assert adapter.can_execute("test_rate_tool") is False

    def test_different_tools_independent(self) -> None:
        adapter = ToolCircuitBreakerAdapter()
        adapter.record_failure("test_tool_a")
        # Other tool should still work
        assert adapter.can_execute("test_tool_b") is True

    def test_success_after_failure_closes_circuit(self) -> None:
        adapter = ToolCircuitBreakerAdapter()
        # Build up some successes first to lower the failure rate
        for _ in range(10):
            adapter.record_success("test_resilient_tool")
        # Now a single failure shouldn't trip it (failure rate = 1/11 ≈ 9%)
        adapter.record_failure("test_resilient_tool")
        assert adapter.can_execute("test_resilient_tool") is True
