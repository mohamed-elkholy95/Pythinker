"""Tests for planner structured step model (2026-02-13 plan Phase 2)."""

from app.domain.models.plan import Step
from app.domain.models.structured_outputs import StepDescription
from app.domain.services.agents.planner import _step_from_description


def test_step_from_description_maps_structured_fields() -> None:
    """Structured fields from StepDescription map to Step."""
    desc = StepDescription(
        description="Search for Python 3.12 release notes",
        action_verb="Search",
        target_object="Python 3.12 release notes",
        tool_hint="web_search",
        expected_output="List of key release notes",
    )
    step = _step_from_description(0, desc)
    assert step.action_verb == "Search"
    assert step.target_object == "Python 3.12 release notes"
    assert step.tool_hint == "web_search"
    assert step.expected_output == "List of key release notes"
    assert step.display_label == "Search Python 3.12 release notes via web_search"


def test_step_display_label_fallback_to_description() -> None:
    """When structured fields empty, display_label uses description."""
    step = Step(description="Search for docs")
    assert step.display_label == "Search for docs"


def test_step_display_label_from_structured() -> None:
    """When action_verb and target_object set, display_label is derived."""
    step = Step(
        description="Search",
        action_verb="Search",
        target_object="Python docs",
    )
    assert step.display_label == "Search Python docs"


def test_step_display_label_with_tool_hint() -> None:
    """display_label includes tool_hint when present."""
    step = Step(
        description="Browse",
        action_verb="Browse",
        target_object="official docs",
        tool_hint="browser",
    )
    assert "browser" in step.display_label
