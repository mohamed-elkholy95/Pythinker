"""Resource constraint checks for plan validation."""

from __future__ import annotations

from app.domain.models.plan import Plan


def validate_resources(
    plan: Plan,
    max_steps_warning: int = 12,
    max_steps_error: int = 20,
) -> tuple[list[str], list[str]]:
    """Validate simple resource constraints based on plan size.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    step_count = len(plan.steps)
    if step_count > max_steps_error:
        errors.append(f"Plan has {step_count} steps; exceeds maximum {max_steps_error}")
    elif step_count > max_steps_warning:
        warnings.append(f"Plan has {step_count} steps; may be too complex")

    return errors, warnings
