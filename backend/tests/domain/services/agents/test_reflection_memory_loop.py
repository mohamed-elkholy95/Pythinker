"""Smoke tests for Phase 3: ReflectionAgent memory write-back (MemoryType.TASK_OUTCOME).

Prior bug: ReflectionAgent.reflect() writes to MemoryType.TASK_OUTCOME, but was only
wired in the deprecated PlanActGraphFlow. Default PlanActFlow never called reflect().

Fix: ReflectionAgent is now initialised in PlanActFlow.__init__ and invoked before
transitioning to SUMMARIZING (when feature_meta_cognition_enabled=True).

These tests verify:
- reflect() calls memory_service.store_memory() with MemoryType.TASK_OUTCOME.
- The memory write-back is skipped gracefully when memory_service is None.
- should_reflect() triggers correctly on error/stall conditions.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.plan import Plan, Step
from app.domain.models.reflection import (
    ProgressMetrics,
    ReflectionConfig,
    ReflectionDecision,
    ReflectionResult,
    ReflectionTriggerType,
)
from app.domain.services.agents.reflection import ReflectionAgent


def _make_minimal_plan() -> Plan:
    plan = MagicMock(spec=Plan)
    plan.steps = [MagicMock(spec=Step, description="step A")]
    plan.goal = "Test goal"
    plan.title = "Test Plan"
    return plan


def _make_reflection_result(decision: ReflectionDecision = ReflectionDecision.CONTINUE) -> ReflectionResult:
    """Build a valid ReflectionResult with all required fields."""
    return ReflectionResult(
        decision=decision,
        confidence=0.9,
        progress_assessment="Progress is on track",
        summary="All good",
        suggestions=[],
    )


def _make_reflection_agent(
    memory_service=None,
    user_id: str | None = None,
) -> ReflectionAgent:
    llm = MagicMock()
    llm.model_name = "test-model"

    json_parser = AsyncMock()
    json_parser.parse = AsyncMock(
        return_value={
            "decision": "continue",
            "confidence": 0.9,
            "progress_assessment": "On track",
            "summary": "Progress is fine",
            "suggestions": [],
        }
    )

    return ReflectionAgent(
        llm=llm,
        json_parser=json_parser,
        config=ReflectionConfig(enabled=True),
        memory_service=memory_service,
        user_id=user_id,
        session_id="test-session-001",
    )


@pytest.mark.asyncio
async def test_reflect_calls_store_memory_with_task_outcome_type():
    """reflect() must call store_memory() with MemoryType.TASK_OUTCOME when memory_service is set."""
    mock_memory = AsyncMock()
    mock_memory.store_memory = AsyncMock(return_value=None)

    agent = _make_reflection_agent(memory_service=mock_memory, user_id="user-123")
    agent._do_reflection = AsyncMock(return_value=_make_reflection_result())

    progress = ProgressMetrics(steps_completed=2, total_steps=5)
    plan = _make_minimal_plan()

    events = []
    async for event in agent.reflect(
        goal="Complete the task",
        plan=plan,
        progress=progress,
        trigger_type=ReflectionTriggerType.STEP_INTERVAL,
    ):
        events.append(event)

    # Verify memory write-back occurred
    mock_memory.store_memory.assert_awaited_once()
    call_kwargs = mock_memory.store_memory.call_args.kwargs

    from app.domain.models.long_term_memory import MemoryType

    assert call_kwargs.get("memory_type") == MemoryType.TASK_OUTCOME
    assert call_kwargs.get("user_id") == "user-123"
    assert call_kwargs.get("session_id") == "test-session-001"
    assert "reflection" in (call_kwargs.get("tags") or [])


@pytest.mark.asyncio
async def test_reflect_skips_memory_write_when_no_memory_service():
    """reflect() must not crash when memory_service is None."""
    agent = _make_reflection_agent(memory_service=None, user_id="user-123")
    agent._do_reflection = AsyncMock(return_value=_make_reflection_result())

    progress = ProgressMetrics(steps_completed=1, total_steps=3)
    plan = _make_minimal_plan()

    events = []
    async for event in agent.reflect(
        goal="Do the thing",
        plan=plan,
        progress=progress,
        trigger_type=ReflectionTriggerType.STEP_INTERVAL,
    ):
        events.append(event)

    from app.domain.models.event import ReflectionEvent, ReflectionStatus

    assert any(
        isinstance(e, ReflectionEvent) and e.status == ReflectionStatus.COMPLETED
        for e in events
    )


def test_should_reflect_returns_none_when_disabled():
    """should_reflect() returns None when ReflectionConfig.enabled is False."""
    agent = _make_reflection_agent()
    agent.config.enabled = False

    progress = ProgressMetrics(steps_completed=5, total_steps=5)
    trigger = agent.should_reflect(progress)
    assert trigger is None


def test_should_reflect_triggers_after_error():
    """should_reflect() triggers AFTER_ERROR when last_had_error=True."""
    agent = _make_reflection_agent()
    # Ensure config allows error-based triggering
    agent.config.trigger.reflect_after_error = True
    # Reset last reflection step so min_steps_between_reflections is satisfied
    agent._last_reflection_step = -10

    progress = ProgressMetrics(steps_completed=3, total_steps=10)
    trigger = agent.should_reflect(progress, last_had_error=True)
    # Either AFTER_ERROR or HIGH_ERROR_RATE are valid error-based triggers
    assert trigger in (ReflectionTriggerType.AFTER_ERROR, ReflectionTriggerType.HIGH_ERROR_RATE)


@pytest.mark.asyncio
async def test_reflect_increments_reflection_count():
    """reflect() increments _reflection_count after each invocation."""
    agent = _make_reflection_agent()
    agent._do_reflection = AsyncMock(return_value=_make_reflection_result())

    initial_count = agent._reflection_count
    progress = ProgressMetrics(steps_completed=2, total_steps=5)
    plan = _make_minimal_plan()

    async for _ in agent.reflect(
        goal="Goal",
        plan=plan,
        progress=progress,
        trigger_type=ReflectionTriggerType.STEP_INTERVAL,
    ):
        pass

    assert agent._reflection_count == initial_count + 1
