"""ReflectionAgent for intermediate progress assessment during execution.

The ReflectionAgent provides course correction capability during task execution,
not just at the end. It enables:
- Early detection of strategy issues
- Adaptive replanning when approaches fail
- User escalation when truly blocked
- Resource-efficient execution through early pivots

This implements the Enhanced Self-Reflection pattern (Phase 2).

Usage:
    reflection_agent = ReflectionAgent(llm, json_parser)

    # Check if reflection should be triggered
    trigger = reflection_agent.should_reflect(progress_metrics)

    if trigger:
        result = await reflection_agent.reflect(
            goal=plan.goal,
            progress=metrics,
            trigger_type=trigger,
            recent_actions=recent_tool_results
        )

        if result.decision == ReflectionDecision.REPLAN:
            # Return to planning with reflection feedback
            ...
"""

import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass

from app.domain.external.llm import LLM
from app.domain.utils.json_parser import JsonParser
from app.domain.models.plan import Plan
from app.domain.models.event import (
    BaseEvent,
    ReflectionEvent,
    ReflectionStatus,
)
from app.domain.models.reflection import (
    ReflectionTrigger,
    ReflectionTriggerType,
    ReflectionDecision,
    ReflectionResult,
    ReflectionConfig,
    ProgressMetrics,
)
from app.domain.services.prompts.reflection import (
    REFLECTION_SYSTEM_PROMPT,
    REFLECT_PROGRESS_PROMPT,
    REFLECT_AFTER_ERROR_PROMPT,
    REFLECT_ON_STALL_PROMPT,
)


logger = logging.getLogger(__name__)


