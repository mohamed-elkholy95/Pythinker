from app.domain.services.agents.intent_classifier import (
    ClassificationContext,
    get_intent_classifier,
)
from app.domain.models.session import AgentMode


def test_blocks_agent_to_discuss_when_session_has_plan():
    """Follow-up in a planned session should NOT downgrade to DISCUSS."""
    classifier = get_intent_classifier()
    ctx = ClassificationContext(
        attachments=[],
        available_skills=[],
        conversation_length=10,
        is_follow_up=True,
        urls=[],
        mcp_tools=[],
        session_mode=AgentMode.AGENT,
        session_had_plan=True,
        session_plan_title="AI Agent Frameworks Research",
    )
    result = classifier.classify_with_context(
        "Can you expand on the comparison?", ctx
    )
    assert result.mode == AgentMode.AGENT, (
        f"Expected AGENT but got {result.mode} — guard failed"
    )
    assert "BLOCKED" in " ".join(result.reasons)


def test_allows_discuss_when_no_plan():
    """Fresh session with no plan should allow DISCUSS mode."""
    classifier = get_intent_classifier()
    ctx = ClassificationContext(
        attachments=[],
        available_skills=[],
        conversation_length=0,
        is_follow_up=False,
        urls=[],
        mcp_tools=[],
        session_mode=AgentMode.AGENT,
        session_had_plan=False,
    )
    result = classifier.classify_with_context("hello", ctx)
    assert result.mode == AgentMode.DISCUSS


def test_continuation_phrase_in_planned_session():
    """Continuation phrases in planned sessions should stay AGENT."""
    classifier = get_intent_classifier()
    ctx = ClassificationContext(
        attachments=[],
        available_skills=[],
        conversation_length=5,
        is_follow_up=True,
        urls=[],
        mcp_tools=[],
        session_mode=AgentMode.AGENT,
        session_had_plan=True,
        session_plan_title="Research Task",
    )
    result = classifier.classify_with_context("go ahead", ctx)
    assert result.mode == AgentMode.AGENT
    assert result.intent == "continuation"
