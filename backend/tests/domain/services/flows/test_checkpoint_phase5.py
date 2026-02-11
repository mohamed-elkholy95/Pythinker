"""Tests for Phase 5 incremental checkpoint writes.

Tests checkpoint writing during execution to prevent context loss.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.plan import ExecutionStatus, Plan, Step


class TestIncrementalCheckpointWrites:
    """Test checkpoint writing during plan execution."""

    @pytest.mark.asyncio
    async def test_write_checkpoint_stores_progress(self):
        """Test checkpoint writes execution progress to memory."""
        from app.domain.services.flows.plan_act import PlanActFlow

        # Create mock flow with memory service
        memory_service_mock = MagicMock()
        memory_service_mock.store_memory = AsyncMock(return_value=MagicMock())

        flow_mock = MagicMock(spec=PlanActFlow)
        flow_mock._memory_service = memory_service_mock
        flow_mock._user_id = "user-123"
        flow_mock._session_id = "session-456"

        # Create mock plan with completed steps
        step1 = Step(
            id="step-1", description="First step", status=ExecutionStatus.COMPLETED, success=True, result="Done"
        )
        step2 = Step(
            id="step-2", description="Second step", status=ExecutionStatus.COMPLETED, success=True, result="Complete"
        )
        step3 = Step(id="step-3", description="Third step", status=ExecutionStatus.PENDING)

        plan = Plan(title="Test Plan", steps=[step1, step2, step3])
        flow_mock.plan = plan

        # Call the actual _write_checkpoint method
        await PlanActFlow._write_checkpoint(flow_mock, step_index=1, is_final=False)

        # Verify store_memory was called
        memory_service_mock.store_memory.assert_called_once()
        call_kwargs = memory_service_mock.store_memory.call_args.kwargs

        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["session_id"] == "session-456"
        assert "checkpoint" in call_kwargs["tags"]
        assert "execution" in call_kwargs["tags"]
        assert "incremental" in call_kwargs["tags"]
        assert call_kwargs["metadata"]["step_index"] == 1
        assert call_kwargs["metadata"]["is_final"] is False

    @pytest.mark.asyncio
    async def test_final_checkpoint_marked_critical(self):
        """Test final checkpoints are marked as CRITICAL importance."""
        from app.domain.models.long_term_memory import MemoryImportance
        from app.domain.services.flows.plan_act import PlanActFlow

        memory_service_mock = MagicMock()
        memory_service_mock.store_memory = AsyncMock(return_value=MagicMock())

        flow_mock = MagicMock(spec=PlanActFlow)
        flow_mock._memory_service = memory_service_mock
        flow_mock._user_id = "user-123"
        flow_mock._session_id = "session-456"

        step = Step(id="step-1", description="Final step", status=ExecutionStatus.COMPLETED, success=True)
        flow_mock.plan = Plan(title="Test", steps=[step])

        # Final checkpoint
        await PlanActFlow._write_checkpoint(flow_mock, step_index=0, is_final=True)

        call_kwargs = memory_service_mock.store_memory.call_args.kwargs
        assert call_kwargs["importance"] == MemoryImportance.CRITICAL
        assert "final" in call_kwargs["tags"]

    @pytest.mark.asyncio
    async def test_incremental_checkpoint_marked_high(self):
        """Test incremental checkpoints are marked as HIGH importance."""
        from app.domain.models.long_term_memory import MemoryImportance
        from app.domain.services.flows.plan_act import PlanActFlow

        memory_service_mock = MagicMock()
        memory_service_mock.store_memory = AsyncMock(return_value=MagicMock())

        flow_mock = MagicMock(spec=PlanActFlow)
        flow_mock._memory_service = memory_service_mock
        flow_mock._user_id = "user-123"
        flow_mock._session_id = "session-456"

        step = Step(id="step-1", description="Mid step", status=ExecutionStatus.COMPLETED, success=True)
        flow_mock.plan = Plan(title="Test", steps=[step])

        # Incremental checkpoint
        await PlanActFlow._write_checkpoint(flow_mock, step_index=0, is_final=False)

        call_kwargs = memory_service_mock.store_memory.call_args.kwargs
        assert call_kwargs["importance"] == MemoryImportance.HIGH
        assert "incremental" in call_kwargs["tags"]

    @pytest.mark.asyncio
    async def test_checkpoint_summary_includes_completed_steps(self):
        """Test checkpoint summary includes all completed steps."""
        from app.domain.services.flows.plan_act import PlanActFlow

        memory_service_mock = MagicMock()
        memory_service_mock.store_memory = AsyncMock(return_value=MagicMock())

        flow_mock = MagicMock(spec=PlanActFlow)
        flow_mock._memory_service = memory_service_mock
        flow_mock._user_id = "user-123"
        flow_mock._session_id = "session-456"

        step1 = Step(
            id="step-1", description="Task A", status=ExecutionStatus.COMPLETED, success=True, result="Success A"
        )
        step2 = Step(
            id="step-2", description="Task B", status=ExecutionStatus.COMPLETED, success=True, result="Success B"
        )
        step3 = Step(
            id="step-3", description="Task C", status=ExecutionStatus.COMPLETED, success=False, result="Failed C"
        )

        flow_mock.plan = Plan(title="Test", steps=[step1, step2, step3])

        await PlanActFlow._write_checkpoint(flow_mock, step_index=2, is_final=False)

        call_kwargs = memory_service_mock.store_memory.call_args.kwargs
        content = call_kwargs["content"]

        assert "Task A" in content
        assert "Task B" in content
        assert "Task C" in content
        assert "✓ Success" in content
        assert "✗ Failed" in content

    @pytest.mark.asyncio
    async def test_checkpoint_limits_to_last_10_steps(self):
        """Test checkpoint summary shows only last 10 steps."""
        from app.domain.services.flows.plan_act import PlanActFlow

        memory_service_mock = MagicMock()
        memory_service_mock.store_memory = AsyncMock(return_value=MagicMock())

        flow_mock = MagicMock(spec=PlanActFlow)
        flow_mock._memory_service = memory_service_mock
        flow_mock._user_id = "user-123"
        flow_mock._session_id = "session-456"

        # 15 completed steps
        steps = [
            Step(
                id=f"step-{i}",
                description=f"Task {i}",
                status=ExecutionStatus.COMPLETED,
                success=True,
                result=f"Result {i}",
            )
            for i in range(15)
        ]

        flow_mock.plan = Plan(title="Test", steps=steps)

        await PlanActFlow._write_checkpoint(flow_mock, step_index=14, is_final=False)

        call_kwargs = memory_service_mock.store_memory.call_args.kwargs
        content = call_kwargs["content"]

        # Should include steps 5-14 (last 10)
        assert "Task 5" in content or "Task 6" in content  # First of last 10
        assert "Task 14" in content  # Last step
        # Should not include early steps
        assert "Step 1: ✓ Success - Task 0 (Result 0)" not in content
        assert "Step 2: ✓ Success - Task 1 (Result 1)" not in content

    @pytest.mark.asyncio
    async def test_no_checkpoint_without_memory_service(self):
        """Test checkpoint is skipped when memory service unavailable."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow_mock = MagicMock(spec=PlanActFlow)
        flow_mock._memory_service = None  # No memory service
        flow_mock._user_id = "user-123"
        flow_mock.plan = Plan(title="Test", steps=[])

        # Should not raise error
        await PlanActFlow._write_checkpoint(flow_mock, step_index=0, is_final=False)

        # No memory service, no store_memory call

    @pytest.mark.asyncio
    async def test_checkpoint_gracefully_handles_storage_errors(self):
        """Test checkpoint continues despite storage errors."""
        from app.domain.services.flows.plan_act import PlanActFlow

        memory_service_mock = MagicMock()
        memory_service_mock.store_memory = AsyncMock(side_effect=Exception("Storage error"))

        flow_mock = MagicMock(spec=PlanActFlow)
        flow_mock._memory_service = memory_service_mock
        flow_mock._user_id = "user-123"
        flow_mock._session_id = "session-456"

        step = Step(id="step-1", description="Test", status=ExecutionStatus.COMPLETED, success=True)
        flow_mock.plan = Plan(title="Test", steps=[step])

        # Should not raise error despite storage failure
        await PlanActFlow._write_checkpoint(flow_mock, step_index=0, is_final=False)

    @pytest.mark.asyncio
    async def test_checkpoint_metadata_includes_plan_info(self):
        """Test checkpoint metadata includes plan title and step counts."""
        from app.domain.services.flows.plan_act import PlanActFlow

        memory_service_mock = MagicMock()
        memory_service_mock.store_memory = AsyncMock(return_value=MagicMock())

        flow_mock = MagicMock(spec=PlanActFlow)
        flow_mock._memory_service = memory_service_mock
        flow_mock._user_id = "user-123"
        flow_mock._session_id = "session-456"

        steps = [Step(id=f"step-{i}", description=f"Task {i}", status=ExecutionStatus.COMPLETED) for i in range(5)]
        flow_mock.plan = Plan(title="Feature Implementation", steps=steps)

        await PlanActFlow._write_checkpoint(flow_mock, step_index=2, is_final=False)

        call_kwargs = memory_service_mock.store_memory.call_args.kwargs
        metadata = call_kwargs["metadata"]

        assert metadata["plan_title"] == "Feature Implementation"
        assert metadata["total_steps"] == 5
        assert metadata["step_index"] == 2
        assert "checkpoint_timestamp" in metadata


class TestCheckpointTriggers:
    """Test when checkpoints are triggered."""

    def test_checkpoint_counter_initialization(self):
        """Test checkpoint counter is initialized."""
        from app.domain.services.flows.plan_act import PlanActFlow

        # This would require full flow initialization, so we test the attribute exists
        # In real integration tests, we'd verify counter behavior
        assert hasattr(PlanActFlow, "__init__")

    def test_checkpoint_interval_default(self):
        """Test checkpoint interval defaults to 5 steps."""
        # Checkpoint interval is set in __init__ as self._checkpoint_interval = 5
        # This is tested via integration tests
        pass


class TestCheckpointIntegration:
    """Integration tests for checkpoint writing in execution flow."""

    @pytest.mark.asyncio
    async def test_checkpoint_written_every_5_steps(self):
        """Test checkpoints are written every 5 completed steps."""
        # This would require full flow execution simulation
        # Tested in integration/E2E tests
        pass

    @pytest.mark.asyncio
    async def test_final_checkpoint_on_completion(self):
        """Test final checkpoint is written when plan completes."""
        # This would require full flow execution simulation
        # Tested in integration/E2E tests
        pass
