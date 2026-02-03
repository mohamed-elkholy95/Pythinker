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
from collections.abc import AsyncGenerator
from typing import Any

from app.core.config import get_feature_flags
from app.domain.external.llm import LLM
from app.domain.models.event import (
    BaseEvent,
    ReflectionEvent,
    ReflectionStatus,
)
from app.domain.models.plan import Plan
from app.domain.models.reflection import (
    ProgressMetrics,
    ReflectionConfig,
    ReflectionDecision,
    ReflectionResult,
    ReflectionTriggerType,
)
from app.domain.services.agents.stuck_detector import StuckAnalysis
from app.domain.services.prompts.reflection import (
    LOOP_TYPE_CAUSES,
    REFLECT_AFTER_ERROR_PROMPT,
    REFLECT_ON_STALL_PROMPT,
    REFLECT_ON_STUCK_PATTERN_PROMPT,
    REFLECT_PROGRESS_PROMPT,
    REFLECTION_SYSTEM_PROMPT,
)
from app.domain.utils.json_parser import JsonParser
from app.infrastructure.observability.prometheus_metrics import (
    record_reflection_check,
    record_reflection_decision,
    record_reflection_trigger,
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

    def __init__(self, llm: LLM, json_parser: JsonParser, config: ReflectionConfig | None = None):
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
        confidence: float = 1.0,
        recent_actions: list[dict[str, Any]] | None = None,
    ) -> ReflectionTriggerType | None:
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

        trigger: ReflectionTriggerType | None = None

        # Check reflection limits
        if self._reflection_count >= self.config.max_reflections_per_task:
            logger.debug(f"Max reflections ({self.config.max_reflections_per_task}) reached")
        else:
            # Check minimum steps between reflections
            steps_since_last = progress.steps_completed - self._last_reflection_step
            if steps_since_last >= self.config.min_steps_between_reflections:
                # Use trigger configuration
                trigger = self.config.trigger.should_trigger(
                    steps_completed=progress.steps_completed,
                    error_count=progress.error_count,
                    total_attempts=progress.successful_actions + progress.failed_actions,
                    confidence=confidence,
                    is_stalled=progress.is_stalled,
                    last_had_error=last_had_error,
                )

        if not trigger:
            flags = get_feature_flags()
            if flags.get("reflection_advanced") and recent_actions:
                # Advanced signals: repeated failures or action loops
                recent = recent_actions[-5:]
                recent_failures = [a for a in recent if not a.get("success")]
                if len(recent_failures) >= 3:
                    trigger = ReflectionTriggerType.HIGH_ERROR_RATE
                else:
                    recent_tools = [a.get("function_name") for a in recent if a.get("function_name")]
                    if len(recent_tools) >= 3 and len(set(recent_tools[-3:])) == 1:
                        trigger = ReflectionTriggerType.PROGRESS_STALL

        if trigger:
            record_reflection_check("triggered")
            record_reflection_trigger(trigger.value)
        else:
            record_reflection_check("skipped")

        return trigger

    async def reflect(
        self,
        goal: str,
        plan: Plan,
        progress: ProgressMetrics,
        trigger_type: ReflectionTriggerType,
        recent_actions: list[dict[str, Any]] | None = None,
        last_error: str | None = None,
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
            f"Reflection triggered: {trigger_type.value} (step {progress.steps_completed}/{progress.total_steps})"
        )

        # Emit triggered event
        yield ReflectionEvent(status=ReflectionStatus.TRIGGERED, trigger_reason=trigger_type.value)

        try:
            # Perform the reflection
            result = await self._do_reflection(
                goal=goal,
                plan=plan,
                progress=progress,
                trigger_type=trigger_type,
                recent_actions=recent_actions or [],
                last_error=last_error,
            )

            # Update tracking
            self._reflection_count += 1
            self._last_reflection_step = progress.steps_completed

            # Emit completed event
            record_reflection_decision(result.decision.value)
            yield ReflectionEvent(
                status=ReflectionStatus.COMPLETED,
                decision=result.decision.value,
                confidence=result.confidence,
                summary=result.summary,
                trigger_reason=trigger_type.value,
            )

        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            # Fail-open: emit CONTINUE recommendation
            record_reflection_decision("continue")
            yield ReflectionEvent(
                status=ReflectionStatus.COMPLETED,
                decision="continue",
                confidence=0.5,
                summary=f"Reflection error (fail-open): {str(e)[:100]}",
                trigger_reason=trigger_type.value,
            )

    async def _do_reflection(
        self,
        goal: str,
        plan: Plan,
        progress: ProgressMetrics,
        trigger_type: ReflectionTriggerType,
        recent_actions: list[dict[str, Any]],
        last_error: str | None,
    ) -> ReflectionResult:
        """Perform the actual reflection assessment."""
        # Select appropriate prompt based on trigger type
        prompt = self._build_reflection_prompt(
            goal=goal,
            plan=plan,
            progress=progress,
            trigger_type=trigger_type,
            recent_actions=recent_actions,
            last_error=last_error,
        )

        # Call LLM
        messages = [{"role": "system", "content": REFLECTION_SYSTEM_PROMPT}, {"role": "user", "content": prompt}]

        response = await self.llm.ask(messages=messages, response_format={"type": "json_object"})

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
            trigger_type=trigger_type,
        )

    def _build_reflection_prompt(
        self,
        goal: str,
        plan: Plan,
        progress: ProgressMetrics,
        trigger_type: ReflectionTriggerType,
        recent_actions: list[dict[str, Any]],
        last_error: str | None,
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
                plan_status=plan_summary,
            )

        if trigger_type == ReflectionTriggerType.PROGRESS_STALL:
            return REFLECT_ON_STALL_PROMPT.format(
                goal=goal,
                repeat_count=progress.actions_since_progress,
                stall_duration="unknown",
                last_success="unknown",
                current_state=f"Step {progress.steps_completed} of {progress.total_steps}",
                attempted_actions=actions_text,
            )

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
            trigger_reason=trigger_type.value,
        )

    def reset(self) -> None:
        """Reset reflection state for a new task."""
        self._reflection_count = 0
        self._last_reflection_step = -1

    def get_stats(self) -> dict[str, Any]:
        """Get reflection statistics."""
        return {
            "total_reflections": self._reflection_count,
            "max_reflections": self.config.max_reflections_per_task,
            "last_reflection_step": self._last_reflection_step,
        }

    async def reflect_on_stuck_pattern(
        self,
        goal: str,
        plan: Plan,
        stuck_analysis: StuckAnalysis,
        recent_actions: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Perform specialized reflection when a stuck pattern is detected.

        This uses the troubleshooting protocol to analyze stuck patterns
        and provide specific recovery guidance.

        Args:
            goal: The original goal/objective
            plan: Current execution plan
            stuck_analysis: Analysis from StuckDetector
            recent_actions: Recent tool call results

        Yields:
            ReflectionEvent with assessment and recovery guidance
        """
        logger.info(
            f"Stuck pattern reflection triggered: {stuck_analysis.loop_type.value} "
            f"({stuck_analysis.repeat_count} repeats)"
        )

        # Emit triggered event
        yield ReflectionEvent(
            status=ReflectionStatus.TRIGGERED, trigger_reason=f"stuck_pattern:{stuck_analysis.loop_type.value}"
        )

        try:
            # Build specialized prompt
            prompt = self._build_stuck_pattern_prompt(
                goal=goal,
                plan=plan,
                stuck_analysis=stuck_analysis,
                recent_actions=recent_actions or [],
            )

            # Call LLM
            messages = [{"role": "system", "content": REFLECTION_SYSTEM_PROMPT}, {"role": "user", "content": prompt}]

            response = await self.llm.ask(messages=messages, response_format={"type": "json_object"})

            content = response.get("content", "")
            parsed = await self.json_parser.parse(content)

            # Parse decision
            decision_str = parsed.get("decision", "adjust").lower()
            try:
                decision = ReflectionDecision(decision_str)
            except ValueError:
                decision = ReflectionDecision.ADJUST  # Default to adjust for stuck patterns

            # Update tracking
            self._reflection_count += 1

            # Build enhanced summary with troubleshooting info
            diagnosis = parsed.get("diagnosis", "")
            most_likely_cause = parsed.get("most_likely_cause", "")
            recommended_action = parsed.get("recommended_action", "")

            summary = f"[{stuck_analysis.loop_type.value}] {diagnosis}"
            if most_likely_cause:
                summary += f" Most likely: {most_likely_cause}."
            if recommended_action:
                summary += f" Action: {recommended_action}"

            # Emit completed event
            yield ReflectionEvent(
                status=ReflectionStatus.COMPLETED,
                decision=decision.value,
                confidence=float(parsed.get("confidence", 0.7)),
                summary=summary[:500],  # Truncate if too long
                trigger_reason=f"stuck_pattern:{stuck_analysis.loop_type.value}",
            )

        except Exception as e:
            logger.error(f"Stuck pattern reflection failed: {e}")
            # Fail-open with ADJUST recommendation
            yield ReflectionEvent(
                status=ReflectionStatus.COMPLETED,
                decision="adjust",
                confidence=0.5,
                summary=f"Stuck pattern analysis error: {str(e)[:100]}. Recommend trying alternative approach.",
                trigger_reason=f"stuck_pattern:{stuck_analysis.loop_type.value}",
            )

    def _build_stuck_pattern_prompt(
        self,
        goal: str,
        plan: Plan,
        stuck_analysis: StuckAnalysis,
        recent_actions: list[dict[str, Any]],
    ) -> str:
        """Build prompt for stuck pattern analysis."""
        # Format recent actions
        actions_text = ""
        if recent_actions:
            action_lines = []
            for action in recent_actions[-8:]:  # More context for stuck analysis
                name = action.get("function_name", "unknown")
                success = action.get("success", True)
                error = action.get("error", "")
                result_preview = str(action.get("result", ""))[:80]
                status = "✓" if success else "✗"
                line = f"- {status} {name}"
                if error:
                    line += f" [ERROR: {error[:50]}]"
                elif result_preview:
                    line += f": {result_preview}"
                action_lines.append(line)
            actions_text = "\n".join(action_lines)
        else:
            actions_text = "No recent actions recorded"

        # Format plan status
        completed_steps = [s for s in plan.steps if s.is_done()]
        pending_steps = [s for s in plan.steps if not s.is_done()]
        plan_status = f"Completed: {len(completed_steps)}, Pending: {len(pending_steps)}"

        # Get loop-type specific causes
        loop_type_key = stuck_analysis.loop_type.value
        possible_causes = LOOP_TYPE_CAUSES.get(loop_type_key, "- Unknown pattern type\n- General debugging needed")

        return REFLECT_ON_STUCK_PATTERN_PROMPT.format(
            goal=goal,
            loop_type=stuck_analysis.loop_type.value,
            affected_tools=", ".join(stuck_analysis.affected_tools) or "Unknown",
            repeat_count=stuck_analysis.repeat_count,
            recovery_strategy=stuck_analysis.recovery_strategy.value,
            pattern_details=stuck_analysis.details,
            recent_actions=actions_text,
            plan_status=plan_status,
            possible_causes=possible_causes,
        )
