"""
Lazy Plan Evaluation module.

This module provides lazy planning that defers detailed planning
of later steps until earlier steps complete.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from app.domain.models.plan import Plan

logger = logging.getLogger(__name__)


class StepDetailLevel(str, Enum):
    """Level of detail in a step."""

    SKELETON = "skeleton"  # Just a placeholder
    OUTLINE = "outline"  # High-level description
    DETAILED = "detailed"  # Full actionable detail
    EXECUTED = "executed"  # Has been executed


@dataclass
class LazyStep:
    """A lazily-evaluated plan step.

    Initially created with minimal detail, expanded
    when execution approaches.
    """

    step_id: str
    description: str
    detail_level: StepDetailLevel = StepDetailLevel.OUTLINE
    detailed_actions: list[str] = field(default_factory=list)
    tool_requirements: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # Other step IDs
    expansion_context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expanded_at: datetime | None = None
    executed_at: datetime | None = None

    def needs_expansion(self) -> bool:
        """Check if step needs to be expanded."""
        return self.detail_level in [StepDetailLevel.SKELETON, StepDetailLevel.OUTLINE]

    def is_ready_to_execute(self) -> bool:
        """Check if step has enough detail to execute."""
        return self.detail_level == StepDetailLevel.DETAILED

    def expand(self, detailed_actions: list[str], tool_requirements: list[str]) -> None:
        """Expand the step with full details."""
        self.detailed_actions = detailed_actions
        self.tool_requirements = tool_requirements
        self.detail_level = StepDetailLevel.DETAILED
        self.expanded_at = datetime.now(UTC)


@dataclass
class LazyPlan:
    """A lazily-evaluated plan."""

    plan_id: str
    goal: str
    lazy_steps: list[LazyStep] = field(default_factory=list)
    expansion_horizon: int = 2  # How many steps ahead to expand
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def get_step(self, step_id: str) -> LazyStep | None:
        """Get a step by ID."""
        for step in self.lazy_steps:
            if step.step_id == step_id:
                return step
        return None

    def get_current_step(self) -> LazyStep | None:
        """Get the next step to execute."""
        for step in self.lazy_steps:
            if step.detail_level != StepDetailLevel.EXECUTED:
                return step
        return None

    def get_steps_needing_expansion(self) -> list[LazyStep]:
        """Get steps that need expansion based on horizon."""
        current_idx = 0
        for i, step in enumerate(self.lazy_steps):
            if step.detail_level != StepDetailLevel.EXECUTED:
                current_idx = i
                break

        # Get steps within horizon that need expansion
        needing_expansion = []
        for i in range(current_idx, min(current_idx + self.expansion_horizon, len(self.lazy_steps))):
            step = self.lazy_steps[i]
            if step.needs_expansion():
                needing_expansion.append(step)

        return needing_expansion


class LazyPlanner:
    """Planner for lazy plan evaluation.

    Defers detailed planning of later steps until earlier
    steps are closer to execution, allowing the plan to
    adapt based on earlier results.
    """

    # Default expansion horizon
    DEFAULT_HORIZON = 2
    # Maximum total steps to plan initially
    MAX_INITIAL_STEPS = 8

    def __init__(
        self,
        expansion_horizon: int | None = None,
    ) -> None:
        """Initialize the lazy planner.

        Args:
            expansion_horizon: How many steps ahead to maintain detail
        """
        self._expansion_horizon = expansion_horizon or self.DEFAULT_HORIZON
        self._active_plans: dict[str, LazyPlan] = {}

    def create_lazy_plan(
        self,
        plan_id: str,
        goal: str,
        initial_steps: list[str],
    ) -> LazyPlan:
        """Create a new lazy plan.

        First few steps get full detail, later steps get outlines.

        Args:
            plan_id: Unique plan identifier
            goal: Plan goal
            initial_steps: List of step descriptions

        Returns:
            The created lazy plan
        """
        lazy_steps = []

        for i, description in enumerate(initial_steps[: self.MAX_INITIAL_STEPS]):
            # First steps in horizon get detailed, others get outline
            detail_level = StepDetailLevel.DETAILED if i < self._expansion_horizon else StepDetailLevel.OUTLINE

            step = LazyStep(
                step_id=f"step_{i + 1}",
                description=description,
                detail_level=detail_level,
            )
            lazy_steps.append(step)

        plan = LazyPlan(
            plan_id=plan_id,
            goal=goal,
            lazy_steps=lazy_steps,
            expansion_horizon=self._expansion_horizon,
        )

        self._active_plans[plan_id] = plan

        logger.info(f"Created lazy plan {plan_id} with {len(lazy_steps)} steps, {self._expansion_horizon} detailed")

        return plan

    def convert_to_lazy_plan(
        self,
        plan: Plan,
    ) -> LazyPlan:
        """Convert a regular plan to a lazy plan.

        Args:
            plan: The plan to convert

        Returns:
            Lazy plan version
        """
        lazy_steps = []

        for i, step in enumerate(plan.steps):
            detail_level = StepDetailLevel.DETAILED if i < self._expansion_horizon else StepDetailLevel.OUTLINE

            lazy_step = LazyStep(
                step_id=step.id,
                description=step.description,
                detail_level=detail_level,
            )
            lazy_steps.append(lazy_step)

        lazy_plan = LazyPlan(
            plan_id=plan.id,
            goal=plan.goal,
            lazy_steps=lazy_steps,
            expansion_horizon=self._expansion_horizon,
        )

        self._active_plans[plan.id] = lazy_plan
        return lazy_plan

    def expand_step(
        self,
        plan_id: str,
        step_id: str,
        detailed_actions: list[str],
        tool_requirements: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> LazyStep | None:
        """Expand a step with full details.

        Args:
            plan_id: Plan ID
            step_id: Step ID to expand
            detailed_actions: Detailed action list
            tool_requirements: Required tools
            context: Expansion context

        Returns:
            The expanded step
        """
        plan = self._active_plans.get(plan_id)
        if not plan:
            return None

        step = plan.get_step(step_id)
        if not step:
            return None

        step.expand(
            detailed_actions=detailed_actions,
            tool_requirements=tool_requirements or [],
        )

        if context:
            step.expansion_context = context

        logger.debug(f"Expanded step {step_id} in plan {plan_id}")
        return step

    def mark_step_executed(
        self,
        plan_id: str,
        step_id: str,
        result: dict[str, Any] | None = None,
    ) -> list[LazyStep]:
        """Mark a step as executed and return steps needing expansion.

        Args:
            plan_id: Plan ID
            step_id: Step ID that was executed
            result: Execution result for context

        Returns:
            List of steps that now need expansion
        """
        plan = self._active_plans.get(plan_id)
        if not plan:
            return []

        step = plan.get_step(step_id)
        if step:
            step.detail_level = StepDetailLevel.EXECUTED
            step.executed_at = datetime.now(UTC)

            # Store result in context for future steps
            if result:
                step.expansion_context["result"] = result

        # Return steps that now need expansion
        return plan.get_steps_needing_expansion()

    def get_expansion_context(
        self,
        plan_id: str,
    ) -> dict[str, Any]:
        """Get context from completed steps for expanding future steps.

        Args:
            plan_id: Plan ID

        Returns:
            Aggregated context from completed steps
        """
        plan = self._active_plans.get(plan_id)
        if not plan:
            return {}

        context = {}
        for step in plan.lazy_steps:
            if step.detail_level == StepDetailLevel.EXECUTED:
                context[step.step_id] = step.expansion_context

        return context

    def adapt_remaining_steps(
        self,
        plan_id: str,
        new_information: dict[str, Any],
    ) -> list[LazyStep]:
        """Adapt remaining steps based on new information.

        Args:
            plan_id: Plan ID
            new_information: New context/results

        Returns:
            Steps that were adapted
        """
        plan = self._active_plans.get(plan_id)
        if not plan:
            return []

        adapted = []
        for step in plan.lazy_steps:
            if step.detail_level in [StepDetailLevel.SKELETON, StepDetailLevel.OUTLINE]:
                # Update expansion context
                step.expansion_context.update(new_information)
                adapted.append(step)

        return adapted

    def get_plan_progress(self, plan_id: str) -> dict[str, Any]:
        """Get progress information for a plan.

        Args:
            plan_id: Plan ID

        Returns:
            Progress information
        """
        plan = self._active_plans.get(plan_id)
        if not plan:
            return {}

        total = len(plan.lazy_steps)
        executed = sum(1 for s in plan.lazy_steps if s.detail_level == StepDetailLevel.EXECUTED)
        detailed = sum(1 for s in plan.lazy_steps if s.detail_level == StepDetailLevel.DETAILED)
        outline = sum(1 for s in plan.lazy_steps if s.detail_level == StepDetailLevel.OUTLINE)

        return {
            "plan_id": plan_id,
            "total_steps": total,
            "executed": executed,
            "detailed": detailed,
            "outline": outline,
            "progress_percent": (executed / total * 100) if total > 0 else 0,
            "current_step": plan.get_current_step().step_id if plan.get_current_step() else None,
        }

    def cleanup_plan(self, plan_id: str) -> None:
        """Clean up a completed plan.

        Args:
            plan_id: Plan ID to clean up
        """
        if plan_id in self._active_plans:
            del self._active_plans[plan_id]


# Global lazy planner instance
_planner: LazyPlanner | None = None


def get_lazy_planner(
    expansion_horizon: int | None = None,
) -> LazyPlanner:
    """Get or create the global lazy planner."""
    global _planner
    if _planner is None:
        _planner = LazyPlanner(expansion_horizon)
    return _planner


def reset_lazy_planner() -> None:
    """Reset the global lazy planner."""
    global _planner
    _planner = None
