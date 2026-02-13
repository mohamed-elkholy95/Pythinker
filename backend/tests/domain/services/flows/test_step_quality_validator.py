"""Tests for StepQualityValidator (2026-02-13 plan Phase 2)."""

from unittest.mock import patch

from app.domain.models.plan import Step
from app.domain.services.flows.step_quality_validator import (
    repair_step_from_description,
    validate_step_quality,
)


def test_validate_step_quality_passes_with_structured_fields() -> None:
    """Step with action_verb and target_object passes."""
    step = Step(
        description="Search for Python docs",
        action_verb="Search",
        target_object="Python docs",
    )
    with patch("app.domain.services.flows.step_quality_validator.get_settings") as m:
        m.return_value.enable_structured_step_model = True
        passed, violations = validate_step_quality(step)
    assert passed is True
    assert violations == []


def test_validate_step_quality_empty_verb_violation() -> None:
    """Step without action_verb when enabled fails."""
    step = Step(description="Search for docs", target_object="docs")
    with patch("app.domain.services.flows.step_quality_validator.get_settings") as m:
        m.return_value.enable_structured_step_model = True
        passed, violations = validate_step_quality(step)
    assert passed is False
    assert "empty_verb" in violations


def test_validate_step_quality_banned_verb_violation() -> None:
    """Step with banned verb fails."""
    step = Step(
        description="Handle the request",
        action_verb="handle",
        target_object="request",
    )
    with patch("app.domain.services.flows.step_quality_validator.get_settings") as m:
        m.return_value.enable_structured_step_model = True
        passed, violations = validate_step_quality(step)
    assert passed is False
    assert "banned_verb" in violations


def test_validate_step_quality_skipped_when_disabled() -> None:
    """When enable_structured_step_model is False, validation passes."""
    step = Step(description="Do something")
    with patch("app.domain.services.flows.step_quality_validator.get_settings") as m:
        m.return_value.enable_structured_step_model = False
        passed, violations = validate_step_quality(step)
    assert passed is True
    assert violations == []


def test_repair_step_from_description() -> None:
    """Repair fills action_verb and target_object from description."""
    step = Step(description="Search for Python 3.12 release notes")
    repaired = repair_step_from_description(step)
    assert repaired.action_verb == "Search"
    assert repaired.target_object == "Python 3.12 release notes"


def test_repair_step_fallback_first_word() -> None:
    """Fallback uses first word as verb, rest as target."""
    step = Step(description="Browse documentation")
    repaired = repair_step_from_description(step)
    assert repaired.action_verb == "Browse"
    assert repaired.target_object == "documentation"


def test_repair_step_preserves_existing() -> None:
    """Repair does not overwrite existing structured fields."""
    step = Step(
        description="Search for docs",
        action_verb="Research",
        target_object="Python docs",
    )
    repaired = repair_step_from_description(step)
    assert repaired.action_verb == "Research"
    assert repaired.target_object == "Python docs"
