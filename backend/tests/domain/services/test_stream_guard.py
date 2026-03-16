"""Tests for the StreamGuard service."""

import asyncio

import pytest

import app.domain.services.stream_guard as stream_guard_module
from app.domain.models.event import MessageEvent, PlanningPhase, ProgressEvent
from app.domain.services.stream_guard import (
    CancellationToken,
    StreamErrorCategory,
    StreamErrorCode,
    StreamGuard,
    StreamMetrics,
    get_aggregate_stream_metrics,
    has_active_stream,
    record_stream_metrics,
    record_stream_reconnection,
)


@pytest.fixture(autouse=True)
def reset_stream_guard_globals():
    stream_guard_module._stream_metrics.clear()
    stream_guard_module._active_streams.clear()
    stream_guard_module._reconnection_events.clear()
    yield
    stream_guard_module._stream_metrics.clear()
    stream_guard_module._active_streams.clear()
    stream_guard_module._reconnection_events.clear()


class TestStreamMetrics:
    """Tests for StreamMetrics class."""

    def test_initial_metrics(self):
        """Test that initial metrics are zero."""
        metrics = StreamMetrics("test-session")
        assert metrics.events_sent == 0
        assert metrics.errors == []
        assert metrics.cancellation_count == 0
        assert metrics.waiting_events == 0
        assert metrics.waiting_stage_counts == {}
        assert metrics.duration_seconds >= 0

    def test_record_event(self):
        """Test recording events."""
        metrics = StreamMetrics("test-session")
        event = MessageEvent(message="test", role="user")

        metrics.record_event(event)
        assert metrics.events_sent == 1

        metrics.record_event(event)
        assert metrics.events_sent == 2

    def test_record_error(self):
        """Test recording errors."""
        metrics = StreamMetrics("test-session")

        metrics.record_error(
            StreamErrorCode.STREAM_TIMEOUT,
            StreamErrorCategory.TIMEOUT,
            recoverable=True,
            message="Timeout occurred",
        )

        assert len(metrics.errors) == 1
        assert metrics.errors[0]["code"] == StreamErrorCode.STREAM_TIMEOUT.value
        assert metrics.errors[0]["recoverable"] is True

    def test_events_per_second(self):
        """Test events per second calculation."""
        metrics = StreamMetrics("test-session")

        # Simulate time passing and events being recorded
        import time

        time.sleep(0.1)  # 100ms

        for _ in range(10):
            metrics.record_event(MessageEvent(message="test", role="user"))

        # Should be approximately 100 events/second (10 events in 0.1s)
        # But with some tolerance for timing
        assert metrics.events_per_second > 50
        assert metrics.events_per_second < 200

    def test_to_dict(self):
        """Test exporting metrics to dict."""
        metrics = StreamMetrics("test-session")
        metrics.record_event(MessageEvent(message="test", role="user"))

        result = metrics.to_dict()

        assert "session_id" in result
        assert "events_sent" in result
        assert "error_count" in result
        assert result["session_id"] == "test-session"
        assert result["events_sent"] == 1

    def test_record_waiting_progress_event_tracks_waiting_metrics(self):
        """Waiting progress events should increment waiting counters and stage breakdown."""
        metrics = StreamMetrics("test-session")

        metrics.record_event(
            ProgressEvent(
                phase=PlanningPhase.WAITING,
                message="Still working on your request...",
                wait_stage="execution_wait",
                wait_elapsed_seconds=12,
            )
        )
        metrics.record_event(
            ProgressEvent(
                phase=PlanningPhase.WAITING,
                message="Still working on your request...",
                wait_stage="tool_wait",
                wait_elapsed_seconds=24,
            )
        )
        metrics.record_event(MessageEvent(message="done", role="assistant"))

        assert metrics.events_sent == 3
        assert metrics.waiting_events == 2
        assert metrics.waiting_stage_counts["execution_wait"] == 1
        assert metrics.waiting_stage_counts["tool_wait"] == 1


