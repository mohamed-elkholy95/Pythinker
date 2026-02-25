"""Phase assignment and step dependency routing for plan execution.

Routes plan steps into logical phases (research, analysis, report) and
validates step execution readiness by checking declared dependencies.

Usage:
    router = PhaseRouter(step_failure_handler=handler)
    router.assign_phases_to_plan(plan)
    can_run = router.check_step_dependencies(plan, step)
    should_skip, reason = router.should_skip_step(plan, step)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from app.domain.models.plan import ExecutionStatus, Phase, PhaseType

if TYPE_CHECKING:
    from app.domain.models.plan import Plan, Step
    from app.domain.services.flows.step_failure import StepFailureHandler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Research keyword heuristics used to classify steps into phases
# ---------------------------------------------------------------------------
_RESEARCH_KEYWORDS = frozenset(
    {
        "search",
        "find",
        "gather",
        "collect",
        "browse",
        "explore",
        "research",
        "investigate",
        "look up",
        "discover",
    }
)

# Pre-compiled word-boundary patterns to avoid false positives
# e.g. "find" should match "find information" but NOT "findings"
_RESEARCH_KEYWORD_PATTERNS = [re.compile(rf"\b{re.escape(kw)}\b") for kw in _RESEARCH_KEYWORDS]

_REPORT_KEYWORDS = ("write", "create", "compile", "draft", "generate", "report", "summarize", "compose")
_REPORT_KEYWORD_PATTERNS = [re.compile(rf"\b{re.escape(kw)}\b") for kw in _REPORT_KEYWORDS]


class PhaseRouter:
    """Routes plan steps into phases and validates step execution readiness.

    Responsibilities:
    - Assign heuristic phases (research, analysis, report) to a plan's steps
    - Check whether a step's declared dependencies are satisfied
    - Check whether a step should be skipped due to upstream failures

    This is a pure domain service with zero infrastructure imports.
    """

    __slots__ = ("_step_failure_handler",)

    def __init__(self, step_failure_handler: StepFailureHandler) -> None:
        self._step_failure_handler = step_failure_handler

    # ── Phase Assignment ──────────────────────────────────────────────

    def assign_phases_to_plan(self, plan: Plan) -> None:
        """Assign phases to plan steps based on step descriptions.

        Groups steps into logical phases (research, analysis, report, delivery)
        for structured progress display in the frontend.

        For simple plans (<=3 steps), assigns a single execution phase.
        For larger plans, uses keyword heuristics to classify each step.
        """
        if not plan.steps:
            return

        # Simple plans: single execution phase
        if len(plan.steps) <= 3:
            plan.phases = [
                Phase(
                    phase_type=PhaseType.RESEARCH_FOUNDATION,
                    label="Executing",
                    description="Executing plan steps",
                    order=0,
                    step_ids=[s.id for s in plan.steps],
                ),
            ]
            return

        # Larger plans: heuristic classification
        research_ids: list[str] = []
        analysis_ids: list[str] = []
        report_ids: list[str] = []

        for step in plan.steps:
            desc_lower = step.description.lower()
            if any(pat.search(desc_lower) for pat in _RESEARCH_KEYWORD_PATTERNS):
                research_ids.append(step.id)
            elif any(pat.search(desc_lower) for pat in _REPORT_KEYWORD_PATTERNS):
                report_ids.append(step.id)
            else:
                analysis_ids.append(step.id)

        phases: list[Phase] = []
        order = 0
        if research_ids:
            phases.append(
                Phase(
                    phase_type=PhaseType.RESEARCH_FOUNDATION,
                    label="Research",
                    description="Gathering information",
                    order=order,
                    step_ids=research_ids,
                )
            )
            order += 1
        if analysis_ids:
            phases.append(
                Phase(
                    phase_type=PhaseType.ANALYSIS_SYNTHESIS,
                    label="Analysis",
                    description="Analyzing findings",
                    order=order,
                    step_ids=analysis_ids,
                )
            )
            order += 1
        if report_ids:
            phases.append(
                Phase(
                    phase_type=PhaseType.REPORT_GENERATION,
                    label="Report",
                    description="Generating output",
                    order=order,
                    step_ids=report_ids,
                )
            )

        # Fallback: if all steps ended up in one bucket or none matched
        if not phases:
            phases = [
                Phase(
                    phase_type=PhaseType.RESEARCH_FOUNDATION,
                    label="Executing",
                    description="Executing plan steps",
                    order=0,
                    step_ids=[s.id for s in plan.steps],
                ),
            ]

        plan.phases = phases

    # ── Step Skip Check ───────────────────────────────────────────────

    def should_skip_step(self, plan: Plan, step: Step) -> tuple[bool, str]:
        """Check if a step should be skipped due to upstream failures.

        Delegates to StepFailureHandler for skip-decision logic.

        Returns:
            Tuple of (should_skip, reason).
        """
        return self._step_failure_handler.should_skip_step(plan, step)

    # ── Dependency Validation ─────────────────────────────────────────

    def check_step_dependencies(self, plan: Plan, step: Step) -> bool:
        """Check if a step's dependencies are satisfied.

        A step can execute if all its dependencies are either:
        - Completed successfully
        - Skipped (considered successful)

        If a dependency has failed/blocked, this step is marked blocked.
        If a dependency is pending/running, returns False (not ready yet).

        Args:
            plan: The execution plan containing all steps.
            step: The step whose dependencies to check.

        Returns:
            True if all dependencies are satisfied, False otherwise.
        """
        if not step.dependencies:
            return True

        for dep_id in step.dependencies:
            dep_step = next((s for s in plan.steps if s.id == dep_id), None)
            if not dep_step:
                # Dependency not found — treat as satisfied (might be external)
                continue

            if dep_step.status not in [ExecutionStatus.COMPLETED, ExecutionStatus.SKIPPED]:
                if dep_step.status in [ExecutionStatus.FAILED, ExecutionStatus.BLOCKED]:
                    step.mark_blocked(f"Dependency {dep_id} failed", blocked_by=dep_id)
                    return False
                if dep_step.status in [ExecutionStatus.PENDING, ExecutionStatus.RUNNING]:
                    return False

        return True
