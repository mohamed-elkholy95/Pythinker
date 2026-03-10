"""Tests for failing steps that produce no meaningful result."""

from __future__ import annotations

from app.domain.models.plan import ExecutionStatus, Step, StepType
from app.domain.services.flows.headline_extractor import extract_headline, is_no_result_headline


def test_is_no_result_headline_detects_empty_result() -> None:
    headline = extract_headline("", tool_name="Research agent observability")
    assert is_no_result_headline(headline)


def test_is_no_result_headline_detects_whitespace_result() -> None:
    headline = extract_headline("   ", tool_name="Research agent observability")
    assert is_no_result_headline(headline)


def test_is_no_result_headline_rejects_valid_result() -> None:
    headline = extract_headline("Found 10 trending repos on GitHub", tool_name="Research trends")
    assert not is_no_result_headline(headline)


def test_is_no_result_headline_rejects_browser_headline() -> None:
    headline = extract_headline(
        "Navigated to https://example.com\nPage title: Dashboard",
        tool_name="browser_navigate",
    )
    assert not is_no_result_headline(headline)


def test_is_no_result_headline_with_none_input() -> None:
    assert is_no_result_headline(None)  # type: ignore[arg-type]


def test_is_no_result_headline_with_empty_string() -> None:
    assert is_no_result_headline("")


def test_is_no_result_headline_with_whitespace_only() -> None:
    assert is_no_result_headline("   ")


def test_is_no_result_headline_with_tool_returned_no_result() -> None:
    assert is_no_result_headline("web_search returned no result")


def test_is_no_result_headline_with_generic_returned_no_result() -> None:
    assert is_no_result_headline("Tool returned no result")


def test_is_no_result_headline_case_insensitive() -> None:
    assert is_no_result_headline("Research RETURNED NO RESULT")


def test_successful_research_step_with_no_result_should_fail() -> None:
    """A research step that completes with empty result should be downgraded."""
    step = Step(id="1", description="Research agent observability")
    step.success = True
    step.status = ExecutionStatus.COMPLETED
    step.result = ""

    headline = extract_headline(step.result or "", tool_name=step.description or "")
    assert is_no_result_headline(headline)
    # The plan_act.py code will use this to downgrade to FAILED


def test_research_step_type_detected_for_gating() -> None:
    """Steps with step_type EXECUTION and 'research' in description should be gated."""
    step = Step(
        id="2",
        description="Research current ML trends",
        step_type=StepType.EXECUTION,
    )
    step.success = True
    step.status = ExecutionStatus.COMPLETED
    step.result = ""

    headline = extract_headline(step.result or "", tool_name=step.description or "")
    assert is_no_result_headline(headline)

    # Verify step matches gating criteria
    desc_lower = (step.description or "").lower()
    step_type_lower = str(step.step_type.value).lower()
    should_gate = "research" in desc_lower or step_type_lower in {
        "research",
        "analysis",
        "execution",
    }
    assert should_gate


def test_delivery_step_with_no_result_not_gated() -> None:
    """Delivery steps should NOT be gated even with empty results."""
    step = Step(
        id="3",
        description="Deliver final report",
        step_type=StepType.DELIVERY,
    )
    step.success = True
    step.status = ExecutionStatus.COMPLETED
    step.result = ""

    desc_lower = (step.description or "").lower()
    step_type_lower = str(step.step_type.value).lower()
    should_gate = "research" in desc_lower or step_type_lower in {
        "research",
        "analysis",
        "execution",
    }
    # delivery is not in the gated set and description has no "research"
    assert not should_gate
