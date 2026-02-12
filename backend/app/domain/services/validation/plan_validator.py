"""Plan validation service combining multiple checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.models.plan import Plan
from app.domain.services.validation.dependency_analyzer import analyze_dependencies
from app.domain.services.validation.resource_validator import validate_resources

TOOL_MENTION_PATTERNS = [
    re.compile(r"tool\s*[:=]\s*`?([a-zA-Z_][\w\-]+)`?", re.IGNORECASE),
    re.compile(r"use\s+`?([a-zA-Z_][\w\-]+)`?\s+tool", re.IGNORECASE),
    re.compile(r"call\s+`?([a-zA-Z_][\w\-]+)`?\s+tool", re.IGNORECASE),
    re.compile(r"`([a-zA-Z_][\w\-]+)`\s+tool", re.IGNORECASE),
]


@dataclass
class PlanValidationReport:
    """Aggregated validation report for a plan."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_summary(self, max_items: int = 5) -> str:
        items = self.errors or self.warnings
        if not items:
            return "No issues detected."
        return "\n- " + "\n- ".join(items[:max_items])


class PlanValidator:
    """Plan validator that aggregates core and extended checks."""

    def __init__(
        self,
        tool_names: list[str] | None = None,
        strict_tool_match: bool = False,
    ) -> None:
        self._tool_names = [name.lower() for name in (tool_names or [])]
        self._strict_tool_match = strict_tool_match

    def validate(self, plan: Plan) -> PlanValidationReport:
        errors: list[str] = []
        warnings: list[str] = []

        # Base validation (dependencies, empty steps, cycles)
        base = plan.validate_plan()
        errors.extend(base.errors)
        warnings.extend(base.warnings)

        # Dependency analysis
        dep_errors, dep_warnings = analyze_dependencies(plan)
        errors.extend(dep_errors)
        warnings.extend(dep_warnings)

        # Resource constraints
        res_errors, res_warnings = validate_resources(plan)
        errors.extend(res_errors)
        warnings.extend(res_warnings)

        # Tool capability matching
        tool_errors, tool_warnings = self._validate_tool_mentions(plan)
        errors.extend(tool_errors)
        warnings.extend(tool_warnings)

        return PlanValidationReport(errors=_dedupe(errors), warnings=_dedupe(warnings))

    def _validate_tool_mentions(self, plan: Plan) -> tuple[list[str], list[str]]:
        if not self._tool_names:
            return [], []

        errors: list[str] = []
        warnings: list[str] = []

        available = set(self._tool_names)
        for step in plan.steps:
            mentions = _extract_tool_mentions(step.description)
            for mention in mentions:
                if mention.lower() not in available:
                    message = f"Step {step.id} references unavailable tool '{mention}'"
                    if self._strict_tool_match:
                        errors.append(message)
                    else:
                        warnings.append(message)

        return errors, warnings


def _extract_tool_mentions(description: str) -> list[str]:
    matches: list[str] = []
    if not description:
        return matches
    for pattern in TOOL_MENTION_PATTERNS:
        matches.extend(pattern.findall(description))
    return matches


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
