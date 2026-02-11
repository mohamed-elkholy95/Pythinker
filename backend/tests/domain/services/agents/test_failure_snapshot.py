"""Tests for Failure Snapshot Generation (Workstream B)

Test coverage for failure snapshot model, generation, and injection.
"""

import pytest

from app.domain.models.failure_snapshot import FailureSnapshot
from app.domain.services.agents.failure_snapshot_service import FailureSnapshotService
from app.infrastructure.observability.agent_metrics import (
    failure_snapshot_generated,
    failure_snapshot_injected,
)


class TestFailureSnapshotModel:
    """Test suite for FailureSnapshot model."""

    def test_snapshot_model_validation(self):
        """Test FailureSnapshot model validation."""
        snapshot = FailureSnapshot(
            failed_step="execute_tool",
            error_type="ToolExecutionError",
            error_message="Network timeout",
            tool_call_context={"tool": "search", "query": "test"},
            retry_count=1,
        )

        assert snapshot.failed_step == "execute_tool"
        assert snapshot.error_type == "ToolExecutionError"
        assert snapshot.retry_count == 1

    def test_error_message_truncation(self):
        """Test field_validator truncates long error messages."""
        long_message = "x" * 600  # Exceeds MAX_ERROR_MESSAGE_LENGTH (500)

        snapshot = FailureSnapshot(
            failed_step="test",
            error_type="TestError",
            error_message=long_message,
            retry_count=0,
        )

        # Should be truncated to 500 + "... [truncated]"
        assert len(snapshot.error_message) <= 520
        assert snapshot.error_message.endswith("... [truncated]")

    def test_snapshot_token_budget_enforcement(self):
        """Test model_validator enforces token budget."""
        # Create snapshot with large tool_call_context
        large_context = {
            f"key_{i}": "x" * 200
            for i in range(20)  # Very large context
        }

        snapshot = FailureSnapshot(
            failed_step="test",
            error_type="TestError",
            error_message="Test error",
            tool_call_context=large_context,
            retry_count=0,
        )

        # Token budget should be enforced (300 tokens)
        # tool_call_context should be truncated
        assert len(snapshot.tool_call_context) <= 3  # Max 3 items
        for _key, value in snapshot.tool_call_context.items():
            assert len(str(value)) <= 100  # Values truncated to 100 chars

    def test_snapshot_minimal_factory(self):
        """Test minimal snapshot factory method."""
        snapshot = FailureSnapshot.minimal(
            error_type="NetworkError",
            retry_count=2,
        )

        assert snapshot.error_type == "NetworkError"
        assert snapshot.retry_count == 2
        assert snapshot.context_pressure == 1.0
        assert snapshot.tool_call_context == {}
        assert "context pressure" in snapshot.error_message

    def test_snapshot_full_factory(self):
        """Test full snapshot factory method."""
        snapshot = FailureSnapshot.full(
            failed_step="search",
            error_type="TimeoutError",
            error_message="Request timeout",
            tool_call_context={"query": "test"},
            retry_count=1,
            context_pressure=0.5,
        )

        assert snapshot.failed_step == "search"
        assert snapshot.error_message == "Request timeout"
        assert snapshot.context_pressure == 0.5

    def test_snapshot_to_retry_context(self):
        """Test conversion to retry context string."""
        snapshot = FailureSnapshot(
            failed_step="execute_tool",
            error_type="ToolError",
            error_message="Tool failed",
            tool_call_context={"tool": "search"},
            retry_count=1,
        )

        context = snapshot.to_retry_context()

        assert "Previous Attempt Failed" in context
        assert "execute_tool" in context
        assert "ToolError" in context
        assert "Tool failed" in context
        assert "search" in context

    def test_snapshot_calculate_size_tokens(self):
        """Test token size calculation."""
        snapshot = FailureSnapshot(
            failed_step="test",
            error_type="TestError",
            error_message="Test",
            retry_count=0,
        )

        tokens = snapshot.calculate_size_tokens()
        assert tokens > 0
        assert tokens < 100  # Should be small for minimal snapshot