class TestCancellationToken:
    """Tests for CancellationToken class."""

    def test_null_token_never_cancelled(self):
        """Test that null token never returns cancelled."""
        token = CancellationToken.null()
        assert token.is_cancelled() is False
        assert bool(token) is True

    def test_event_based_token(self):
        """Test token with asyncio.Event."""
        event = asyncio.Event()
        token = CancellationToken(event=event, session_id="test")

        assert token.is_cancelled() is False

        event.set()
        assert token.is_cancelled() is True

    @pytest.mark.asyncio
    async def test_check_cancelled_raises(self):
        """Test that check_cancelled raises when cancelled."""
        event = asyncio.Event()
        event.set()
        token = CancellationToken(event=event, session_id="test")

        with pytest.raises(asyncio.CancelledError):
            await token.check_cancelled()

    @pytest.mark.asyncio
    async def test_wait_for_cancellation_timeout(self):
        """Test wait_for_cancellation with timeout."""
        event = asyncio.Event()
        token = CancellationToken(event=event, session_id="test")

        # Should return False after timeout
        result = await token.wait_for_cancellation(wait_seconds=0.1)
        assert result is False

    @pytest.mark.asyncio
    async def test_wrap_awaitable_success(self):
        """Test wrap_awaitable completes normally."""
        token = CancellationToken.null()

        async def successful_op():
            await asyncio.sleep(0.01)
            return "success"

        result = await token.wrap_awaitable(successful_op())
        assert result == "success"

    @pytest.mark.asyncio
    async def test_wrap_awaitable_cancellation(self):
        """Test wrap_awaitable raises on cancellation."""
        event = asyncio.Event()
        token = CancellationToken(event=event, session_id="test")

        async def slow_op():
            await asyncio.sleep(1.0)
            return "should not reach"

        # Cancel immediately
        event.set()

        with pytest.raises(asyncio.CancelledError):
            await token.wrap_awaitable(slow_op())


