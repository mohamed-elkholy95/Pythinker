import pytest
from unittest.mock import MagicMock
from app.domain.services.conversation_context_service import ConversationContextService
from app.domain.models.event import (
    PlanEvent,
    PlanStatus,
    ThoughtEvent,
    ThoughtStatus,
    ReflectionEvent,
    ReflectionStatus,
    VerificationEvent,
    VerificationStatus,
    ComprehensionEvent,
    ModeChangeEvent,
    TaskRecreationEvent,
)
from app.domain.models.plan import Plan, Step
from app.domain.models.conversation_context import TurnEventType, TurnRole


@pytest.fixture
def service():
    """Minimal ConversationContextService for extraction tests."""
    svc = ConversationContextService.__new__(ConversationContextService)
    settings = MagicMock()
    settings.conversation_context_min_content_length = 10
    svc._settings = settings
    svc._seen_hashes = set()
    return svc


def _make_plan_event():
    plan = Plan(
        title="Top 3 AI Frameworks",
        steps=[
            Step(description="Research frameworks"),
            Step(description="Compare features"),
        ],
    )
    return PlanEvent(plan=plan, status=PlanStatus.CREATED)


def test_extract_plan_event(service):
    event = _make_plan_event()
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is not None
    assert turn.role == TurnRole.PLAN_SUMMARY
    assert turn.event_type == TurnEventType.PLAN
    assert "Top 3 AI Frameworks" in turn.content
    assert "Research frameworks" in turn.content


def test_extract_plan_event_skips_updated(service):
    plan = Plan(title="Test Plan", steps=[])
    event = PlanEvent(plan=plan, status=PlanStatus.UPDATED)
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is None


def test_extract_thought_event_final(service):
    event = ThoughtEvent(
        status=ThoughtStatus.CHAIN_COMPLETE,
        thought_type="analysis",
        content="The data shows clear trends in framework adoption rates",
        confidence=0.85,
        is_final=True,
    )
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is not None
    assert turn.role == TurnRole.THOUGHT
    assert turn.event_type == TurnEventType.THOUGHT


def test_extract_thought_event_skips_non_final(service):
    event = ThoughtEvent(
        status=ThoughtStatus.THINKING,
        thought_type="analysis",
        content="Still processing the data points from multiple sources",
        is_final=False,
    )
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is None


def test_extract_reflection_event(service):
    event = ReflectionEvent(
        status=ReflectionStatus.COMPLETED,
        decision="continue",
        summary="All steps completed successfully so far",
        confidence=0.9,
    )
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is not None
    assert turn.event_type == TurnEventType.REFLECTION
    assert turn.role == TurnRole.ASSISTANT
    assert "Reflection" in turn.content


def test_extract_verification_event(service):
    event = VerificationEvent(
        status=VerificationStatus.PASSED,
        verdict="pass",
        summary="Plan is well-structured and achievable",
        confidence=0.95,
    )
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is not None
    assert turn.event_type == TurnEventType.VERIFICATION
    assert turn.role == TurnRole.ASSISTANT
    assert "Verification" in turn.content


def test_extract_comprehension_event(service):
    event = ComprehensionEvent(
        original_length=500,
        summary="User wants a detailed analysis of top AI frameworks with benchmarks",
        key_requirements=["benchmarks", "comparison table"],
    )
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is not None
    assert turn.event_type == TurnEventType.COMPREHENSION
    assert turn.role == TurnRole.ASSISTANT
    assert "comprehension" in turn.content.lower()


def test_extract_mode_change_event(service):
    event = ModeChangeEvent(mode="discuss", reason="follow-up question detected")
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is not None
    assert turn.event_type == TurnEventType.MODE_CHANGE
    assert "discuss" in turn.content


def test_extract_task_recreation_event(service):
    event = TaskRecreationEvent(
        reason="New requirements discovered after comprehension",
        previous_step_count=3,
        new_step_count=5,
        preserved_findings=2,
    )
    turn = service.extract_turn_from_event(event, "s1", "u1", 1)
    assert turn is not None
    assert turn.event_type == TurnEventType.TASK_RECREATION
    assert turn.role == TurnRole.ASSISTANT
    assert "recreated" in turn.content.lower()
