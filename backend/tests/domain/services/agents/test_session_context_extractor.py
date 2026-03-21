from unittest.mock import MagicMock

from app.domain.models.event import PlanEvent, PlanStatus, StepEvent, StepStatus
from app.domain.models.plan import Plan, Step
from app.domain.services.agents.session_context_extractor import (
    SessionContextExtractor,
    SessionExecutionContext,
)


def _make_session(events=None, title=None):
    session = MagicMock()
    session.events = events or []
    session.title = title or "Test Session"
    return session


def _make_plan_event(title: str = "AI Frameworks Research") -> PlanEvent:
    step = Step(description="Search web")
    plan = Plan(title=title, steps=[step])
    return PlanEvent(plan=plan, status=PlanStatus.CREATED)


def _make_step_completed() -> StepEvent:
    step = Step(description="Search web")
    return StepEvent(step=step, status=StepStatus.COMPLETED)


def test_extract_session_with_plan():
    plan_event = _make_plan_event("AI Frameworks Research")
    session = _make_session([plan_event, _make_step_completed()])
    ctx = SessionContextExtractor.extract(session)
    assert ctx.had_plan is True
    assert ctx.plan_title == "AI Frameworks Research"
    assert ctx.completed_steps == 1
    assert len(ctx.plan_steps) == 1


def test_extract_session_without_plan():
    session = _make_session([])
    ctx = SessionContextExtractor.extract(session)
    assert ctx.had_plan is False
    assert ctx.plan_title is None
    assert ctx.completed_steps == 0


def test_to_plan_summary_formatted():
    plan_event = _make_plan_event("Compare Frameworks")
    session = _make_session([plan_event])
    ctx = SessionContextExtractor.extract(session)
    summary = ctx.to_plan_summary()
    assert "Compare Frameworks" in summary
    assert "Search web" in summary
    assert "0/1" in summary


def test_to_plan_summary_empty_when_no_plan():
    session = _make_session([])
    ctx = SessionContextExtractor.extract(session)
    assert ctx.to_plan_summary() == ""


def test_topic_falls_back_to_session_title():
    session = _make_session([], title="My Custom Title")
    ctx = SessionContextExtractor.extract(session)
    assert ctx.topic == "My Custom Title"
