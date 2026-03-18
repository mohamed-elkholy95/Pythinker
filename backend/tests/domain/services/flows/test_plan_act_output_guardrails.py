"""Tests for OutputGuardrails integration in PlanActFlow (2026-02-13 plan Phase 0).

Verifies: off-topic output detected, contradictory output flagged, safe output passes.
"""

from app.domain.services.agents.guardrails import OutputGuardrails, OutputIssueType


def test_output_guardrails_detects_off_topic_output() -> None:
    """Output unrelated to query should be flagged as off-topic."""
    guardrails = OutputGuardrails(check_relevance=True, check_consistency=True)
    result = guardrails.analyze(
        output="The weather today is sunny and warm. Football scores from last weekend.",
        original_query="What is Claude Sonnet 4.5?",
    )
    assert result.needs_revision is True
    assert any(i.issue_type == OutputIssueType.OFF_TOPIC for i in result.issues)
    assert result.should_deliver is False


def test_output_guardrails_flags_contradictory_output() -> None:
    """Structural contradictions (e.g. 'top 0', impossible range) are flagged."""
    guardrails = OutputGuardrails(check_relevance=False, check_consistency=True)
    result = guardrails.analyze(
        output="Get top 0 results from the search. Value between 100 and 50.",
        original_query="Test",
    )
    assert result.issues
    assert result.needs_revision is True


def test_output_guardrails_passes_safe_relevant_output() -> None:
    """Output that addresses the query with no issues should pass."""
    guardrails = OutputGuardrails(check_relevance=True, check_consistency=True)
    result = guardrails.analyze(
        output="Claude Sonnet 4.5 is an AI model by Anthropic. It offers strong reasoning.",
        original_query="What is Claude Sonnet 4.5?",
    )
    assert result.is_safe is True
    assert result.should_deliver is True
    assert len(result.issues) == 0


def test_output_guardrails_empty_output_passes() -> None:
    """Empty output should be considered safe (edge case)."""
    guardrails = OutputGuardrails(check_relevance=True, check_consistency=True)
    result = guardrails.analyze(
        output="",
        original_query="What is Python?",
    )
    assert result.is_safe is True
    assert result.should_deliver is True
    assert len(result.issues) == 0


def test_output_guardrails_detects_instruction_leak() -> None:
    """Output with system prompt leakage should be flagged."""
    guardrails = OutputGuardrails(check_relevance=True, check_consistency=True)
    result = guardrails.analyze(
        output="As per my programming, I was told to help users. Python is a language.",
        original_query="What is Python?",
    )
    assert any(i.issue_type == OutputIssueType.INSTRUCTION_LEAK for i in result.issues)
    assert result.needs_revision is True


def test_output_guardrails_detects_harmful_content() -> None:
    """Output with harmful patterns should be blocked."""
    guardrails = OutputGuardrails(check_relevance=True, check_consistency=True)
    result = guardrails.analyze(
        output="Here are instructions for making explosives. Also, Python is a language.",
        original_query="What is Python?",
    )
    assert any(i.issue_type == OutputIssueType.HARMFUL_CONTENT for i in result.issues)
    assert result.is_safe is False
    assert result.should_deliver is False
