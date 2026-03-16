"""Tests for enhanced contradiction detection (2026-02-13 plan Phase 5)."""

from app.domain.services.agents.guardrails import OutputGuardrails


def test_mutually_exclusive_detected() -> None:
    """'find X but not X' pattern is detected."""
    guardrails = OutputGuardrails(check_relevance=False, check_consistency=True)
    result = guardrails.analyze(
        output="The user wants to find Python but not Python in the results.",
        original_query="Test",
    )
    assert any(i.issue_type.value == "contradictory" for i in result.issues)


def test_impossible_numeric_top_zero() -> None:
    """'top 0' is detected as impossible."""
    guardrails = OutputGuardrails(check_relevance=False, check_consistency=True)
    result = guardrails.analyze(
        output="Get top 0 results from the search.",
        original_query="Test",
    )
    assert any("top 0" in (i.description or "").lower() for i in result.issues)


def test_impossible_range_detected() -> None:
    """'between 100 and 50' is detected."""
    guardrails = OutputGuardrails(check_relevance=False, check_consistency=True)
    result = guardrails.analyze(
        output="Value must be between 100 and 50.",
        original_query="Test",
    )
    assert any("range" in (i.description or "").lower() or "100" in (i.description or "") for i in result.issues)


def test_legitimate_contrast_not_flagged() -> None:
    """Normal contrast like 'X is fast but Y is not' should not trigger."""
    guardrails = OutputGuardrails(check_relevance=False, check_consistency=True)
    result = guardrails.analyze(
        output="Python is fast but Java is not as fast for this workload.",
        original_query="Test",
    )
    # Our new patterns don't match "X but not Y" when X != Y
    contradictory = [i for i in result.issues if i.issue_type.value == "contradictory"]
    assert len(contradictory) == 0
