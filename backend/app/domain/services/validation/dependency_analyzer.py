"""Dependency analysis for plan validation."""

from __future__ import annotations

from app.domain.models.plan import Plan


def analyze_dependencies(plan: Plan) -> tuple[list[str], list[str]]:
    """Analyze plan dependencies for structural issues.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    step_ids = [step.id for step in plan.steps]
    if len(step_ids) != len(set(step_ids)):
        seen = set()
        for step_id in step_ids:
            if step_id in seen:
                errors.append(f"Duplicate step id detected: {step_id}")
            else:
                seen.add(step_id)

    index_by_id = {step.id: idx for idx, step in enumerate(plan.steps)}
    for step in plan.steps:
        for dep_id in step.dependencies:
            dep_index = index_by_id.get(dep_id)
            if dep_index is None:
                continue
            if dep_index > index_by_id.get(step.id, 0):
                warnings.append(f"Step {step.id} depends on a later step {dep_id}")

    return errors, warnings
