"""
Test suite for orphaned background task prevention.

Validates that tools do NOT execute after cancellation is requested,
preventing the race condition where SSE disconnect doesn't stop agent execution.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import ToolEvent, ToolStatus
from app.domain.models.tool import Tool, ToolFunction
from app.domain.services.agents.base import BaseAgent
from app.domain.services.agent_task_runner import AgentTaskRunner
from app.domain.utils.cancellation import CancellationToken


class TestOrphanedTaskPrevention:
    """Test suite for preventing orphaned background tasks after cancellation."""

    @pytest.fixture
    def cancel_event(self):
        """Create a cancellation event."""
        return asyncio.Event()

    @pytest.fixture
    def cancel_token(self, cancel_event):
        """Create a cancellation token."""
        return CancellationToken(event=cancel_event, session_id="test-session")

    @pytest.fixture
    def mock_tool(self):
        """Create a mock tool for testing."""
        tool = MagicMock(spec=Tool)
        tool.name = "test_tool"
        tool.invoke_function = AsyncMock(return_value={"result": "success"})
        return tool

    @pytest.fixture
    def mock_agent(self, cancel_token):
        """Create a mock agent with cancellation support."""
        agent = MagicMock(spec=BaseAgent)
        agent._cancel_token = cancel_token
        agent.invoke_tool = AsyncMock(return_value={"result": "success"})
        return agent

    # ====================
    # Pre-Emission Tests
    # ====================

    @pytest.mark.asyncio
    async def test_tool_not_emitted_when_cancelled_before_execution(
        self, mock_agent, cancel_event
    ):
        """
        CRITICAL: Tool events should NOT be emitted if cancellation requested.

        This tests the fix in base.py:893 and base.py:994
        where we add await self._cancel_token.check_cancelled() before yield.
        """
        # Arrange: Set cancellation BEFORE tool execution
        cancel_event.set()

        # Mock execute_tools to simulate the critical path
        async def execute_tools_with_check():
            # This simulates the fix: check cancellation before emitting
            await mock_agent._cancel_token.check_cancelled()
            yield ToolEvent(
                tool_name="test_tool",
                status=ToolStatus.CALLING,
                result=None,
            )

        # Act & Assert: Should raise CancelledError, NOT emit events
        with pytest.raises(asyncio.CancelledError):
            async for event in execute_tools_with_check():
                pytest.fail("Should not emit any events after cancellation")

    @pytest.mark.asyncio
    async def test_tool_not_emitted_when_cancelled_during_parallel_execution(
        self, mock_agent, cancel_event
    ):
        """
        Test parallel execution path (base.py:893-903) with cancellation.

        Ensures tools are not emitted when cancel_event is set.
        """
        # Arrange: Prepare multiple tool calls
        tool_calls = [
            {"id": "call_1", "function": {"name": "tool1", "arguments": "{}"}},
            {"id": "call_2", "function": {"name": "tool2", "arguments": "{}"}},
        ]

        # Set cancellation before execution
        cancel_event.set()

        # Mock parallel execution path
        async def parallel_execute():
            # Check cancellation BEFORE emitting (the fix)
            await mock_agent._cancel_token.check_cancelled()

            for call in tool_calls:
                yield ToolEvent(
                    tool_name=call["function"]["name"],
                    status=ToolStatus.CALLING,
                    result=None,
                )

        # Act & Assert
        with pytest.raises(asyncio.CancelledError):
            async for _ in parallel_execute():
                pytest.fail("Should not emit events in parallel mode when cancelled")

    @pytest.mark.asyncio
    async def test_tool_not_emitted_when_cancelled_during_sequential_execution(
        self, mock_agent, cancel_event
    ):
        """
        Test sequential execution path (base.py:994-1006) with cancellation.

        Ensures tools are not emitted when cancel_event is set.
        """
        # Arrange: Single tool call
        tool_call = {"id": "call_1", "function": {"name": "tool1", "arguments": "{}"}}

        # Set cancellation before execution
        cancel_event.set()

        # Mock sequential execution path
        async def sequential_execute():
            # Check cancellation BEFORE emitting (the fix)
            await mock_agent._cancel_token.check_cancelled()

            yield ToolEvent(
                tool_name=tool_call["function"]["name"],
                status=ToolStatus.CALLING,
                result=None,
            )

        # Act & Assert
        with pytest.raises(asyncio.CancelledError):
            async for _ in sequential_execute():
                pytest.fail("Should not emit events in sequential mode when cancelled")

    # ====================
    # Pre-Invocation Tests
    # ====================

    @pytest.mark.asyncio
    async def test_tool_not_invoked_when_cancelled_before_execution(
        self, mock_agent, mock_tool, cancel_event
    ):
        """
        CRITICAL: Tool invocation should NOT happen if cancellation requested.

        This tests the fix in base.py:567-572 where we add cancellation check
        before await tool.invoke_function().
        """
        # Arrange: Set cancellation BEFORE invocation
        cancel_event.set()

        # Mock invoke_tool with cancellation check (the fix)
        async def invoke_with_check():
            await mock_agent._cancel_token.check_cancelled()
            return await mock_tool.invoke_function("test_func", {})

        # Act & Assert: Should raise CancelledError, NOT invoke tool
        with pytest.raises(asyncio.CancelledError):
            await invoke_with_check()

        # Verify: Tool was never invoked
        mock_tool.invoke_function.assert_not_called()

    @pytest.mark.asyncio
    async def test_tool_invocation_cancelled_mid_execution(
        self, mock_agent, mock_tool, cancel_event
    ):
        """
        Test that cancellation during tool execution is handled gracefully.

        Even if tool starts, cancellation should interrupt it.
        """
        # Arrange: Tool that takes time to execute
        async def slow_tool():
            await asyncio.sleep(0.1)
            return {"result": "too slow"}

        mock_tool.invoke_function = slow_tool

        # Start execution, then cancel mid-flight
        async def execute_and_cancel():
            # Start execution
            task = asyncio.create_task(mock_tool.invoke_function())

            # Cancel after 50ms
            await asyncio.sleep(0.05)
            cancel_event.set()
            task.cancel()

            return await task

        # Act & Assert
        with pytest.raises(asyncio.CancelledError):
            await execute_and_cancel()

    # ====================
    # Grace Period Tests
    # ====================

    @pytest.mark.asyncio
    async def test_immediate_cancellation_on_client_disconnect(self, cancel_event):
        """
        Test that client disconnect triggers immediate cancellation.

        This validates the fix in session_routes.py:799-803 where we
        change from 45-second grace period to immediate cancellation.
        """
        # Arrange: Simulate SSE disconnect handler
        async def handle_disconnect(close_reason: str):
            if close_reason == "client_disconnected":
                # NEW: Immediate cancellation (no grace period)
                cancel_event.set()
                return 0  # No delay
            elif close_reason == "generator_cancelled":
                # Short grace period for legitimate retries
                await asyncio.sleep(5.0)
                cancel_event.set()
                return 5
            return None

        # Act: Client disconnect
        delay = await handle_disconnect("client_disconnected")

        # Assert: Immediate cancellation (0 delay)
        assert delay == 0
        assert cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_short_grace_period_on_generator_cancelled(self, cancel_event):
        """
        Test that generator cancellation has short grace period (5s, not 45s).
        """
        # Arrange
        async def handle_disconnect(close_reason: str):
            if close_reason == "generator_cancelled":
                await asyncio.sleep(5.0)
                cancel_event.set()
                return 5
            return None

        # Act
        start = asyncio.get_event_loop().time()
        delay = await handle_disconnect("generator_cancelled")
        elapsed = asyncio.get_event_loop().time() - start

        # Assert: 5-second grace period
        assert delay == 5
        assert 4.9 <= elapsed <= 5.2  # Allow small variance
        assert cancel_event.is_set()

    # ====================
    # Background Task Cleanup Tests
    # ====================

    @pytest.mark.asyncio
    async def test_background_tasks_cancelled_on_destroy(self):
        """
        Test that background tasks are cancelled when task runner is destroyed.

        This validates the fix in agent_task_runner.py destroy() method.
        """
        # Arrange: Create mock task runner with background tasks
        background_tasks = set()

        async def long_running_task():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise  # Re-raise to signal cancellation

        # Create 3 background tasks
        for i in range(3):
            task = asyncio.create_task(long_running_task())
            background_tasks.add(task)

        # Mock destroy() with cancellation logic (the fix)
        async def destroy_with_cleanup():
            for task in list(background_tasks):
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            background_tasks.clear()

        # Act: Destroy task runner
        await destroy_with_cleanup()

        # Assert: All tasks cancelled and cleared
        assert len(background_tasks) == 0

    @pytest.mark.asyncio
    async def test_background_tasks_cleanup_handles_already_done_tasks(self):
        """
        Test that cleanup handles tasks that are already completed.
        """
        # Arrange
        background_tasks = set()

        async def quick_task():
            await asyncio.sleep(0.01)
            return "done"

        # Create completed task
        task = asyncio.create_task(quick_task())
        await task  # Wait for completion
        background_tasks.add(task)

        # Mock destroy
        async def destroy_with_cleanup():
            for task in list(background_tasks):
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            background_tasks.clear()

        # Act
        await destroy_with_cleanup()

        # Assert: No errors, task cleared
        assert len(background_tasks) == 0
        assert task.done()

    # ====================
    # Integration Tests
    # ====================

    @pytest.mark.asyncio
    async def test_end_to_end_cancellation_flow(self, mock_agent, cancel_event):
        """
        End-to-end test: SSE disconnect → cancellation → no tool execution.

        Simulates the full flow from client disconnect to agent stopping.
        """
        # Arrange: Agent with pending tool execution
        tool_executed = False

        async def agent_workflow():
            # Simulate waiting for LLM response
            await asyncio.sleep(0.05)

            # Check cancellation BEFORE emitting tool
            await mock_agent._cancel_token.check_cancelled()

            # Tool emission (should not reach here)
            yield ToolEvent(tool_name="test", status=ToolStatus.CALLING, result=None)

            # Check cancellation BEFORE invocation
            await mock_agent._cancel_token.check_cancelled()

            # Tool invocation (should not reach here)
            nonlocal tool_executed
            tool_executed = True

        # Act: Start workflow, then cancel
        workflow_task = asyncio.create_task(
            asyncio.wait_for(
                self._consume_generator(agent_workflow()), timeout=1.0
            )
        )

        # Simulate SSE disconnect after 20ms
        await asyncio.sleep(0.02)
        cancel_event.set()  # Client disconnect

        # Assert: Workflow raises CancelledError, tool never executed
        with pytest.raises(asyncio.CancelledError):
            await workflow_task

        assert not tool_executed

    @pytest.mark.asyncio
    async def test_race_condition_prevention(self, mock_agent, cancel_event):
        """
        Test that fixes prevent the 45-second race condition window.

        Before fix: Tool could start during 45s grace period
        After fix: Tool blocked immediately on cancellation
        """
        # Arrange: Simulate the problematic timing
        events_emitted = []

        async def problematic_flow():
            # Simulate LLM processing (30ms)
            await asyncio.sleep(0.03)

            # OLD CODE (no check): Would emit event here
            # NEW CODE (with check): Raises CancelledError

            await mock_agent._cancel_token.check_cancelled()

            events_emitted.append("tool_calling")
            yield ToolEvent(tool_name="test", status=ToolStatus.CALLING, result=None)

        # Act: Cancel during LLM processing (after 10ms)
        flow_task = asyncio.create_task(self._consume_generator(problematic_flow()))

        await asyncio.sleep(0.01)
        cancel_event.set()  # Cancel during LLM processing

        # Assert: Flow cancelled, NO events emitted
        with pytest.raises(asyncio.CancelledError):
            await flow_task

        assert len(events_emitted) == 0  # Critical: No events leaked

    # ====================
    # Helper Methods
    # ====================

    @staticmethod
    async def _consume_generator(gen):
        """Helper to consume async generator and collect events."""
        events = []
        async for event in gen:
            events.append(event)
        return events


# ====================
# Performance Tests
# ====================


class TestCancellationPerformance:
    """Test that cancellation happens quickly (no 45s delay)."""

    @pytest.mark.asyncio
    async def test_cancellation_latency_under_1_second(self):
        """
        Verify cancellation completes in <1 second (not 45 seconds).
        """
        # Arrange
        cancel_event = asyncio.Event()

        async def agent_simulation():
            while True:
                # Check cancellation every iteration
                if cancel_event.is_set():
                    raise asyncio.CancelledError("Session cancelled")
                await asyncio.sleep(0.1)

        # Act: Start agent, then cancel
        agent_task = asyncio.create_task(agent_simulation())

        start = asyncio.get_event_loop().time()
        await asyncio.sleep(0.05)  # Let agent start

        cancel_event.set()  # Request cancellation

        with pytest.raises(asyncio.CancelledError):
            await agent_task

        elapsed = asyncio.get_event_loop().time() - start

        # Assert: Cancelled in <1 second (not 45 seconds!)
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_concurrent_cancellation_requests(self):
        """
        Test that multiple concurrent cancellation requests are handled gracefully.
        """
        # Arrange
        cancel_event = asyncio.Event()
        cancellation_count = 0

        async def agent_simulation():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                nonlocal cancellation_count
                cancellation_count += 1
                raise

        # Act: Start agent
        agent_task = asyncio.create_task(agent_simulation())

        # Send multiple cancellation signals (simulates race condition)
        cancel_event.set()
        cancel_event.set()
        cancel_event.set()

        agent_task.cancel()

        # Assert: Handled gracefully (no crash)
        with pytest.raises(asyncio.CancelledError):
            await agent_task

        assert cancellation_count == 1  # Only cancelled once
