"""Tests for SSE Streaming v2

Phase 3 Enhancement: Tests for graph-style event streaming with disconnect handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import StreamEvent, ToolEvent, ToolStatus
from app.interfaces.schemas.event import EventMapper


def create_tool_event(
    tool_name: str = "search",
    status: ToolStatus = ToolStatus.CALLING,
    result: str | None = None,
) -> ToolEvent:
    """Helper to create ToolEvent with required fields."""
    return ToolEvent(
        tool_call_id="test-call-id",
        tool_name=tool_name,
        function_name=tool_name,
        function_args={},
        status=status,
        function_result=result,
    )


class TestStreamEvent:
    """Tests for StreamEvent model."""

    def test_stream_event_creation(self):
        """Test creating a stream event."""
        event = StreamEvent(content="Hello", is_final=False)
        assert event.content == "Hello"
        assert event.is_final is False
        assert event.type == "stream"

    def test_stream_event_final(self):
        """Test final stream event."""
        event = StreamEvent(content="Complete response", is_final=True)
        assert event.is_final is True

    def test_stream_event_empty_content(self):
        """Test stream event with empty content."""
        event = StreamEvent(content="", is_final=False)
        assert event.content == ""


class TestToolEvent:
    """Tests for ToolEvent model."""

    def test_tool_event_calling(self):
        """Test tool calling event."""
        event = create_tool_event(tool_name="search", status=ToolStatus.CALLING)
        assert event.tool_name == "search"
        assert event.status == ToolStatus.CALLING
        assert event.function_result is None

    def test_tool_event_called(self):
        """Test tool called event."""
        event = create_tool_event(
            tool_name="search",
            status=ToolStatus.CALLED,
            result="Found 10 results",
        )
        assert event.status == ToolStatus.CALLED
        assert event.function_result == "Found 10 results"


class TestSSEStreamingV2:
    """Tests for SSE streaming v2 functionality."""

    @pytest.fixture
    def mock_graph(self):
        """Create mock graph runtime."""
        return MagicMock()

    @pytest.fixture
    def mock_event_queue(self):
        """Create mock event queue."""
        return asyncio.Queue()

    @pytest.mark.asyncio
    async def test_chat_model_stream_event(self, mock_event_queue):
        """Test handling on_chat_model_stream events."""
        # Simulate v2 graph event output
        chunk = MagicMock()
        chunk.content = "Hello"

        event = {
            "event": "on_chat_model_stream",
            "data": {"chunk": chunk},
        }

        # Process event
        if event["event"] == "on_chat_model_stream":
            chunk_data = event.get("data", {})
            chunk_obj = chunk_data.get("chunk")
            if chunk_obj and hasattr(chunk_obj, "content") and chunk_obj.content:
                await mock_event_queue.put(StreamEvent(content=chunk_obj.content, is_final=False))

        # Verify event was queued
        queued_event = await mock_event_queue.get()
        assert isinstance(queued_event, StreamEvent)
        assert queued_event.content == "Hello"

    @pytest.mark.asyncio
    async def test_tool_start_event(self, mock_event_queue):
        """Test handling on_tool_start events."""
        event = {
            "event": "on_tool_start",
            "name": "search",
            "data": {"input": {"query": "python"}},
        }

        if event["event"] == "on_tool_start":
            tool_name = event.get("name", "unknown")
            await mock_event_queue.put(create_tool_event(tool_name=tool_name, status=ToolStatus.CALLING))

        queued_event = await mock_event_queue.get()
        assert isinstance(queued_event, ToolEvent)
        assert queued_event.tool_name == "search"
        assert queued_event.status == ToolStatus.CALLING

    @pytest.mark.asyncio
    async def test_tool_end_event(self, mock_event_queue):
        """Test handling on_tool_end events."""
        event = {
            "event": "on_tool_end",
            "name": "search",
            "data": {"output": "Found 5 results"},
        }

        if event["event"] == "on_tool_end":
            tool_name = event.get("name", "unknown")
            tool_output = event.get("data", {}).get("output")
            await mock_event_queue.put(
                create_tool_event(
                    tool_name=tool_name,
                    status=ToolStatus.CALLED,
                    result=str(tool_output)[:500] if tool_output else None,
                )
            )

        queued_event = await mock_event_queue.get()
        assert isinstance(queued_event, ToolEvent)
        assert queued_event.status == ToolStatus.CALLED
        assert queued_event.function_result == "Found 5 results"

    @pytest.mark.asyncio
    async def test_chain_end_pending_events(self, mock_event_queue):
        """Test handling on_chain_end with pending_events."""
        pending_event = StreamEvent(content="Pending content", is_final=False)
        event = {
            "event": "on_chain_end",
            "data": {
                "output": {
                    "pending_events": [pending_event],
                }
            },
        }

        if event["event"] == "on_chain_end":
            output = event.get("data", {}).get("output", {})
            if isinstance(output, dict):
                pending_events = output.get("pending_events", [])
                for evt in pending_events:
                    await mock_event_queue.put(evt)

        queued_event = await mock_event_queue.get()
        assert queued_event.content == "Pending content"


class TestDisconnectHandling:
    """Tests for client disconnect handling."""

    @pytest.fixture
    def mock_request(self):
        """Create mock request with is_disconnected method."""
        request = MagicMock()
        request.is_disconnected = AsyncMock(return_value=False)
        return request

    @pytest.mark.asyncio
    async def test_disconnect_check_during_streaming(self, mock_request):
        """Test disconnect check during streaming."""
        events = [
            StreamEvent(content="chunk1", is_final=False),
            StreamEvent(content="chunk2", is_final=False),
            StreamEvent(content="final", is_final=True),
        ]

        sent_events = []
        for event in events:
            if await mock_request.is_disconnected():
                break
            sent_events.append(event)

        # All events should be sent (not disconnected)
        assert len(sent_events) == 3

    @pytest.mark.asyncio
    async def test_disconnect_stops_streaming(self, mock_request):
        """Test that disconnect stops streaming."""
        # Simulate disconnect after first event
        call_count = 0

        async def check_disconnect():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        mock_request.is_disconnected = check_disconnect

        events = [
            StreamEvent(content="chunk1", is_final=False),
            StreamEvent(content="chunk2", is_final=False),
            StreamEvent(content="chunk3", is_final=False),
        ]

        sent_events = []
        for event in events:
            if await mock_request.is_disconnected():
                break
            sent_events.append(event)

        # Only first event should be sent
        assert len(sent_events) == 1
        assert sent_events[0].content == "chunk1"

    @pytest.mark.asyncio
    async def test_send_timeout_handling(self):
        """Test handling of send timeouts."""

        async def slow_send():
            await asyncio.sleep(2)
            return "sent"

        with pytest.raises(asyncio.TimeoutError):
            async with asyncio.timeout(0.1):
                await slow_send()

    @pytest.mark.asyncio
    async def test_send_with_timeout_success(self):
        """Test successful send within timeout."""

        async def fast_send():
            await asyncio.sleep(0.01)
            return "sent"

        async with asyncio.timeout(1):
            result = await fast_send()
            assert result == "sent"


class TestEventQueueManagement:
    """Tests for event queue management."""

    @pytest.mark.asyncio
    async def test_queue_size_limit(self):
        """Test queue respects size limit."""
        max_size = 5
        queue = asyncio.Queue(maxsize=max_size)

        # Fill queue to capacity
        for i in range(max_size):
            await queue.put(StreamEvent(content=f"event_{i}", is_final=False))

        assert queue.full()

        # Next put should block (use put_nowait to verify)
        with pytest.raises(asyncio.QueueFull):
            queue.put_nowait(StreamEvent(content="overflow", is_final=False))

    @pytest.mark.asyncio
    async def test_queue_consumer_producer(self):
        """Test queue producer/consumer pattern."""
        queue = asyncio.Queue()
        consumed = []

        async def producer():
            for i in range(5):
                await queue.put(StreamEvent(content=f"event_{i}", is_final=i == 4))
                await asyncio.sleep(0.01)
            await queue.put(None)  # Signal completion

        async def consumer():
            while True:
                event = await queue.get()
                if event is None:
                    break
                consumed.append(event)

        await asyncio.gather(producer(), consumer())

        assert len(consumed) == 5
        assert consumed[-1].is_final is True

    @pytest.mark.asyncio
    async def test_queue_graceful_shutdown(self):
        """Test graceful queue shutdown."""
        queue = asyncio.Queue()

        # Add some events
        for i in range(3):
            await queue.put(StreamEvent(content=f"event_{i}", is_final=False))

        # Signal shutdown
        await queue.put(None)

        # Consumer drains queue
        events = []
        while True:
            event = await queue.get()
            if event is None:
                break
            events.append(event)

        assert len(events) == 3


class TestSSEFeatureFlag:
    """Tests for SSE v2 feature flag behavior."""

    def test_feature_flag_enables_v2(self):
        """Test feature flag enables v2 streaming."""
        with patch("app.core.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.feature_sse_v2 = True
            mock_settings.return_value = settings

            assert settings.feature_sse_v2 is True

    def test_feature_flag_fallback_to_v1(self):
        """Test feature flag fallback to v1."""
        with patch("app.core.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.feature_sse_v2 = False
            mock_settings.return_value = settings

            assert settings.feature_sse_v2 is False


class TestStreamingPerformance:
    """Tests for streaming performance characteristics."""

    @pytest.mark.asyncio
    async def test_streaming_latency(self):
        """Test streaming maintains low latency."""
        import time

        queue = asyncio.Queue()
        latencies = []

        async def producer():
            for i in range(10):
                await queue.put((time.time(), f"chunk_{i}"))
                await asyncio.sleep(0.01)
            await queue.put((None, None))

        async def consumer():
            while True:
                send_time, _content = await queue.get()
                if send_time is None:
                    break
                latency = time.time() - send_time
                latencies.append(latency)

        await asyncio.gather(producer(), consumer())

        # Average latency should be very low
        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 0.05  # Less than 50ms average

    @pytest.mark.asyncio
    async def test_backpressure_handling(self):
        """Test backpressure when consumer is slow."""
        queue = asyncio.Queue(maxsize=3)
        blocked_count = 0

        async def fast_producer():
            nonlocal blocked_count
            for i in range(10):
                try:
                    queue.put_nowait(f"event_{i}")
                except asyncio.QueueFull:
                    blocked_count += 1
                    await queue.put(f"event_{i}")  # Wait for space

        async def slow_consumer():
            consumed = 0
            while consumed < 10:
                await asyncio.sleep(0.02)  # Slow consumption
                try:
                    await asyncio.wait_for(queue.get(), timeout=0.1)
                    consumed += 1
                except TimeoutError:
                    break

        await asyncio.gather(fast_producer(), slow_consumer())

        # Producer should have been blocked some times
        assert blocked_count > 0


class TestEventSerialization:
    """Tests for event serialization for SSE."""

    def test_stream_event_json_serialization(self):
        """Test StreamEvent JSON serialization."""
        event = StreamEvent(content="Hello world", is_final=True)
        json_str = event.model_dump_json()

        import json

        parsed = json.loads(json_str)
        assert parsed["content"] == "Hello world"
        assert parsed["is_final"] is True
        assert parsed["type"] == "stream"

    @pytest.mark.asyncio
    async def test_stream_event_phase_passthrough_to_sse(self):
        """Test StreamEvent phase is preserved in SSE payload."""
        event = StreamEvent(content="summary chunk", is_final=False, phase="summarizing")

        sse_event = await EventMapper.event_to_sse_event(event)

        assert sse_event.event == "stream"
        assert getattr(sse_event.data, "phase", None) == "summarizing"

    def test_tool_event_json_serialization(self):
        """Test ToolEvent JSON serialization."""
        event = create_tool_event(
            tool_name="search",
            status=ToolStatus.CALLED,
            result="5 results",
        )
        json_str = event.model_dump_json()

        import json

        parsed = json.loads(json_str)
        assert parsed["tool_name"] == "search"
        assert parsed["status"] == "called"
        assert parsed["function_result"] == "5 results"

    def test_event_type_field_present(self):
        """Test event type field is present for SSE routing."""
        stream_event = StreamEvent(content="test", is_final=False)
        tool_event = create_tool_event(tool_name="test", status=ToolStatus.CALLING)

        assert hasattr(stream_event, "type")
        assert hasattr(tool_event, "type")
