"""Extract session execution context for intent classification and prompt injection.

Provides a lightweight summary of what a session has done — plans created,
steps completed, topics researched — without requiring full event replay.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionExecutionContext:
    """Summary of a session's execution history."""

    had_plan: bool
    plan_title: str | None
    plan_steps: list[str]
    completed_steps: int
    topic: str | None

    def to_plan_summary(self) -> str:
        """Format as text for prompt injection."""
        if not self.had_plan:
            return ""
        steps = "\n".join(f"  - {s}" for s in self.plan_steps)
        progress = f" ({self.completed_steps}/{len(self.plan_steps)} completed)"
        return f"Plan: {self.plan_title}{progress}\nSteps:\n{steps}"


class SessionContextExtractor:
    """Extract execution context from a session's event history."""

    @staticmethod
    def extract(session: object) -> SessionExecutionContext:
        """Build a summary of the session's execution history.

        Args:
            session: Session object with .events list and .title

        Returns:
            SessionExecutionContext with plan/step information
        """
        from app.domain.models.event import PlanEvent, PlanStatus, StepEvent, StepStatus

        plan_title: str | None = None
        plan_steps: list[str] = []
        completed_steps: int = 0
        had_plan = False

        for event in getattr(session, "events", None) or []:
            if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                had_plan = True
                plan_title = getattr(event.plan, "title", None)
                plan_steps = [
                    s.description
                    for s in (getattr(event.plan, "steps", None) or [])
                    if hasattr(s, "description")
                ]
            elif isinstance(event, StepEvent) and event.status == StepStatus.COMPLETED:
                completed_steps += 1

        return SessionExecutionContext(
            had_plan=had_plan,
            plan_title=plan_title,
            plan_steps=plan_steps,
            completed_steps=completed_steps,
            topic=plan_title or getattr(session, "title", None),
        )
