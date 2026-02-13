"""Step naming quality regression (2026-02-13 plan Phase 6)."""

from unittest.mock import patch

from app.domain.models.plan import Step
from app.domain.services.flows.step_quality_validator import (
    BANNED_VERBS,
    repair_step_from_description,
    validate_step_quality,
)


def test_no_banned_verb_passes() -> None:
    """Steps with banned action_verbs should fail validation."""
    for banned in BANNED_VERBS:
        step = Step(
            description="Step",
            action_verb=banned,
            target_object="something",
        )
        with patch("app.domain.services.flows.step_quality_validator.get_settings") as m:
            m.return_value.enable_structured_step_model = True
            passed, violations = validate_step_quality(step)
        assert not passed, f"Banned verb '{banned}' should fail"
        assert "banned_verb" in violations


def test_merged_step_preserves_target() -> None:
    """Repair from description should preserve target_object."""
    step = Step(description="Search for Python 3.12 release notes")
    repaired = repair_step_from_description(step)
    assert repaired.target_object
    assert "Python" in (repaired.target_object or "")


def test_display_label_non_empty() -> None:
    """display_label must be non-empty for steps with description."""
    step = Step(description="Research the topic")
    assert step.display_label
    assert len(step.display_label.strip()) > 0
