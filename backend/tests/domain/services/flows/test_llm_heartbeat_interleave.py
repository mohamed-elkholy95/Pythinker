"""Tests for interleave_heartbeat() — ensures heartbeats are emitted
even when the inner async generator stalls on long LLM calls."""

from __future__ import annotations

import asyncio
import collections.abc

import pytest

from app.domain.models.event import BaseEvent, PlanningPhase, ProgressEvent
from app.domain.services.flows.llm_heartbeat import LLMHeartbeat, interleave_heartbeat


class _DummyEvent(BaseEvent):
    """Minimal event subclass for testing."""

    label: str = ""


async def _fast_generator(count: int = 3) -> collections.abc.AsyncGenerator[_DummyEvent, None]:
    """Yields events immediately — no stalling."""
    for i in range(count):
        yield _DummyEvent(label=f"event-{i}")


async def _slow_generator(
    stall_seconds: float = 0.5,
    count: int = 2,
) -> collections.abc.AsyncGenerator[_DummyEvent, None]:
    """Simulates a stalled LLM call — waits before yielding."""
    for i in range(count):
        await asyncio.sleep(stall_seconds)
        yield _DummyEvent(label=f"slow-{i}")


async def _empty_generator() -> collections.abc.AsyncGenerator[_DummyEvent, None]:
    """Yields nothing."""
    return
    yield  # noqa: RET504 — makes it an async generator


@pytest.mark.asyncio
async def test_interleave_fast_generator_no_heartbeats() -> None:
    """When inner generator is fast, heartbeats should not appear."""
    hb = LLMHeartbeat(
        phase=PlanningPhase.HEARTBEAT,
        message="working...",
        interval_seconds=10.0,  # Long interval — should never fire
    )
    events: list[BaseEvent] = []
    async with hb:
        async for event in interleave_heartbeat(_fast_generator(), hb):
            events.append(event)

    labels = [e.label for e in events if isinstance(e, _DummyEvent)]
    assert labels == ["event-0", "event-1", "event-2"]
    # No heartbeats expected since generator was fast
    heartbeats = [e for e in events if isinstance(e, ProgressEvent)]
    assert len(heartbeats) == 0


@pytest.mark.asyncio
async def test_interleave_slow_generator_emits_heartbeats() -> None:
    """When inner generator stalls, heartbeats should be interleaved."""
    hb = LLMHeartbeat(
        phase=PlanningPhase.HEARTBEAT,
        message="working...",
        interval_seconds=0.1,  # Fire every 100ms
    )
    events: list[BaseEvent] = []
    async with hb:
        async for event in interleave_heartbeat(_slow_generator(stall_seconds=0.35, count=2), hb):
            events.append(event)

    # Should have at least 1 heartbeat per stall period
    heartbeats = [e for e in events if isinstance(e, ProgressEvent)]
    assert len(heartbeats) >= 2, f"Expected >=2 heartbeats, got {len(heartbeats)}"

    # All heartbeats should have the correct phase
    for hb_event in heartbeats:
        assert hb_event.phase == PlanningPhase.HEARTBEAT
        assert hb_event.message == "working..."

    # Real events should still be present
    labels = [e.label for e in events if isinstance(e, _DummyEvent)]
    assert labels == ["slow-0", "slow-1"]


@pytest.mark.asyncio
async def test_interleave_empty_generator() -> None:
    """Empty generator should complete cleanly with no events."""
    hb = LLMHeartbeat(
        phase=PlanningPhase.HEARTBEAT,
        message="working...",
        interval_seconds=10.0,
    )
    events: list[BaseEvent] = []
    async with hb:
        async for event in interleave_heartbeat(_empty_generator(), hb):
            events.append(event)

    assert len(events) == 0


@pytest.mark.asyncio
async def test_interleave_preserves_event_order() -> None:
    """Heartbeats should appear BEFORE their corresponding real event."""
    hb = LLMHeartbeat(
        phase=PlanningPhase.HEARTBEAT,
        message="working...",
        interval_seconds=0.05,  # Very fast heartbeat
    )
    events: list[BaseEvent] = []
    async with hb:
        async for event in interleave_heartbeat(_slow_generator(stall_seconds=0.2, count=1), hb):
            events.append(event)

    # Pattern should be: [heartbeat, ..., heartbeat, real_event]
    # The last non-heartbeat event should be the real event
    real_events = [e for e in events if isinstance(e, _DummyEvent)]
    assert len(real_events) == 1
    assert real_events[0].label == "slow-0"

    # At least one heartbeat should precede the real event
    if len(events) > 1:
        first_real_idx = next(i for i, e in enumerate(events) if isinstance(e, _DummyEvent))
        heartbeats_before = [e for e in events[:first_real_idx] if isinstance(e, ProgressEvent)]
        assert len(heartbeats_before) >= 1