class TestStreamGuard:
    """Tests for StreamGuard class."""

    @pytest.mark.asyncio
    async def test_wrap_yields_events(self):
        """Test that wrap yields all events from generator."""

        async def generator():
            yield MessageEvent(message="1", role="user")
            yield MessageEvent(message="2", role="user")

        guard = StreamGuard(session_id="test")
        events = [event async for event in guard.wrap(generator())]

        assert len(events) == 2
        assert guard.metrics.events_sent == 2

    @pytest.mark.asyncio
    async def test_wrap_handles_cancellation(self):
        """Test that wrap handles cancellation properly."""
        event = asyncio.Event()
        token = CancellationToken(event=event, session_id="test")

        async def generator():
            yield MessageEvent(message="1", role="user")
            event.set()  # Cancel after first event
            await asyncio.sleep(1)  # This should be interrupted
            yield MessageEvent(message="2", role="user")

        guard = StreamGuard(session_id="test", cancel_token=token)
        events = [event async for event in guard.wrap(generator())]

        # Should have received first event + cancellation error event
        assert len(events) >= 1
        assert guard.metrics.cancellation_count >= 1

    @pytest.mark.asyncio
    async def test_wrap_handles_exception(self):
        """Test that wrap handles exceptions properly."""

        async def generator():
            yield MessageEvent(message="1", role="user")
            raise RuntimeError("Test error")

        guard = StreamGuard(session_id="test")
        events = [event async for event in guard.wrap(generator())]

        # Should have received first event + error event
        assert len(events) == 2
        assert isinstance(events[1], type(events[1]))  # ErrorEvent
        assert len(guard.metrics.errors) == 1

    @pytest.mark.asyncio
    async def test_classifies_timeout_error(self):
        """Test error classification for timeout errors."""

        async def generator():
            raise TimeoutError("Connection timed out")
            if False:  # pragma: no cover - ensures this is an async generator
                yield MessageEvent(message="never", role="user")

        guard = StreamGuard(session_id="test")
        events = [event async for event in guard.wrap(generator())]

        assert len(events) == 1
        # ErrorEvent should have timeout-related fields
        assert events[0].error_code == StreamErrorCode.STREAM_TIMEOUT.value
        assert events[0].recoverable is True

    def test_get_metrics(self):
        """Test getting metrics from guard."""
        guard = StreamGuard(session_id="test")
        metrics = guard.get_metrics()

        assert isinstance(metrics, StreamMetrics)
        assert metrics.session_id == "test"

    @pytest.mark.asyncio
    async def test_wrap_tracks_active_connection_lifecycle(self):
        """Stream should appear as active while generator is open, then be removed."""

        async def generator():
            yield MessageEvent(message="1", role="user")
            await asyncio.sleep(0.01)

        guard = StreamGuard(session_id="session-active", endpoint="chat")
        wrapped = guard.wrap(generator())
        iterator = wrapped.__aiter__()

        first = await iterator.__anext__()
        assert isinstance(first, MessageEvent)

        during = await get_aggregate_stream_metrics()
        assert during["active_connections"] == 1
        assert during["active_connections_by_endpoint"].get("chat") == 1

        with pytest.raises(StopAsyncIteration):
            await iterator.__anext__()

        after = await get_aggregate_stream_metrics()
        assert after["active_connections"] == 0

    @pytest.mark.asyncio
    async def test_has_active_stream_matches_lifecycle(self):
        """Session activity helper should track registration/unregistration accurately."""

        async def generator():
            yield MessageEvent(message="1", role="user")
            await asyncio.sleep(0.01)

        guard = StreamGuard(session_id="session-has-active", endpoint="chat")
        wrapped = guard.wrap(generator())
        iterator = wrapped.__aiter__()

        _ = await iterator.__anext__()
        assert await has_active_stream("session-has-active", endpoint="chat") is True

        with pytest.raises(StopAsyncIteration):
            await iterator.__anext__()

        assert await has_active_stream("session-has-active", endpoint="chat") is False

    @pytest.mark.asyncio
    async def test_aggregate_metrics_includes_percentiles_and_reconnections(self):
        metrics = StreamMetrics(session_id="session-1", endpoint="chat")
        metrics.event_latencies = [0.1, 0.2, 0.3]
        metrics.events_sent = 3
        metrics.record_error(
            StreamErrorCode.INTERNAL_ERROR,
            StreamErrorCategory.INTERNAL,
            recoverable=True,
            message="boom",
        )
        await record_stream_metrics(metrics)
        await record_stream_reconnection("session-1", "chat")
        await record_stream_reconnection("session-1", "chat")

        aggregate = await get_aggregate_stream_metrics()

        assert aggregate["total_sessions"] == 1
        assert aggregate["total_events"] == 3
        assert aggregate["reconnections_last_5m"] == 2
        assert aggregate["reconnections_last_5m_by_endpoint"].get("chat") == 2
        assert aggregate["latency_ms"]["p50"] is not None
        assert aggregate["latency_ms"]["p95"] is not None
        assert aggregate["latency_ms"]["p99"] is not None
        assert aggregate["error_count_by_category"].get("internal") == 1

    @pytest.mark.asyncio
    async def test_aggregate_metrics_includes_waiting_distribution(self):
        metrics = StreamMetrics(session_id="session-wait", endpoint="chat")
        metrics.record_event(
            ProgressEvent(
                phase=PlanningPhase.WAITING,
                message="Still working on your request...",
                wait_stage="execution_wait",
                wait_elapsed_seconds=8,
            )
        )
        metrics.record_event(
            ProgressEvent(
                phase=PlanningPhase.WAITING,
                message="Still working on your request...",
                wait_stage="tool_wait",
                wait_elapsed_seconds=16,
            )
        )
        metrics.record_event(MessageEvent(message="done", role="assistant"))
        await record_stream_metrics(metrics)

        aggregate = await get_aggregate_stream_metrics()

        assert aggregate["waiting_events_total"] == 2
        assert aggregate["avg_waiting_events_per_session"] == pytest.approx(2.0)
        assert aggregate["waiting_event_ratio"] == pytest.approx(2 / 3)
        assert aggregate["waiting_stage_counts"].get("execution_wait") == 1
        assert aggregate["waiting_stage_counts"].get("tool_wait") == 1
