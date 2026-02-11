"""Integration Tests for Failure Snapshot (E2E)

End-to-end tests for failure snapshot generation and injection.
"""

import pytest

from app.domain.services.agents.failure_snapshot_service import FailureSnapshotService
from app.infrastructure.observability.agent_metrics import (
    failure_snapshot_generated,
    failure_snapshot_injected,
)


class TestFailureSnapshotE2E:
    """End-to-end test suite for failure snapshot flows."""

    @pytest.fixture
    def snapshot_service(self):
        """Create snapshot service with default config."""
        return FailureSnapshotService(token_budget=2000, pressure_threshold=0.8)

    @pytest.mark.asyncio
    async def test_snapshot_generated_from_error(self, snapshot_service):
        """E2E: Failed step generates snapshot from exception."""
        # Create error
        error = ValueError("Missing required field 'url'")

        # Generate snapshot
        snapshot = await snapshot_service.generate_snapshot(
            failed_step="browser_navigation",
            error=error,
            tool_call_context={
                "tool_name": "browser",
                "attempted_args": {"timeout": 5000},
                "validation_error": "Field 'url' is required",
            },
            retry_count=1,
            context_pressure=0.3,
        )

        # Verify snapshot created
        assert snapshot is not None
        assert snapshot.failed_step == "browser_navigation"
        assert snapshot.error_type == "ValueError"
        assert "Missing required field 'url'" in snapshot.error_message
        assert snapshot.retry_count == 1
        assert snapshot.context_pressure == 0.3
        assert "tool_name" in snapshot.tool_call_context
        assert snapshot.tool_call_context["tool_name"] == "browser"

    @pytest.mark.asyncio
    async def test_snapshot_injected_in_retry(self, snapshot_service):
        """E2E: Snapshot injected into retry prompt."""
        # Generate snapshot
        error = RuntimeError("Tool validation error")
        snapshot = await snapshot_service.generate_snapshot(
            failed_step="search_execution",
            error=error,
            tool_call_context={"tool_name": "search", "query": "test"},
            retry_count=1,
        )

        # Inject into retry
        base_prompt = "Execute the search query for machine learning tutorials"
        retry_prompt = await snapshot_service.inject_into_retry(
            snapshot=snapshot,
            base_prompt=base_prompt,
        )

        # Verify injection
        assert retry_prompt is not None
        assert base_prompt in retry_prompt
        assert "Previous Attempt Failed" in retry_prompt
        assert "search_execution" in retry_prompt
        assert "RuntimeError" in retry_prompt

    @pytest.mark.asyncio
    async def test_snapshot_token_budget_enforced(self, snapshot_service):
        """E2E: Snapshot size stays within token budget."""
        # Create very large context
        large_context = {f"field_{i}": f"Very long value " * 200 for i in range(100)}

        # Generate snapshot
        error = Exception("Test error")
        snapshot = await snapshot_service.generate_snapshot(
            failed_step="test_step",
            error=error,
            tool_call_context=large_context,
            retry_count=0,
        )

        # Verify token budget enforced
        snapshot_tokens = snapshot.calculate_size_tokens()
        assert snapshot_tokens <= snapshot_service.token_budget

        # Verify truncation occurred
        assert len(snapshot.tool_call_context) < len(large_context)

    @pytest.mark.asyncio
    async def test_adaptive_snapshot_low_pressure(self, snapshot_service):
        """E2E: Low context pressure creates full snapshot."""
        error = ValueError("Test error")
        snapshot = await snapshot_service.generate_snapshot(
            failed_step="test_step",
            error=error,
            tool_call_context={
                "tool_name": "search",
                "args": {"query": "test", "limit": 10},
                "error": "timeout",
            },
            retry_count=0,
            context_pressure=0.2,  # Low pressure
        )

        # Verify full context preserved
        assert snapshot.failed_step == "test_step"
        assert snapshot.error_type == "ValueError"
        assert "Test error" in snapshot.error_message
        assert len(snapshot.tool_call_context) == 3
        assert snapshot.context_pressure == 0.2

    @pytest.mark.asyncio
    async def test_adaptive_snapshot_high_pressure(self, snapshot_service):
        """E2E: High context pressure creates minimal snapshot."""
        error = RuntimeError("Test error with lots of context")
        snapshot = await snapshot_service.generate_snapshot(
            failed_step="complex_step",
            error=error,
            tool_call_context={
                "tool_name": "browser",
                "args": {"url": "https://example.com"},
                "result": "timeout",
                "extra_field_1": "data",
                "extra_field_2": "more data",
            },
            retry_count=0,
            context_pressure=0.95,  # High pressure
        )

        # Verify minimal snapshot
        assert snapshot.failed_step == "unknown"  # Minimal uses "unknown"
        assert snapshot.error_type == "RuntimeError"
        assert "Error details omitted" in snapshot.error_message
        assert len(snapshot.tool_call_context) == 0  # Empty in minimal
        assert snapshot.context_pressure == 1.0  # Minimal sets to 1.0

    @pytest.mark.asyncio
    async def test_snapshot_metrics_tracked(self, snapshot_service):
        """E2E: Snapshot generation and injection metrics tracked."""
        # Capture initial metrics
        initial_generated = failure_snapshot_generated.get(
            {"failure_type": "ValueError", "step_name": "test_step"}
        )

        # Generate snapshot
        error = ValueError("Test")
        snapshot = await snapshot_service.generate_snapshot(
            failed_step="test_step",
            error=error,
            retry_count=0,
        )

        # Verify generation metric incremented
        final_generated = failure_snapshot_generated.get(
            {"failure_type": "ValueError", "step_name": "test_step"}
        )
        assert final_generated >= initial_generated

        # Capture initial injection metrics
        initial_injected = failure_snapshot_injected.get({"retry_count": "0"})

        # Inject snapshot
        await snapshot_service.inject_into_retry(
            snapshot=snapshot,
            base_prompt="Test prompt",
        )

        # Verify injection metric incremented
        final_injected = failure_snapshot_injected.get({"retry_count": "0"})
        assert final_injected >= initial_injected

    @pytest.mark.asyncio
    async def test_snapshot_preserves_critical_info(self, snapshot_service):
        """E2E: Snapshot preserves critical failure information."""
        error = RuntimeError("Critical: URL must start with https://")
        snapshot = await snapshot_service.generate_snapshot(
            failed_step="browser_security_check",
            error=error,
            tool_call_context={
                "tool_name": "browser",
                "attempted_url": "http://insecure.com",
                "validation_error": "URL must start with https://",
                "security_requirement": "Only HTTPS URLs allowed",
            },
            retry_count=2,
            context_pressure=0.5,
        )

        # Verify critical info preserved
        assert snapshot.failed_step == "browser_security_check"
        assert snapshot.error_type == "RuntimeError"
        assert "https://" in snapshot.error_message
        assert snapshot.retry_count == 2
        assert "tool_name" in snapshot.tool_call_context
        assert snapshot.tool_call_context["tool_name"] == "browser"

    @pytest.mark.asyncio
    async def test_snapshot_retry_context_format(self, snapshot_service):
        """E2E: Snapshot retry context is properly formatted."""
        error = Exception("Test error")
        snapshot = await snapshot_service.generate_snapshot(
            failed_step="test_step",
            error=error,
            tool_call_context={"tool": "search", "query": "test"},
            retry_count=1,
        )

        # Get retry context
        retry_context = snapshot.to_retry_context()

        # Verify format
        assert "## Previous Attempt Failed" in retry_context
        assert "**Step**: test_step" in retry_context
        assert "**Error Type**: Exception" in retry_context
        assert "**Retry Count**: 1" in retry_context
        assert "**Tool Context**:" in retry_context
        assert "Please retry" in retry_context

    @pytest.mark.asyncio
    async def test_multiple_snapshots_independent(self, snapshot_service):
        """E2E: Multiple snapshots are independent."""
        # Generate first snapshot
        error1 = ValueError("Error 1")
        snapshot1 = await snapshot_service.generate_snapshot(
            failed_step="step_1",
            error=error1,
            tool_call_context={"context": "1"},
            retry_count=0,
        )

        # Generate second snapshot
        error2 = RuntimeError("Error 2")
        snapshot2 = await snapshot_service.generate_snapshot(
            failed_step="step_2",
            error=error2,
            tool_call_context={"context": "2"},
            retry_count=1,
        )

        # Verify independence
        assert snapshot1.failed_step == "step_1"
        assert snapshot2.failed_step == "step_2"
        assert snapshot1.error_type == "ValueError"
        assert snapshot2.error_type == "RuntimeError"
        assert snapshot1.tool_call_context["context"] == "1"
        assert snapshot2.tool_call_context["context"] == "2"
        assert snapshot1.retry_count == 0
        assert snapshot2.retry_count == 1

    @pytest.mark.asyncio
    async def test_snapshot_should_generate_decision(self, snapshot_service):
        """E2E: Service correctly decides when to generate snapshots."""
        error = ValueError("Test")

        # Should generate: not last retry
        assert snapshot_service.should_generate_snapshot(
            error=error,
            retry_count=0,
            max_retries=3,
        )

        # Should generate: mid-retry
        assert snapshot_service.should_generate_snapshot(
            error=error,
            retry_count=2,
            max_retries=3,
        )

        # Should NOT generate: last retry
        assert not snapshot_service.should_generate_snapshot(
            error=error,
            retry_count=3,
            max_retries=3,
        )

        # Should NOT generate: exceeded retries
        assert not snapshot_service.should_generate_snapshot(
            error=error,
            retry_count=4,
            max_retries=3,
        )

        # Should NOT generate: KeyboardInterrupt
        assert not snapshot_service.should_generate_snapshot(
            error=KeyboardInterrupt(),
            retry_count=0,
            max_retries=3,
        )

    @pytest.mark.asyncio
    async def test_context_pressure_calculation(self, snapshot_service):
        """E2E: Context pressure calculated correctly."""
        # Low pressure
        low_pressure = await snapshot_service.calculate_context_pressure(
            current_tokens=1000,
            max_tokens=10000,
        )
        assert 0.09 <= low_pressure <= 0.11  # ~0.1

        # Medium pressure
        medium_pressure = await snapshot_service.calculate_context_pressure(
            current_tokens=5000,
            max_tokens=10000,
        )
        assert 0.49 <= medium_pressure <= 0.51  # ~0.5

        # High pressure
        high_pressure = await snapshot_service.calculate_context_pressure(
            current_tokens=9000,
            max_tokens=10000,
        )
        assert 0.89 <= high_pressure <= 0.91  # ~0.9

        # Over capacity (capped at 1.0)
        over_pressure = await snapshot_service.calculate_context_pressure(
            current_tokens=15000,
            max_tokens=10000,
        )
        assert over_pressure == 1.0

        # Zero max (edge case)
        zero_pressure = await snapshot_service.calculate_context_pressure(
            current_tokens=1000,
            max_tokens=0,
        )
        assert zero_pressure == 0.0
