from app.domain.models.plan import Plan, Step
from app.domain.services.validation.plan_validator import PlanValidator


def test_plan_validator_detects_duplicate_ids():
    plan = Plan(
        title="Dup IDs",
        goal="Test",
        steps=[
            Step(id="1", description="First step"),
            Step(id="1", description="Duplicate step"),
        ],
    )
    report = PlanValidator().validate(plan)
    assert any("Duplicate step id" in error for error in report.errors)


def test_plan_validator_warns_on_late_dependency():
    step1 = Step(id="1", description="First step")
    step2 = Step(id="2", description="Second step", dependencies=["3"])
    step3 = Step(id="3", description="Third step")
    plan = Plan(title="Deps", goal="Test", steps=[step1, step2, step3])

    report = PlanValidator().validate(plan)
    assert any("depends on a later step" in warning for warning in report.warnings)


def test_plan_validator_tool_mentions_warn_when_missing():
    plan = Plan(
        title="Tools",
        goal="Test",
        steps=[
            Step(id="1", description="Use tool: browser_view to inspect page"),
        ],
    )
    report = PlanValidator(tool_names=["shell_exec"]).validate(plan)
    assert any("unavailable tool" in warning for warning in report.warnings)
