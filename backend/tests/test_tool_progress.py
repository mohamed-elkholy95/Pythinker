"""Tests for tool execution progress tracking."""

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from app.domain.models.event import ToolProgressEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, ToolProgress
from app.domain.services.tools.base import tool as tool_decorator


class TestToolProgress:
    """Tests for ToolProgress dataclass."""

    def test_progress_initialization(self):
        """Test that ToolProgress initializes correctly."""
        progress = ToolProgress(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
        )

        assert progress.tool_call_id == "test-123"
        assert progress.tool_name == "browser"
        assert progress.function_name == "navigate"
        assert progress.steps_completed == 0
        assert progress.steps_total is None
        assert progress.current_step == "Initializing"
        assert progress.checkpoints == []

    def test_progress_percent_calculation(self):
        """Test progress percentage calculation."""
        progress = ToolProgress(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
            steps_total=10,
        )

        assert progress.progress_percent == 0

        progress.steps_completed = 5
        assert progress.progress_percent == 50

        progress.steps_completed = 10
        assert progress.progress_percent == 100

        # Cap at 100%
        progress.steps_completed = 15
        assert progress.progress_percent == 100

    def test_progress_percent_with_unknown_total(self):
        """Test progress percentage when total is unknown."""
        progress = ToolProgress(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
            steps_total=None,
        )

        progress.steps_completed = 5
        assert progress.progress_percent == 0

    def test_elapsed_time_tracking(self):
        """Test elapsed time calculation."""
        progress = ToolProgress(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
        )

        # Small delay to ensure measurable elapsed time
        time.sleep(0.01)
        elapsed = progress.elapsed_ms

        assert elapsed >= 10  # At least 10ms

    def test_estimated_remaining_time(self):
        """Test remaining time estimation."""
        progress = ToolProgress(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
            steps_total=10,
        )

        # No estimate when no progress
        assert progress.estimated_remaining_ms is None

        # Simulate some progress
        progress.steps_completed = 5
        # With 5 of 10 steps done, remaining should be similar to elapsed
        remaining = progress.estimated_remaining_ms
        assert remaining is not None
        assert remaining >= 0

    @pytest.mark.asyncio
    async def test_update_increments_steps(self):
        """Test that update increments steps correctly."""
        progress = ToolProgress(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
        )

        await progress.update("Step 1")
        assert progress.steps_completed == 1
        assert progress.current_step == "Step 1"

        await progress.update("Step 2")
        assert progress.steps_completed == 2
        assert progress.current_step == "Step 2"

    @pytest.mark.asyncio
    async def test_update_with_explicit_values(self):
        """Test update with explicit step values."""
        progress = ToolProgress(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
        )

        await progress.update("Jumping ahead", steps_completed=5, steps_total=10)
        assert progress.steps_completed == 5
        assert progress.steps_total == 10
        assert progress.progress_percent == 50

    @pytest.mark.asyncio
    async def test_update_calls_callback(self):
        """Test that update calls the progress callback."""
        callback = AsyncMock()
        progress = ToolProgress(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
            _callback=callback,
        )

        await progress.update("Testing callback")

        callback.assert_called_once()
        call_kwargs = callback.call_args.kwargs
        assert call_kwargs["tool_call_id"] == "test-123"
        assert call_kwargs["current_step"] == "Testing callback"

    @pytest.mark.asyncio
    async def test_checkpoint_creates_restore_point(self):
        """Test checkpoint creation."""
        progress = ToolProgress(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
        )

        await progress.update("Step 1")
        checkpoint_id = await progress.checkpoint({"url": "https://example.com", "scroll_position": 500})

        assert checkpoint_id is not None
        assert len(progress.checkpoints) == 1
        assert progress.last_checkpoint_id == checkpoint_id

        checkpoint = progress.get_last_checkpoint()
        assert checkpoint is not None
        assert checkpoint["id"] == checkpoint_id
        assert checkpoint["data"]["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_checkpoint_notifies_callback(self):
        """Test that checkpoint notifies callback with checkpoint data."""
        callback = AsyncMock()
        progress = ToolProgress(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
            _callback=callback,
        )

        checkpoint_data = {"state": "saved"}
        await progress.checkpoint(checkpoint_data)

        call_kwargs = callback.call_args.kwargs
        assert call_kwargs["checkpoint_id"] is not None
        assert call_kwargs["checkpoint_data"] == checkpoint_data

    @pytest.mark.asyncio
    async def test_callback_failure_doesnt_crash(self):
        """Test that callback failure is handled gracefully."""
        callback = AsyncMock(side_effect=Exception("Callback error"))
        progress = ToolProgress(
            tool_call_id="test-123",
            tool_name="browser",
            function_name="navigate",
            _callback=callback,
        )

        # Should not raise
        await progress.update("Step 1")
        assert progress.steps_completed == 1


class TestBaseToolProgress:
    """Tests for BaseTool progress integration."""

    def test_tool_has_progress_callback_support(self):
        """Test that BaseTool accepts progress callback."""
        callback = AsyncMock()
        tool = BaseTool(progress_callback=callback)

        assert tool._progress_callback is callback

    def test_set_progress_callback(self):
        """Test setting progress callback after init."""
        tool = BaseTool()
        callback = AsyncMock()

        tool.set_progress_callback(callback)

        assert tool._progress_callback is callback

    def test_create_progress_tracker(self):
        """Test creating a progress tracker."""
        callback = AsyncMock()
        tool = BaseTool(progress_callback=callback)
        tool.name = "test_tool"

        progress = tool.create_progress(
            tool_call_id="call-123",
            function_name="do_something",
            steps_total=5,
        )

        assert progress.tool_call_id == "call-123"
        assert progress.tool_name == "test_tool"
        assert progress.function_name == "do_something"
        assert progress.steps_total == 5
        assert progress._callback is callback
        assert tool.get_active_progress() is progress

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint_default(self):
        """Test that default resume returns None."""
        tool = BaseTool()

        result = await tool.resume_from_checkpoint(
            checkpoint_id="cp-123",
            checkpoint_data={"state": "test"},
        )

        assert result is None


class TestToolProgressEvent:
    """Tests for ToolProgressEvent model."""

    def test_event_creation(self):
        """Test creating a ToolProgressEvent."""
        event = ToolProgressEvent(
            tool_call_id="call-123",
            tool_name="browser",
            function_name="navigate",
            progress_percent=50,
            current_step="Loading page",
            steps_completed=5,
            steps_total=10,
            elapsed_ms=1500.5,
        )

        assert event.type == "tool_progress"
        assert event.tool_call_id == "call-123"
        assert event.progress_percent == 50
        assert event.current_step == "Loading page"

    def test_event_with_checkpoint(self):
        """Test event with checkpoint data."""
        event = ToolProgressEvent(
            tool_call_id="call-123",
            tool_name="browser",
            function_name="navigate",
            progress_percent=75,
            current_step="Scrolling",
            checkpoint_id="cp-abc",
            checkpoint_data={"scroll_y": 1000},
        )

        assert event.checkpoint_id == "cp-abc"
        assert event.checkpoint_data["scroll_y"] == 1000


class TestProgressIntegration:
    """Integration tests for progress tracking."""

    @pytest.mark.asyncio
    async def test_full_progress_lifecycle(self):
        """Test complete progress tracking lifecycle."""
        events_received = []

        async def capture_callback(**kwargs):
            events_received.append(kwargs)

        tool = BaseTool(progress_callback=capture_callback)
        tool.name = "test_tool"

        # Create progress tracker
        progress = tool.create_progress(
            tool_call_id="call-123",
            function_name="long_operation",
            steps_total=3,
        )

        # Simulate long operation with progress updates
        await progress.update("Starting operation")
        await progress.update("Processing data")
        await progress.checkpoint({"partial_result": "data"})
        await progress.update("Finishing up")

        assert len(events_received) == 4
        assert events_received[0]["current_step"] == "Starting operation"
        assert events_received[1]["current_step"] == "Processing data"
        assert events_received[2]["checkpoint_id"] is not None
        assert events_received[3]["current_step"] == "Finishing up"
        assert events_received[3]["progress_percent"] == 100

    @pytest.mark.asyncio
    async def test_progress_with_unknown_total(self):
        """Test progress tracking when total steps unknown."""
        events_received = []

        async def capture_callback(**kwargs):
            events_received.append(kwargs)

        tool = BaseTool(progress_callback=capture_callback)
        tool.name = "search"

        progress = tool.create_progress(
            tool_call_id="call-456",
            function_name="search_web",
            steps_total=None,  # Unknown total
        )

        await progress.update("Searching...")
        await progress.update("Found first result")
        await progress.update("Found second result", steps_total=5)  # Now we know total

        # First two should have 0% (unknown total)
        assert events_received[0]["progress_percent"] == 0
        assert events_received[1]["progress_percent"] == 0
        # Third should have calculated percent
        assert events_received[2]["progress_percent"] == 60  # 3/5 = 60%


class TestProgressWithSampleTool:
    """Tests with a sample tool implementation."""

    @pytest.mark.asyncio
    async def test_tool_with_progress_enabled(self):
        """Test a tool that uses progress tracking."""

        class SampleTool(BaseTool):
            name = "sample"
            supports_progress = True

            @tool_decorator(
                name="long_task",
                description="A long-running task",
                parameters={},
                required=[],
            )
            async def long_task(self) -> ToolResult:
                progress = self.create_progress(
                    tool_call_id="sample-call",
                    function_name="long_task",
                    steps_total=3,
                )

                await progress.update("Step 1: Init")
                await asyncio.sleep(0.01)

                await progress.update("Step 2: Process")
                await asyncio.sleep(0.01)

                await progress.update("Step 3: Complete")

                return ToolResult(success=True, message="Done")

        events = []

        async def callback(**kwargs):
            events.append(kwargs)

        tool = SampleTool(progress_callback=callback)
        result = await tool.long_task()

        assert result.success is True
        assert len(events) == 3
        assert events[2]["progress_percent"] == 100