class ReflectionAgent:
    """Agent that assesses progress and recommends course corrections.

    The reflection agent provides intermediate assessment during execution,
    enabling early detection and correction of strategy issues.

    Design principles:
    - Fast: Quick assessments that don't slow down execution
    - Conservative: Default to CONTINUE unless clear reason to change
    - Actionable: Provide specific guidance for adjustments
    - Fail-open: On error, recommend CONTINUE to avoid blocking
    """

    def __init__(
        self,
        llm: LLM,
        json_parser: JsonParser,
        config: Optional[ReflectionConfig] = None
    ):
        """Initialize the ReflectionAgent.

        Args:
            llm: Language model for assessment
            json_parser: Parser for structured responses
            config: Optional configuration
        """
        self.llm = llm
        self.json_parser = json_parser
        self.config = config or ReflectionConfig()

        # Track reflection history to prevent loops
        self._reflection_count = 0
        self._last_reflection_step = -1

    def should_reflect(
        self,
        progress: ProgressMetrics,
        last_had_error: bool = False,
        confidence: float = 1.0
    ) -> Optional[ReflectionTriggerType]:
        """Check if reflection should be triggered.

        Args:
            progress: Current progress metrics
            last_had_error: Whether the last action had an error
            confidence: Current confidence level

        Returns:
            ReflectionTriggerType if triggered, None otherwise
        """
        if not self.config.enabled:
            return None

        # Check reflection limits
        if self._reflection_count >= self.config.max_reflections_per_task:
            logger.debug(
                f"Max reflections ({self.config.max_reflections_per_task}) reached"
            )
            return None

        # Check minimum steps between reflections
        steps_since_last = progress.steps_completed - self._last_reflection_step
        if steps_since_last < self.config.min_steps_between_reflections:
            return None

        # Use trigger configuration
        return self.config.trigger.should_trigger(
            steps_completed=progress.steps_completed,
            error_count=progress.error_count,
            total_attempts=progress.successful_actions + progress.failed_actions,
            confidence=confidence,
            is_stalled=progress.is_stalled,
            last_had_error=last_had_error
        )

    async def reflect(
        self,
        goal: str,
        plan: Plan,
        progress: ProgressMetrics,
        trigger_type: ReflectionTriggerType,
        recent_actions: List[Dict[str, Any]] = None,
        last_error: Optional[str] = None
    ) -> AsyncGenerator[BaseEvent, None]:
        """Perform reflection and yield events.

        Args:
            goal: The original goal/objective
            plan: Current execution plan
            progress: Current progress metrics
            trigger_type: What triggered this reflection
            recent_actions: Recent tool call results
            last_error: Most recent error message if any

        Yields:
            ReflectionEvent with assessment results
        """
        logger.info(
            f"Reflection triggered: {trigger_type.value} "
            f"(step {progress.steps_completed}/{progress.total_steps})"
        )

        # Emit triggered event
        yield ReflectionEvent(
            status=ReflectionStatus.TRIGGERED,
            trigger_reason=trigger_type.value
        )

        try:
            # Perform the reflection
            result = await self._do_reflection(
                goal=goal,
                plan=plan,
                progress=progress,
                trigger_type=trigger_type,
                recent_actions=recent_actions or [],
                last_error=last_error
            )

            # Update tracking
            self._reflection_count += 1
            self._last_reflection_step = progress.steps_completed

            # Emit completed event
            yield ReflectionEvent(
                status=ReflectionStatus.COMPLETED,
                decision=result.decision.value,
                confidence=result.confidence,
                summary=result.summary,
                trigger_reason=trigger_type.value
            )

        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            # Fail-open: emit CONTINUE recommendation
            yield ReflectionEvent(
                status=ReflectionStatus.COMPLETED,
                decision="continue",
                confidence=0.5,
                summary=f"Reflection error (fail-open): {str(e)[:100]}",
                trigger_reason=trigger_type.value
            )

    async def _do_reflection(
        self,
        goal: str,
        plan: Plan,
        progress: ProgressMetrics,
        trigger_type: ReflectionTriggerType,
        recent_actions: List[Dict[str, Any]],
        last_error: Optional[str]
    ) -> ReflectionResult:
        """Perform the actual reflection assessment."""
        # Select appropriate prompt based on trigger type
        prompt = self._build_reflection_prompt(
            goal=goal,
            plan=plan,
            progress=progress,
            trigger_type=trigger_type,
            recent_actions=recent_actions,
            last_error=last_error
        )

        # Call LLM
        messages = [
            {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        response = await self.llm.ask(
            messages=messages,
            response_format={"type": "json_object"}
        )

        content = response.get("content", "")
        parsed = await self.json_parser.parse(content)

        # Parse decision
        decision_str = parsed.get("decision", "continue").lower()
        try:
            decision = ReflectionDecision(decision_str)
        except ValueError:
            decision = ReflectionDecision.CONTINUE

        return ReflectionResult(
            decision=decision,
            confidence=float(parsed.get("confidence", 0.8)),
            progress_assessment=parsed.get("progress_assessment", ""),
            issues_identified=parsed.get("issues_identified", []),
            strategy_adjustment=parsed.get("strategy_adjustment"),
            replan_reason=parsed.get("replan_reason"),
            user_question=parsed.get("user_question"),
            summary=parsed.get("summary", "Reflection completed"),
            trigger_type=trigger_type
        )

    def _build_reflection_prompt(
        self,
        goal: str,
        plan: Plan,
        progress: ProgressMetrics,
        trigger_type: ReflectionTriggerType,
        recent_actions: List[Dict[str, Any]],
        last_error: Optional[str]
    ) -> str:
        """Build the appropriate reflection prompt."""
        # Format recent actions
        actions_text = ""
        if recent_actions:
            action_lines = []
            for action in recent_actions[-5:]:  # Last 5 actions
                name = action.get("function_name", "unknown")
                success = action.get("success", True)
                result_preview = str(action.get("result", ""))[:100]
                status = "✓" if success else "✗"
                action_lines.append(f"- {status} {name}: {result_preview}")
            actions_text = "\n".join(action_lines)
        else:
            actions_text = "No recent actions recorded"

        # Format plan summary
        completed_steps = [s for s in plan.steps if s.is_done()]
        pending_steps = [s for s in plan.steps if not s.is_done()]
        plan_summary = f"Completed: {len(completed_steps)}, Pending: {len(pending_steps)}"

        # Get current step description
        current_step = "None"
        if pending_steps:
            current_step = pending_steps[0].description[:100]

        # Select prompt based on trigger
        if trigger_type == ReflectionTriggerType.AFTER_ERROR:
            return REFLECT_AFTER_ERROR_PROMPT.format(
                goal=goal,
                step_description=current_step,
                error_message=last_error or "Unknown error",
                is_recoverable="Unknown",
                steps_completed=progress.steps_completed,
                total_steps=progress.total_steps,
                previous_errors=progress.error_count,
                plan_status=plan_summary
            )

        elif trigger_type == ReflectionTriggerType.PROGRESS_STALL:
            return REFLECT_ON_STALL_PROMPT.format(
                goal=goal,
                repeat_count=progress.actions_since_progress,
                stall_duration="unknown",
                last_success="unknown",
                current_state=f"Step {progress.steps_completed} of {progress.total_steps}",
                attempted_actions=actions_text
            )

        else:
            # Default progress check prompt
            return REFLECT_PROGRESS_PROMPT.format(
                goal=goal,
                plan_summary=plan_summary,
                steps_completed=progress.steps_completed,
                total_steps=progress.total_steps,
                success_rate=round(progress.success_rate * 100, 1),
                current_step=current_step,
                recent_actions=actions_text,
                error_count=progress.error_count,
                last_error=last_error or "None",
                is_stalled="Yes" if progress.is_stalled else "No",
                trigger_reason=trigger_type.value
            )

    def reset(self) -> None:
        """Reset reflection state for a new task."""
        self._reflection_count = 0
        self._last_reflection_step = -1

    def get_stats(self) -> Dict[str, Any]:
        """Get reflection statistics."""
        return {
            "total_reflections": self._reflection_count,
            "max_reflections": self.config.max_reflections_per_task,
            "last_reflection_step": self._last_reflection_step,
        }
