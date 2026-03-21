import asyncio

import pytest

from app.domain.models.event import PlanningPhase, ProgressEvent
from app.domain.services.flows.tool_executor import ToolExecutorWithHeartbeat


@pytest.mark.asyncio
async def test_heartbeat_emitted_during_slow_tool():
    """Heartbeat ProgressEvents should be emitted during tool execution > interval."""
    executor = ToolExecutorWithHeartbeat(interval_seconds=0.3)

    async def slow_tool():
        await asyncio.sleep(1.0)
        return {"result": "done"}

    events = [event async for event in executor.execute("browser_navigate", slow_tool)]

    heartbeats = [e for e in events if isinstance(e, ProgressEvent)]
    assert len(heartbeats) >= 2, f"Expected >=2 heartbeats, got {len(heartbeats)}"
    assert all(e.phase == PlanningPhase.TOOL_EXECUTING for e in heartbeats)


@pytest.mark.asyncio
async def test_tool_result_yielded_after_heartbeats():
    """The actual tool result should be yielded alongside heartbeats."""
    executor = ToolExecutorWithHeartbeat(interval_seconds=0.2)

    async def fast_tool():
        await asyncio.sleep(0.5)
        return {"result": "ok"}

    events = [event async for event in executor.execute("search", fast_tool)]

    # Should have heartbeats + the tool result
    non_heartbeats = [e for e in events if not isinstance(e, ProgressEvent)]
    assert len(non_heartbeats) == 1
    assert non_heartbeats[0] == {"result": "ok"}


@pytest.mark.asyncio
async def test_fast_tool_no_heartbeats():
    """A tool that completes faster than the heartbeat interval should yield no heartbeats."""
    executor = ToolExecutorWithHeartbeat(interval_seconds=5.0)

    async def instant_tool():
        return "instant"

    events = [event async for event in executor.execute("quick_tool", instant_tool)]

    heartbeats = [e for e in events if isinstance(e, ProgressEvent)]
    assert len(heartbeats) == 0
    assert events == ["instant"]
