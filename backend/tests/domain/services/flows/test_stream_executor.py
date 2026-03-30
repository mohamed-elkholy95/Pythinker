import asyncio

import pytest

from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    ProgressEvent,
    ToolEvent,
    ToolStatus,
)
from app.domain.services.flows.stream_executor import StreamExecutor
from app.domain.utils.cancellation import CancellationToken


async def _events_gen(*events: BaseEvent):
    for e in events:
        yield e


@pytest.mark.asyncio
async def test_streams_events_from_inner():
    token = CancellationToken(session_id="s1")
    executor = StreamExecutor(
        cancel_token=token,
        session_id="s1",
        agent_id="a1",
        wall_clock_timeout=60,
        idle_timeout=10,
    )
    done = DoneEvent()
    collected = [event async for event in executor.execute(_events_gen(done))]
    assert len(collected) == 1
    assert isinstance(collected[0], DoneEvent)


@pytest.mark.asyncio
async def test_idle_timeout_emits_error_and_done():
    token = CancellationToken(session_id="s2")
    executor = StreamExecutor(
        cancel_token=token,
        session_id="s2",
        agent_id="a2",
        wall_clock_timeout=60,
        idle_timeout=1,
    )

    async def _stalling_gen():
        yield ProgressEvent(phase="received", message="start")
        await asyncio.sleep(5)
        yield DoneEvent()

    collected = [event async for event in executor.execute(_stalling_gen())]

    assert len(collected) == 3
    assert isinstance(collected[1], ErrorEvent)
    assert "stuck" in collected[1].error.lower() or "timeout" in collected[1].error.lower()
    assert isinstance(collected[2], DoneEvent)


@pytest.mark.asyncio
async def test_cancellation_raises_cancelled_error():
    event = asyncio.Event()
    event.set()  # Pre-cancelled
    token = CancellationToken(event=event, session_id="s3")
    executor = StreamExecutor(
        cancel_token=token,
        session_id="s3",
        agent_id="a3",
        wall_clock_timeout=60,
        idle_timeout=10,
        grace_period=0,
    )

    with pytest.raises(asyncio.CancelledError):
        async for _ in executor.execute(_events_gen(DoneEvent())):
            pass


@pytest.mark.asyncio
async def test_grace_period_allows_reconnection():
    event = asyncio.Event()
    token = CancellationToken(event=event, session_id="s4")
    executor = StreamExecutor(
        cancel_token=token,
        session_id="s4",
        agent_id="a4",
        wall_clock_timeout=60,
        idle_timeout=30,
        grace_period=2,
    )

    tool_calling = ToolEvent(
        tool_call_id="call-1",
        tool_name="browser_navigate",
        function_name="browser_navigate",
        function_args={},
        status=ToolStatus.CALLING,
    )
    tool_called = ToolEvent(
        tool_call_id="call-1",
        tool_name="browser_navigate",
        function_name="browser_navigate",
        function_args={},
        status=ToolStatus.CALLED,
    )

    async def _tool_gen():
        yield tool_calling
        await asyncio.sleep(0.3)
        event.set()  # Simulate disconnect
        await asyncio.sleep(0.3)
        event.clear()  # Simulate reconnect before grace expires
        yield tool_called
        yield DoneEvent()

    collected = [ev async for ev in executor.execute(_tool_gen())]

    types = [type(e).__name__ for e in collected]
    assert "DoneEvent" in types, f"Expected completion but got: {types}"


@pytest.mark.asyncio
async def test_idle_timeout_closes_inner_generator():
    """Verify that idle timeout calls aclose() on the inner generator.

    This prevents the "empty pages after sandbox cleanup" bug where the
    inner generator's finally-block (e.g., final file sweep) was never
    executed because the generator was abandoned on timeout.
    """
    cleanup_ran = False

    async def _gen_with_cleanup():
        nonlocal cleanup_ran
        try:
            yield ProgressEvent(phase="received", message="start")
            await asyncio.sleep(10)  # Longer than idle_timeout
            yield DoneEvent()
        finally:
            cleanup_ran = True

    token = CancellationToken(session_id="s5")
    executor = StreamExecutor(
        cancel_token=token,
        session_id="s5",
        agent_id="a5",
        wall_clock_timeout=60,
        idle_timeout=1,
    )
    collected = [event async for event in executor.execute(_gen_with_cleanup())]

    assert cleanup_ran, "Inner generator finally-block must run on idle timeout"
    assert len(collected) == 3  # ProgressEvent + ErrorEvent + DoneEvent
    assert isinstance(collected[1], ErrorEvent)
    assert collected[1].error_code == "workflow_idle_timeout"
    assert isinstance(collected[2], DoneEvent)