class TestFailureSnapshotService:
    """Test suite for FailureSnapshotService."""

    @pytest.fixture
    def snapshot_service(self):
        """Create snapshot service instance."""
        return FailureSnapshotService(token_budget=300, pressure_threshold=0.8)

    @pytest.mark.asyncio
    async def test_snapshot_generation_on_failure(self, snapshot_service):
        """Test snapshot generated from error."""
        error = ValueError("Test error message")

        snapshot = await snapshot_service.generate_snapshot(
            failed_step="test_step",
            error=error,
            tool_call_context={"tool": "search", "query": "test"},
            retry_count=1,
            context_pressure=0.5,
        )

        assert snapshot.failed_step == "test_step"
        assert snapshot.error_type == "ValueError"
        assert "Test error message" in snapshot.error_message
        assert snapshot.retry_count == 1

    @pytest.mark.asyncio
    async def test_adaptive_truncation(self, snapshot_service):
        """Test adaptive truncation under high context pressure."""
        error = RuntimeError("Test error")

        # Low pressure: full snapshot
        snapshot_low = await snapshot_service.generate_snapshot(
            failed_step="step1",
            error=error,
            tool_call_context={"key": "value"},
            retry_count=0,
            context_pressure=0.3,
        )
        assert snapshot_low.tool_call_context != {}
        assert snapshot_low.context_pressure == 0.3

        # High pressure: minimal snapshot
        snapshot_high = await snapshot_service.generate_snapshot(
            failed_step="step2",
            error=error,
            retry_count=1,
            context_pressure=0.9,
        )
        assert snapshot_high.tool_call_context == {}
        assert snapshot_high.context_pressure == 1.0

    @pytest.mark.asyncio
    async def test_snapshot_injection_in_retry(self, snapshot_service):
        """Test snapshot injected into retry context."""
        snapshot = FailureSnapshot(
            failed_step="test",
            error_type="TestError",
            error_message="Test",
            retry_count=1,
        )

        base_prompt = "Execute the task"
        enhanced = await snapshot_service.inject_into_retry(snapshot, base_prompt)

        assert "Previous Attempt Failed" in enhanced
        assert "Execute the task" in enhanced
        assert enhanced.index("Previous Attempt Failed") < enhanced.index("Execute the task")

    @pytest.mark.asyncio
    async def test_should_generate_snapshot_logic(self, snapshot_service):
        """Test snapshot generation decision logic."""
        error = ValueError("test")

        # Should generate for normal retry
        assert snapshot_service.should_generate_snapshot(error, 0, 3) is True

        # Should NOT generate for last retry
        assert snapshot_service.should_generate_snapshot(error, 3, 3) is False

        # Should NOT generate for system exceptions
        system_error = KeyboardInterrupt()
        assert snapshot_service.should_generate_snapshot(system_error, 0, 3) is False

    @pytest.mark.asyncio
    async def test_context_pressure_calculation(self, snapshot_service):
        """Test context pressure calculation."""
        # 50% pressure
        pressure = await snapshot_service.calculate_context_pressure(5000, 10000)
        assert pressure == 0.5

        # 100% pressure
        pressure = await snapshot_service.calculate_context_pressure(10000, 10000)
        assert pressure == 1.0

        # Over 100% (capped at 1.0)
        pressure = await snapshot_service.calculate_context_pressure(15000, 10000)
        assert pressure == 1.0

        # Zero max tokens (edge case)
        pressure = await snapshot_service.calculate_context_pressure(1000, 0)
        assert pressure == 0.0

    @pytest.mark.asyncio
    async def test_snapshot_metrics_tracked(self, snapshot_service):
        """Test snapshot generation metrics."""
        initial_count = failure_snapshot_generated.get({"failure_type": "ValueError", "step_name": "test_step"})

        error = ValueError("test")
        await snapshot_service.generate_snapshot(
            failed_step="test_step",
            error=error,
            retry_count=0,
        )

        final_count = failure_snapshot_generated.get({"failure_type": "ValueError", "step_name": "test_step"})
        assert final_count > initial_count

    @pytest.mark.asyncio
    async def test_injection_metrics_tracked(self, snapshot_service):
        """Test injection metrics."""
        initial_count = failure_snapshot_injected.get({"retry_count": "1"})

        snapshot = FailureSnapshot(
            failed_step="test",
            error_type="TestError",
            error_message="Test",
            retry_count=1,
        )

        await snapshot_service.inject_into_retry(snapshot, "Test prompt")

        final_count = failure_snapshot_injected.get({"retry_count": "1"})
        assert final_count > initial_count
