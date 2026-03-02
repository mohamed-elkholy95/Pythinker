"""Step failure handling for plan execution.

Extracts from PlanActFlow: handles step failures by cascading blocked
status to dependents and skipping optional steps.
"""

import logging

from app.domain.models.plan import ExecutionStatus, Plan, Step

logger = logging.getLogger(__name__)


class StepFailureHandler:
    """Handles step failures and skip decisions during plan execution.

    Responsibilities:
    - Mark dependent steps as blocked when a step fails
    - Determine if pending steps should be skipped
    - Cascade skip/block decisions through the plan
    """

    def handle_failure(self, plan: Plan, failed_step: Step) -> list[str]:
        """Handle step failure by marking dependent steps as blocked.

        If the failed step produced partial results (step.result is truthy),
        immediately attempt to unblock dependents so they can proceed with
        whatever data is available.

        Args:
            plan: The current plan
            failed_step: The step that failed

        Returns:
            List of step IDs that were marked as blocked
        """
        reason = failed_step.error or failed_step.result or "Step execution failed"
        blocked_ids = plan.mark_blocked_cascade(
            blocked_step_id=failed_step.id,
            reason=reason[:200],
        )

        # Always try to unblock dependents so the plan can make forward
        # progress.  When the failed step produced no result at all (e.g.
        # LLM retry loop exhausted), inject a minimal placeholder so
        # unblock_independent_steps() recognises the blocker as "has
        # partial results" and dependents are not permanently stuck.
        if blocked_ids:
            if not failed_step.result:
                failed_step.result = f"[Step failed without results: {(failed_step.error or 'execution error')[:120]}]"
                logger.info(
                    "Injected placeholder result on step %s to unblock %d dependents",
                    failed_step.id,
                    len(blocked_ids),
                )
            unblocked = plan.unblock_independent_steps()
            if unblocked:
                logger.info(
                    "Partial-result propagation: step %s failed but had results — unblocked %d dependents: %s",
                    failed_step.id,
                    len(unblocked),
                    unblocked,
                )
                # Remove unblocked IDs from the blocked list since they're now PENDING
                blocked_ids = [sid for sid in blocked_ids if sid not in unblocked]

        return blocked_ids

    def should_skip_step(self, plan: Plan, step: Step) -> tuple[bool, str]:
        """Check if a step should be skipped.

        Steps can be skipped if they're optional and a dependency failed.

        Args:
            plan: The current plan
            step: The step to evaluate

        Returns:
            Tuple of (should_skip, reason)
        """
        # Check if any dependency is blocked
        for dep_id in step.dependencies:
            dep_step = next((s for s in plan.steps if s.id == dep_id), None)
            if dep_step and dep_step.status == ExecutionStatus.BLOCKED:
                return True, "Dependency is blocked"

        # Check for optional steps
        optional_patterns = ["optional", "if needed", "if required", "alternatively"]
        description_lower = step.description.lower()
        is_optional = any(pattern in description_lower for pattern in optional_patterns)

        if is_optional:
            has_failed_dep = any(
                dep_step.status == ExecutionStatus.FAILED
                for dep_id in step.dependencies
                for dep_step in plan.steps
                if dep_step.id == dep_id
            )
            if has_failed_dep:
                return True, "Optional step skipped: dependency failed"

        return False, ""

    def check_and_skip_steps(self, plan: Plan) -> list[str]:
        """Check all pending steps and skip those that should be skipped.

        Args:
            plan: The current plan

        Returns:
            List of step IDs that were skipped
        """
        skipped_ids = []
        for step in plan.steps:
            if step.status == ExecutionStatus.PENDING:
                should_skip, reason = self.should_skip_step(plan, step)
                if should_skip:
                    step.mark_skipped(reason)
                    skipped_ids.append(step.id)
                    logger.info(f"Skipped step {step.id}: {reason}")

        return skipped_ids
