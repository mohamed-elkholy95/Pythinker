"""Tests for LLMHeartbeat periodic event emitter."""
from __future__ import annotations

import asyncio

import pytest

from app.domain.models.event import PlanningPhase, ProgressEvent
from app.domain.services.flows.llm_heartbeat import LLMHeartbeat


@pytest.mark.asyncio
async def test_heartbeat_emits_events_while_waiting() -> None:
    """Heartbeat emits at least 2 events after sleeping for 3+ intervals."""
    heartbeat = LLMHeartbeat(
        phase=PlanningPhase.PLANNING,
        message="Generating plan...",
        interval_seconds=0.1,
    )
    heartbeat.start()
    await asyncio.sleep(0.35)
    heartbeat.stop()
    events = heartbeat.drain()
    assert len(events) >= 2, f"Expected >=2 events, got {len(events)}"


@pytest.mark.asyncio
async def test_heartbeat_stops_cleanly() -> None:
    """After stop(), the background task is cancelled and no more events are produced."""
    heartbeat = LLMHeartbeat(
        phase=PlanningPhase.PLANNING,
        message="Generating plan...",
        interval_seconds=0.1,
    )
    heartbeat.start()
    await asyncio.sleep(0.15)
    heartbeat.stop()
    # Allow the event loop to process the cancellation
    await asyncio.sleep(0.0)

    events_at_stop = heartbeat.drain()

    # Sleep past another potential interval — no new events should accumulate
    await asyncio.sleep(0.2)
    events_after_stop = heartbeat.drain()

    assert len(events_after_stop) == 0, (
        f"Expected 0 events after stop, got {len(events_after_stop)}"
    )
    # Sanity: we did receive events before stopping
    assert len(events_at_stop) >= 1, (
        f"Expected >=1 events before stop, got {len(events_at_stop)}"
    )


@pytest.mark.asyncio
async def test_heartbeat_as_context_manager() -> None:
    """async with LLMHeartbeat(...) starts and stops automatically."""
    async with LLMHeartbeat(
        phase=PlanningPhase.PLANNING,
        message="Generating plan...",
        interval_seconds=0.1,
    ) as heartbeat:
        await asyncio.sleep(0.35)
        events = heartbeat.drain()

    assert len(events) >= 2, f"Expected >=2 events inside context, got {len(events)}"
    # After exiting the context the task should be done
    assert heartbeat._task is not None
    assert heartbeat._task.done()


@pytest.mark.asyncio
async def test_drain_clears_buffer() -> None:
    """drain() returns buffered events and leaves the buffer empty afterwards."""
    heartbeat = LLMHeartbeat(
        phase=PlanningPhase.PLANNING,
        message="Generating plan...",
        interval_seconds=0.1,
    )
    heartbeat.start()
    await asyncio.sleep(0.35)
    heartbeat.stop()

    first_drain = heartbeat.drain()
    second_drain = heartbeat.drain()

    assert len(first_drain) >= 2, f"Expected >=2 events on first drain, got {len(first_drain)}"
    assert len(second_drain) == 0, f"Expected 0 events on second drain, got {len(second_drain)}"


@pytest.mark.asyncio
async def test_all_events_have_correct_phase() -> None:
    """Every event emitted by the heartbeat carries the specified phase."""
    phase = PlanningPhase.VERIFYING
    message = "Checking plan quality..."

    async with LLMHeartbeat(
        phase=phase,
        message=message,
        interval_seconds=0.1,
    ) as heartbeat:
        await asyncio.sleep(0.35)
        events = heartbeat.drain()

    assert len(events) >= 2, f"Expected >=2 events, got {len(events)}"
    for event in events:
        assert isinstance(event, ProgressEvent)
        assert event.phase == phase, f"Expected phase {phase}, got {event.phase}"
        assert event.message == message, f"Expected message '{message}', got '{event.message}'"
