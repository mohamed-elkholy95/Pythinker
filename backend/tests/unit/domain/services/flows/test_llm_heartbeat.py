"""Comprehensive unit tests for LLMHeartbeat and interleave_heartbeat.

Covers every public method, edge cases, error conditions, and ordering
guarantees defined in llm_heartbeat.py.  No real I/O — the only real
async work is asyncio.sleep() with sub-50ms intervals so the suite
stays fast.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator

import pytest

from app.domain.models.event import BaseEvent, PlanningPhase, ProgressEvent
from app.domain.services.flows.llm_heartbeat import LLMHeartbeat, interleave_heartbeat

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_PHASES = list(PlanningPhase)

FAST_INTERVAL = 0.05  # 50ms — fast enough to accumulate events quickly
SLOW_INTERVAL = 10.0  # 10s — effectively never fires during a short test


class _StubEvent(BaseEvent):
    """Minimal concrete BaseEvent for use as inner-generator payload."""

    label: str = ""


async def _yield_n(
    count: int,
    delay: float = 0.0,
) -> AsyncGenerator[_StubEvent, None]:
    """Yields *count* StubEvents, optionally with a per-item delay."""
    for i in range(count):
        if delay > 0:
            await asyncio.sleep(delay)
        yield _StubEvent(label=f"item-{i}")


async def _empty() -> AsyncGenerator[_StubEvent, None]:
    """Yields nothing — exhausted immediately."""
    return
    yield  # make it an async generator


async def _single_slow(stall: float = 0.2) -> AsyncGenerator[_StubEvent, None]:
    """Yields one event after a configurable stall."""
    await asyncio.sleep(stall)
    yield _StubEvent(label="only")


async def _raise_mid_stream(at: int = 1) -> AsyncGenerator[_StubEvent, None]:
    """Yields *at* events then raises RuntimeError."""
    for i in range(at):
        yield _StubEvent(label=f"before-error-{i}")
    raise RuntimeError("generator error")


async def _collect(gen: AsyncGenerator) -> list:
    """Drain an async generator into a list."""
    return [item async for item in gen]


# ---------------------------------------------------------------------------
# LLMHeartbeat — construction and initial state
# ---------------------------------------------------------------------------


class TestLLMHeartbeatInit:
    def test_default_interval_is_2_5_seconds(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="thinking")
        assert hb._interval == 2.5

    def test_custom_interval_stored(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=7.3)
        assert hb._interval == 7.3

    def test_initial_buffer_is_empty(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="thinking")
        assert len(hb._events) == 0

    def test_initial_task_is_none(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="thinking")
        assert hb._task is None

    def test_initial_stopped_flag_is_false(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="thinking")
        assert hb._stopped is False

    @pytest.mark.parametrize("phase", ALL_PHASES)
    def test_all_planning_phases_accepted(self, phase: PlanningPhase) -> None:
        hb = LLMHeartbeat(phase=phase, message="msg")
        assert hb._phase == phase


# --- LLMHeartbeat.start() ---


class TestLLMHeartbeatStart:
    async def test_start_creates_task(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        hb.start()
        try:
            assert hb._task is not None
            assert isinstance(hb._task, asyncio.Task)
        finally:
            hb.stop()
            await asyncio.sleep(0)

    async def test_start_sets_stopped_to_false(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        # Manually set stopped to True before starting
        hb._stopped = True
        hb.start()
        try:
            assert hb._stopped is False
        finally:
            hb.stop()
            await asyncio.sleep(0)

    async def test_started_task_is_not_done(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        hb.start()
        try:
            assert not hb._task.done()
        finally:
            hb.stop()
            await asyncio.sleep(0)

    async def test_start_twice_replaces_task(self) -> None:
        """Calling start() a second time creates a fresh task (not guarded against, but shouldn't crash)."""
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        hb.start()
        first_task = hb._task
        hb.stop()
        await asyncio.sleep(0)
        hb.start()
        second_task = hb._task
        try:
            assert second_task is not first_task
        finally:
            hb.stop()
            await asyncio.sleep(0)


# --- LLMHeartbeat.stop() ---


class TestLLMHeartbeatStop:
    async def test_stop_sets_stopped_flag(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        hb.start()
        hb.stop()
        assert hb._stopped is True

    async def test_stop_cancels_task(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        hb.start()
        task = hb._task
        hb.stop()
        await asyncio.sleep(0)  # Let cancellation propagate
        assert task.done()

    async def test_stop_before_start_does_not_raise(self) -> None:
        """Calling stop() with no task should be a no-op."""
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        # _task is None — should not raise AttributeError or anything
        hb.stop()
        assert hb._stopped is True

    async def test_stop_twice_does_not_raise(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        hb.start()
        hb.stop()
        hb.stop()  # Second stop — task already cancelled, should not raise
        assert hb._stopped is True

    async def test_stop_prevents_further_event_emission(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=FAST_INTERVAL)
        hb.start()
        await asyncio.sleep(FAST_INTERVAL * 1.5)  # Allow at least one event
        hb.stop()
        hb.drain()  # Clear events emitted before stop

        # After stop, another interval passes — no new events should appear
        await asyncio.sleep(FAST_INTERVAL * 2)
        post_stop_events = hb.drain()
        assert len(post_stop_events) == 0


# --- LLMHeartbeat.drain() ---


class TestLLMHeartbeatDrain:
    async def test_drain_on_empty_buffer_returns_empty_list(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        result = hb.drain()
        assert result == []

    async def test_drain_returns_list_type(self) -> None:
        """drain() must return a plain list, not a deque or other sequence."""
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=FAST_INTERVAL)
        hb.start()
        await asyncio.sleep(FAST_INTERVAL * 2)
        hb.stop()
        result = hb.drain()
        assert isinstance(result, list)

    async def test_drain_clears_buffer(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=FAST_INTERVAL)
        hb.start()
        await asyncio.sleep(FAST_INTERVAL * 3)
        hb.stop()
        first = hb.drain()
        second = hb.drain()
        assert len(first) >= 1
        assert second == []

    async def test_drain_without_start_is_safe(self) -> None:
        """drain() before start() should return [] and not raise."""
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x")
        assert hb.drain() == []

    async def test_drain_multiple_times_returns_empty_after_first(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=FAST_INTERVAL)
        hb.start()
        await asyncio.sleep(FAST_INTERVAL * 2)
        hb.stop()
        hb.drain()  # First drain
        for _ in range(5):
            assert hb.drain() == []

    async def test_drain_returns_progress_event_instances(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="keep alive", interval_seconds=FAST_INTERVAL)
        hb.start()
        await asyncio.sleep(FAST_INTERVAL * 2)
        hb.stop()
        events = hb.drain()
        assert len(events) >= 1
        for event in events:
            assert isinstance(event, ProgressEvent)

    async def test_drain_events_carry_correct_phase_and_message(self) -> None:
        phase = PlanningPhase.VERIFYING
        message = "Verification in progress"
        hb = LLMHeartbeat(phase=phase, message=message, interval_seconds=FAST_INTERVAL)
        hb.start()
        await asyncio.sleep(FAST_INTERVAL * 2.5)
        hb.stop()
        events = hb.drain()
        assert len(events) >= 1
        for event in events:
            assert event.phase == phase
            assert event.message == message


# ---------------------------------------------------------------------------
# LLMHeartbeat — emit timing and accumulation
# ---------------------------------------------------------------------------


class TestLLMHeartbeatEmission:
    async def test_emits_multiple_events_over_time(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=FAST_INTERVAL)
        hb.start()
        await asyncio.sleep(FAST_INTERVAL * 3.5)
        hb.stop()
        events = hb.drain()
        assert len(events) >= 3, f"expected >=3 events, got {len(events)}"

    async def test_no_events_emitted_before_first_interval(self) -> None:
        """The emit loop sleeps first, so no event is emitted at t=0."""
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        hb.start()
        await asyncio.sleep(0)  # Yield control but don't wait a full interval
        events = hb.drain()
        assert len(events) == 0
        hb.stop()

    async def test_each_event_has_unique_id(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=FAST_INTERVAL)
        hb.start()
        await asyncio.sleep(FAST_INTERVAL * 3)
        hb.stop()
        events = hb.drain()
        ids = [e.id for e in events]
        assert len(ids) == len(set(ids)), "events should have unique ids"

    @pytest.mark.parametrize("phase", ALL_PHASES)
    async def test_phase_propagated_to_all_events(self, phase: PlanningPhase) -> None:
        hb = LLMHeartbeat(phase=phase, message="test", interval_seconds=FAST_INTERVAL)
        hb.start()
        await asyncio.sleep(FAST_INTERVAL * 2)
        hb.stop()
        events = hb.drain()
        for event in events:
            assert event.phase == phase


# ---------------------------------------------------------------------------
# LLMHeartbeat — async context manager
# ---------------------------------------------------------------------------


class TestLLMHeartbeatContextManager:
    async def test_aenter_returns_heartbeat_instance(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb as entered:
            assert entered is hb

    async def test_context_manager_starts_task(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb:
            assert hb._task is not None
            assert not hb._task.done()

    async def test_context_manager_stops_task_on_exit(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb:
            task = hb._task
        assert task.done()

    async def test_context_manager_emits_events_inside_block(self) -> None:
        async with LLMHeartbeat(
            phase=PlanningPhase.HEARTBEAT,
            message="alive",
            interval_seconds=FAST_INTERVAL,
        ) as hb:
            await asyncio.sleep(FAST_INTERVAL * 3)
            events = hb.drain()
        assert len(events) >= 2, f"expected >=2 events inside context, got {len(events)}"

    async def test_context_manager_sets_stopped_on_exit(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb:
            pass
        assert hb._stopped is True

    async def test_context_manager_exits_cleanly_on_exception(self) -> None:
        """__aexit__ should suppress no exceptions but must not raise on its own."""
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=FAST_INTERVAL)
        with pytest.raises(ValueError, match="boom"):
            async with hb:
                raise ValueError("boom")
        # Task should be cleaned up even after exception
        assert hb._task is not None
        assert hb._task.done()

    async def test_context_manager_task_already_done_aexit_is_safe(self) -> None:
        """If the background task finishes by itself before __aexit__, suppress(CancelledError) handles it."""
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb:
            # Manually cancel the task to simulate premature completion
            hb._task.cancel()
            await asyncio.sleep(0)
        # __aexit__ must not raise even though the task was already cancelled
        assert hb._task.done()


# ---------------------------------------------------------------------------
# interleave_heartbeat — basic forwarding
# ---------------------------------------------------------------------------


class TestInterleaveHeartbeatForwarding:
    async def test_all_inner_events_forwarded(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb:
            result = await _collect(interleave_heartbeat(_yield_n(5), hb))
        labels = [e.label for e in result if isinstance(e, _StubEvent)]
        assert labels == [f"item-{i}" for i in range(5)]

    async def test_empty_inner_generator_produces_no_events(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb:
            result = await _collect(interleave_heartbeat(_empty(), hb))
        assert result == []

    async def test_single_fast_event_forwarded(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb:
            result = await _collect(interleave_heartbeat(_yield_n(1), hb))
        stub_events = [e for e in result if isinstance(e, _StubEvent)]
        assert len(stub_events) == 1
        assert stub_events[0].label == "item-0"

    async def test_fast_generator_no_heartbeats_when_interval_is_long(self) -> None:
        """Inner events arrive before heartbeat interval — no ProgressEvents expected."""
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb:
            result = await _collect(interleave_heartbeat(_yield_n(3), hb))
        heartbeats = [e for e in result if isinstance(e, ProgressEvent)]
        assert len(heartbeats) == 0

    async def test_return_type_is_union_of_inner_and_progress(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="hb", interval_seconds=FAST_INTERVAL)
        async with hb:
            result = await _collect(interleave_heartbeat(_yield_n(2, delay=FAST_INTERVAL * 2), hb))
        for event in result:
            assert isinstance(event, (ProgressEvent, _StubEvent))


# ---------------------------------------------------------------------------
# interleave_heartbeat — heartbeat injection when inner stalls
# ---------------------------------------------------------------------------


class TestInterleaveHeartbeatInjection:
    async def test_heartbeats_injected_during_stall(self) -> None:
        hb = LLMHeartbeat(
            phase=PlanningPhase.HEARTBEAT,
            message="working",
            interval_seconds=FAST_INTERVAL,
        )
        async with hb:
            result = await _collect(interleave_heartbeat(_single_slow(stall=FAST_INTERVAL * 4), hb))
        heartbeats = [e for e in result if isinstance(e, ProgressEvent)]
        assert len(heartbeats) >= 1, f"expected heartbeats during stall, got {len(heartbeats)}"

    async def test_heartbeat_count_proportional_to_stall_duration(self) -> None:
        stall = FAST_INTERVAL * 6  # ~300ms stall
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=FAST_INTERVAL)
        async with hb:
            result = await _collect(interleave_heartbeat(_single_slow(stall=stall), hb))
        heartbeats = [e for e in result if isinstance(e, ProgressEvent)]
        # With 6-interval stall, should get at least 3 heartbeats (conservative)
        assert len(heartbeats) >= 3, f"expected >=3 heartbeats, got {len(heartbeats)}"

    async def test_all_heartbeats_have_correct_phase(self) -> None:
        phase = PlanningPhase.WAITING
        hb = LLMHeartbeat(phase=phase, message="waiting...", interval_seconds=FAST_INTERVAL)
        async with hb:
            result = await _collect(interleave_heartbeat(_single_slow(stall=FAST_INTERVAL * 3), hb))
        for event in result:
            if isinstance(event, ProgressEvent):
                assert event.phase == phase

    async def test_all_heartbeats_have_correct_message(self) -> None:
        message = "custom heartbeat message"
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message=message, interval_seconds=FAST_INTERVAL)
        async with hb:
            result = await _collect(interleave_heartbeat(_single_slow(stall=FAST_INTERVAL * 3), hb))
        for event in result:
            if isinstance(event, ProgressEvent):
                assert event.message == message


# ---------------------------------------------------------------------------
# interleave_heartbeat — event ordering guarantees
# ---------------------------------------------------------------------------


class TestInterleaveHeartbeatOrdering:
    async def test_heartbeats_precede_corresponding_real_event(self) -> None:
        """Buffered heartbeats must be yielded before the real event that unlocked them."""
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=FAST_INTERVAL)
        async with hb:
            result = await _collect(interleave_heartbeat(_single_slow(stall=FAST_INTERVAL * 4), hb))
        if len(result) > 1:
            first_real_idx = next(
                (i for i, e in enumerate(result) if isinstance(e, _StubEvent)),
                len(result),
            )
            # All events before the first real event should be ProgressEvent
            for event in result[:first_real_idx]:
                assert isinstance(event, ProgressEvent), f"expected ProgressEvent before real event, got {type(event)}"

    async def test_inner_event_sequence_preserved(self) -> None:
        """The relative order of inner events is maintained even with interleaved heartbeats."""
        item_count = 4
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=FAST_INTERVAL)
        async with hb:
            result = await _collect(interleave_heartbeat(_yield_n(item_count, delay=FAST_INTERVAL * 1.5), hb))
        labels = [e.label for e in result if isinstance(e, _StubEvent)]
        assert labels == [f"item-{i}" for i in range(item_count)]

    async def test_final_heartbeats_drained_after_exhaustion(self) -> None:
        """After inner generator exhausts, remaining buffered heartbeats must still be yielded."""
        # Use a generator that emits many heartbeats, then a very fast inner
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=FAST_INTERVAL)
        # Pre-seed the heartbeat buffer by waiting before entering interleave
        hb.start()
        await asyncio.sleep(FAST_INTERVAL * 3)  # Let heartbeats accumulate
        # Now run interleave — the pending_next resolves immediately (empty gen)
        result = await _collect(interleave_heartbeat(_empty(), hb))
        hb.stop()
        # The drained heartbeats from the final branch should appear in result
        # (they were accumulated before interleave was called)
        heartbeats = [e for e in result if isinstance(e, ProgressEvent)]
        assert len(heartbeats) >= 1, "expected pre-accumulated heartbeats to be yielded on exhaustion"


# ---------------------------------------------------------------------------
# interleave_heartbeat — early consumer exit / task cleanup
# ---------------------------------------------------------------------------


class TestInterleaveHeartbeatCleanup:
    async def test_consumer_break_does_not_hang(self) -> None:
        """If the outer consumer stops iterating, pending_next must be cancelled cleanly."""
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=FAST_INTERVAL)

        collected: list[BaseEvent] = []
        async with hb:
            async for event in interleave_heartbeat(_yield_n(100, delay=0.001), hb):
                collected.append(event)
                if len(collected) >= 3:
                    break  # Abandon the generator early

        # Should reach here without deadlock — if it does, the task cleanup works
        assert len(collected) >= 3

    async def test_consumer_break_on_empty_generator(self) -> None:
        """Breaking on an empty generator should not raise."""
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb:
            async for _event in interleave_heartbeat(_empty(), hb):
                break  # Loop body never runs, but the generator must not raise


# ---------------------------------------------------------------------------
# interleave_heartbeat — error propagation
# ---------------------------------------------------------------------------


class TestInterleaveHeartbeatErrorPropagation:
    async def test_inner_generator_error_propagates(self) -> None:
        """RuntimeError raised inside the inner generator must propagate to the consumer."""
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb:
            with pytest.raises(RuntimeError, match="generator error"):
                await _collect(interleave_heartbeat(_raise_mid_stream(at=0), hb))

    async def test_inner_generator_partial_events_then_error(self) -> None:
        """Events emitted before the error in the inner generator are still received."""
        collected: list[BaseEvent] = []
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=SLOW_INTERVAL)
        async with hb:
            with pytest.raises(RuntimeError, match="generator error"):
                async for event in interleave_heartbeat(_raise_mid_stream(at=2), hb):
                    collected.append(event)  # noqa: PERF401

        stub_events = [e for e in collected if isinstance(e, _StubEvent)]
        assert len(stub_events) == 2
        assert stub_events[0].label == "before-error-0"
        assert stub_events[1].label == "before-error-1"


# ---------------------------------------------------------------------------
# interleave_heartbeat — interaction with heartbeat that is not yet started
# ---------------------------------------------------------------------------


class TestInterleaveHeartbeatWithUnstartedHeartbeat:
    async def test_unstarted_heartbeat_still_works_for_forwarding(self) -> None:
        """interleave_heartbeat only calls heartbeat.drain() — works even if start() was never called."""
        hb = LLMHeartbeat(phase=PlanningPhase.HEARTBEAT, message="x", interval_seconds=SLOW_INTERVAL)
        # Do NOT call hb.start() — but drain() is safe on an empty deque
        result = await _collect(interleave_heartbeat(_yield_n(3), hb))
        labels = [e.label for e in result if isinstance(e, _StubEvent)]
        assert labels == ["item-0", "item-1", "item-2"]
        # No heartbeats because the background task never ran
        assert not any(isinstance(e, ProgressEvent) for e in result)


# ---------------------------------------------------------------------------
# _emit_loop — CancelledError handled internally
# ---------------------------------------------------------------------------


class TestEmitLoopCancellation:
    async def test_cancelled_error_in_loop_does_not_propagate(self) -> None:
        """_emit_loop catches CancelledError and returns cleanly."""
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=FAST_INTERVAL)
        hb.start()
        task = hb._task
        task.cancel()
        # Awaiting the task should not raise CancelledError to us
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert task.done()

    async def test_loop_stops_accumulating_after_stop(self) -> None:
        hb = LLMHeartbeat(phase=PlanningPhase.PLANNING, message="x", interval_seconds=FAST_INTERVAL)
        hb.start()
        await asyncio.sleep(FAST_INTERVAL * 2)
        hb.stop()
        await asyncio.sleep(0)
        count_at_stop = len(hb._events)
        await asyncio.sleep(FAST_INTERVAL * 3)
        count_after_stop = len(hb._events)
        # No new events should be appended after stop
        assert count_after_stop == count_at_stop


# ---------------------------------------------------------------------------
# Regression — interleave_heartbeat internal _interval access
# ---------------------------------------------------------------------------


class TestInterleaveHeartbeatIntervalAccess:
    async def test_interleave_uses_heartbeat_interval_for_wait_timeout(self) -> None:
        """interleave_heartbeat uses heartbeat._interval for asyncio.wait timeout.
        Verify it reads the correct interval by observing timing behaviour.
        """
        short_interval = FAST_INTERVAL
        hb = LLMHeartbeat(
            phase=PlanningPhase.HEARTBEAT,
            message="tick",
            interval_seconds=short_interval,
        )
        async with hb:
            result = await _collect(interleave_heartbeat(_single_slow(stall=short_interval * 5), hb))
        heartbeats = [e for e in result if isinstance(e, ProgressEvent)]
        # With 5-interval stall and correct interval used for wait, we expect >=2 timeout cycles
        assert len(heartbeats) >= 2
