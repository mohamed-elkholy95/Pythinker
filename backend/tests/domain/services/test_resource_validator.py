from __future__ import annotations

from app.domain.models.plan import Plan, Step
from app.domain.services.validation.resource_validator import validate_resources


def _make_plan(step_count: int) -> Plan:
    """Return a Plan with the given number of minimal steps."""
    steps = [Step(id=f"step-{i}", description=f"Step {i}") for i in range(step_count)]
    return Plan(steps=steps)


class TestValidateResourcesDefaultThresholds:
    def test_empty_plan_returns_no_issues(self) -> None:
        plan = _make_plan(0)
        errors, warnings = validate_resources(plan)
        assert errors == []
        assert warnings == []

    def test_single_step_returns_no_issues(self) -> None:
        plan = _make_plan(1)
        errors, warnings = validate_resources(plan)
        assert errors == []
        assert warnings == []

    def test_at_warning_threshold_returns_no_issues(self) -> None:
        # 12 steps == max_steps_warning → no warning (condition is strictly >)
        plan = _make_plan(12)
        errors, warnings = validate_resources(plan)
        assert errors == []
        assert warnings == []

    def test_one_over_warning_threshold_emits_warning(self) -> None:
        plan = _make_plan(13)
        errors, warnings = validate_resources(plan)
        assert errors == []
        assert len(warnings) == 1
        assert "13" in warnings[0]

    def test_at_error_threshold_emits_warning_not_error(self) -> None:
        # 20 steps == max_steps_error → no error (condition is strictly >)
        plan = _make_plan(20)
        errors, warnings = validate_resources(plan)
        assert errors == []
        assert len(warnings) == 1

    def test_one_over_error_threshold_emits_error(self) -> None:
        plan = _make_plan(21)
        errors, warnings = validate_resources(plan)
        assert len(errors) == 1
        assert "21" in errors[0]
        assert warnings == []

    def test_far_over_error_threshold_emits_single_error(self) -> None:
        plan = _make_plan(50)
        errors, warnings = validate_resources(plan)
        assert len(errors) == 1
        assert "50" in errors[0]
        assert warnings == []

    def test_error_message_mentions_max(self) -> None:
        plan = _make_plan(25)
        errors, _ = validate_resources(plan)
        assert "20" in errors[0]  # mentions max_steps_error default value

    def test_warning_message_contains_step_count(self) -> None:
        plan = _make_plan(15)
        _, warnings = validate_resources(plan)
        assert "15" in warnings[0]


class TestValidateResourcesCustomThresholds:
    def test_custom_warning_threshold_lower(self) -> None:
        plan = _make_plan(6)
        errors, warnings = validate_resources(plan, max_steps_warning=5, max_steps_error=10)
        assert errors == []
        assert len(warnings) == 1
        assert "6" in warnings[0]

    def test_custom_warning_threshold_not_triggered(self) -> None:
        plan = _make_plan(4)
        errors, warnings = validate_resources(plan, max_steps_warning=5, max_steps_error=10)
        assert errors == []
        assert warnings == []

    def test_custom_error_threshold_triggered(self) -> None:
        plan = _make_plan(11)
        errors, warnings = validate_resources(plan, max_steps_warning=5, max_steps_error=10)
        assert len(errors) == 1
        assert warnings == []

    def test_custom_error_threshold_at_boundary_no_error(self) -> None:
        plan = _make_plan(10)
        errors, warnings = validate_resources(plan, max_steps_warning=5, max_steps_error=10)
        assert errors == []
        assert len(warnings) == 1

    def test_large_custom_thresholds_no_issues(self) -> None:
        plan = _make_plan(30)
        errors, warnings = validate_resources(plan, max_steps_warning=50, max_steps_error=100)
        assert errors == []
        assert warnings == []

    def test_returns_tuple_of_two_lists(self) -> None:
        plan = _make_plan(5)
        result = validate_resources(plan)
        assert isinstance(result, tuple)
        assert len(result) == 2
        errors, warnings = result
        assert isinstance(errors, list)
        assert isinstance(warnings, list)
