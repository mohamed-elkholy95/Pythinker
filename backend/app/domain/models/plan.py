from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum
import uuid


class ExecutionStatus(str, Enum):
    """Execution status for plan steps with enhanced state tracking."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"  # Step failed and blocks dependent steps
    SKIPPED = "skipped"  # Step skipped due to condition or optimization

    @classmethod
    def get_status_marks(cls) -> Dict[str, str]:
        """Get visual markers for UI display."""
        return {
            cls.PENDING.value: "[ ]",
            cls.RUNNING.value: "[→]",
            cls.COMPLETED.value: "[✓]",
            cls.FAILED.value: "[✗]",
            cls.BLOCKED.value: "[!]",
            cls.SKIPPED.value: "[-]",
        }

    @classmethod
    def get_active_statuses(cls) -> List[str]:
        """Get statuses that indicate step needs attention."""
        return [cls.PENDING.value, cls.RUNNING.value]

    @classmethod
    def get_terminal_statuses(cls) -> List[str]:
        """Get statuses that indicate step is done (no further action needed)."""
        return [cls.COMPLETED.value, cls.FAILED.value, cls.BLOCKED.value, cls.SKIPPED.value]

    @classmethod
    def get_success_statuses(cls) -> List[str]:
        """Get statuses that indicate successful completion."""
        return [cls.COMPLETED.value, cls.SKIPPED.value]

    @classmethod
    def get_failure_statuses(cls) -> List[str]:
        """Get statuses that indicate failure."""
        return [cls.FAILED.value, cls.BLOCKED.value]

    def is_active(self) -> bool:
        """Check if this status indicates active/pending work."""
        return self.value in self.get_active_statuses()

    def is_terminal(self) -> bool:
        """Check if this status indicates completion (success or failure)."""
        return self.value in self.get_terminal_statuses()

    def is_success(self) -> bool:
        """Check if this status indicates success."""
        return self.value in self.get_success_statuses()

    def is_failure(self) -> bool:
        """Check if this status indicates failure."""
        return self.value in self.get_failure_statuses()


class Step(BaseModel):
    """Step in a plan with enhanced status tracking."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    success: bool = False
    attachments: List[str] = []
    # Enhanced fields
    notes: str = ""  # Additional context (e.g., why blocked)
    agent_type: Optional[str] = None  # Which agent should handle this
    dependencies: List[str] = Field(default_factory=list)  # Step IDs this depends on
    blocked_by: Optional[str] = None  # ID of step that caused blocking

    def is_done(self) -> bool:
        """Check if step has reached a terminal state."""
        return self.status.is_terminal()

    def is_actionable(self) -> bool:
        """Check if step can be executed (pending and not blocked)."""
        return self.status == ExecutionStatus.PENDING

    def mark_blocked(self, reason: str, blocked_by: Optional[str] = None) -> None:
        """Mark this step as blocked with a reason."""
        self.status = ExecutionStatus.BLOCKED
        self.notes = reason
        self.blocked_by = blocked_by
        self.success = False

    def mark_skipped(self, reason: str) -> None:
        """Mark this step as skipped with a reason."""
        self.status = ExecutionStatus.SKIPPED
        self.notes = reason
        self.success = True  # Skipped is considered successful

    def get_status_mark(self) -> str:
        """Get visual marker for this step's status."""
        marks = ExecutionStatus.get_status_marks()
        return marks.get(self.status.value, "[ ]")

class Plan(BaseModel):
    """Plan with steps and enhanced progress tracking."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    goal: str = ""
    language: Optional[str] = "en"
    steps: List[Step] = []
    message: Optional[str] = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def is_done(self) -> bool:
        """Check if plan has reached a terminal state."""
        return self.status.is_terminal()

    def get_next_step(self) -> Optional[Step]:
        """Get next step that needs execution."""
        for step in self.steps:
            if step.is_actionable():
                return step
        return None

    def get_running_step(self) -> Optional[Step]:
        """Get currently running step if any."""
        for step in self.steps:
            if step.status == ExecutionStatus.RUNNING:
                return step
        return None

    def get_progress(self) -> Dict[str, Any]:
        """Get progress statistics for the plan."""
        total = len(self.steps)
        if total == 0:
            return {"total": 0, "completed": 0, "failed": 0, "blocked": 0, "skipped": 0, "pending": 0, "running": 0, "progress_pct": 0.0}

        status_counts = {status.value: 0 for status in ExecutionStatus}
        for step in self.steps:
            status_counts[step.status.value] += 1

        completed = status_counts[ExecutionStatus.COMPLETED.value]
        skipped = status_counts[ExecutionStatus.SKIPPED.value]
        successful = completed + skipped
        progress_pct = (successful / total) * 100 if total > 0 else 0.0

        return {
            "total": total,
            "completed": completed,
            "failed": status_counts[ExecutionStatus.FAILED.value],
            "blocked": status_counts[ExecutionStatus.BLOCKED.value],
            "skipped": skipped,
            "pending": status_counts[ExecutionStatus.PENDING.value],
            "running": status_counts[ExecutionStatus.RUNNING.value],
            "progress_pct": progress_pct
        }

    def format_progress_text(self) -> str:
        """Format plan progress as human-readable text."""
        progress = self.get_progress()
        marks = ExecutionStatus.get_status_marks()

        lines = [
            f"Plan: {self.title or self.goal[:50]}",
            f"Progress: {progress['completed']}/{progress['total']} completed ({progress['progress_pct']:.1f}%)",
            ""
        ]

        for i, step in enumerate(self.steps):
            mark = step.get_status_mark()
            lines.append(f"{i+1}. {mark} {step.description}")
            if step.notes:
                lines.append(f"   Notes: {step.notes}")

        return "\n".join(lines)

    def mark_blocked_cascade(self, blocked_step_id: str, reason: str) -> List[str]:
        """Mark all steps that depend on a blocked step as blocked.

        Args:
            blocked_step_id: ID of the step that failed
            reason: Reason for the blocking

        Returns:
            List of step IDs that were marked as blocked
        """
        blocked_ids = []

        for step in self.steps:
            if blocked_step_id in step.dependencies and step.status == ExecutionStatus.PENDING:
                step.mark_blocked(
                    reason=f"Blocked by step {blocked_step_id}: {reason}",
                    blocked_by=blocked_step_id
                )
                blocked_ids.append(step.id)
                # Recursively block dependents
                blocked_ids.extend(self.mark_blocked_cascade(step.id, reason))

        return blocked_ids

    def infer_sequential_dependencies(self) -> None:
        """Infer sequential dependencies based on step order.

        By default, each step depends on the previous step in sequence.
        This provides basic dependency tracking for plans without explicit dependencies.
        """
        for i, step in enumerate(self.steps):
            if i > 0 and not step.dependencies:
                # Add dependency on previous step if not already set
                prev_step = self.steps[i - 1]
                step.dependencies = [prev_step.id]

    def infer_smart_dependencies(self) -> None:
        """Infer dependencies based on step descriptions.

        Analyzes step descriptions to identify logical dependencies
        based on keyword patterns like "using results from", "after", etc.
        """
        # Keywords that indicate dependency on previous steps
        dependency_patterns = [
            "using the", "based on", "from the", "with the",
            "using results", "after", "once", "then",
        ]

        for i, step in enumerate(self.steps):
            if step.dependencies:
                continue  # Already has explicit dependencies

            desc_lower = step.description.lower()

            # Check for explicit dependency patterns
            has_dependency_pattern = any(
                pattern in desc_lower for pattern in dependency_patterns
            )

            if has_dependency_pattern and i > 0:
                # Depends on previous step
                step.dependencies = [self.steps[i - 1].id]
            elif i > 0:
                # Default: sequential dependency
                step.dependencies = [self.steps[i - 1].id]

    def get_step_by_id(self, step_id: str) -> Optional[Step]:
        """Get a step by its ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def dump_json(self) -> str:
        return self.model_dump_json(include={"goal", "language", "steps"})
