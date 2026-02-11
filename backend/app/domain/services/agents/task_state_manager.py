"""
Task state management for todo recitation and progress tracking.

Maintains a persistent task_state.md file in the sandbox to keep
objectives and progress in the agent's recent attention span.
Based on Manus's recitation approach for improved goal focus.

Enhanced with ProgressMetrics integration for reflection system (Phase 2).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.models.reflection import ProgressMetrics

logger = logging.getLogger(__name__)


TASK_STATE_PATH = "/home/ubuntu/task_state.md"

TASK_STATE_TEMPLATE = """# Task State

## Objective
{objective}

## Progress
{progress}

## Key Findings
{findings}

## Current Focus
{current_focus}

---
*Last updated: {timestamp}*
"""

STEP_STATUS_ICONS = {
    "completed": "[x]",
    "in_progress": "[>]",
    "pending": "[ ]",
    "failed": "[!]",
}


@dataclass
class TaskState:
    """Current state of the task for recitation"""

    objective: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    current_step_index: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    # Track visited URLs and search queries to survive token trimming
    visited_urls: set[str] = field(default_factory=set)
    searched_queries: set[str] = field(default_factory=set)

    def add_step(self, description: str, status: str = "pending", step_id: str | None = None) -> None:
        """Add a step to the task"""
        self.steps.append(
            {
                "id": step_id or str(len(self.steps) + 1),
                "description": description,
                "status": status,
            }
        )

    def mark_step_completed(self, step_id: str, result: str | None = None) -> bool:
        """Mark a step as completed.

        Returns:
            True if step was found and updated, False otherwise
        """
        # Normalize step_id to string for consistent matching
        step_id = str(step_id)
        found = False
        for step in self.steps:
            if str(step["id"]) == step_id:
                step["status"] = "completed"
                if result:
                    step["result"] = result
                found = True
                break
        self.last_updated = datetime.now()
        return found

    def mark_step_in_progress(self, step_id: str) -> bool:
        """Mark a step as in progress.

        Returns:
            True if step was found and updated, False otherwise
        """
        # Normalize step_id to string for consistent matching
        step_id = str(step_id)
        found = False
        for step in self.steps:
            if str(step["id"]) == step_id:
                step["status"] = "in_progress"
                found = True
                break
        self.last_updated = datetime.now()
        return found

    def record_url(self, url: str) -> bool:
        """Record a visited URL. Returns True if this is a new URL."""
        if not url:
            return False
        # Normalize URL for dedup (strip trailing slash, fragment)
        normalized = url.split("#")[0].rstrip("/")
        is_new = normalized not in self.visited_urls
        self.visited_urls.add(normalized)
        return is_new

    def record_query(self, query: str) -> bool:
        """Record a search query. Returns True if this is a new query."""
        if not query:
            return False
        normalized = query.strip().lower()
        is_new = normalized not in self.searched_queries
        self.searched_queries.add(normalized)
        return is_new

    def get_visited_summary(self) -> str:
        """Return a compact summary of visited URLs and search queries for context injection.

        This summary survives token trimming because it's regenerated from TaskState
        (which persists outside of message history) and injected fresh each time.
        """
        lines: list[str] = []
        if self.searched_queries:
            queries = sorted(self.searched_queries)
            # Show up to 20, truncate if more
            shown = queries[:20]
            lines.append(f"SEARCHES ALREADY PERFORMED ({len(self.searched_queries)} total):")
            lines.extend(f"  - {q}" for q in shown)
            if len(queries) > 20:
                lines.append(f"  ... and {len(queries) - 20} more")

        if self.visited_urls:
            urls = sorted(self.visited_urls)
            shown = urls[:20]
            lines.append(f"URLS ALREADY VISITED ({len(self.visited_urls)} total):")
            lines.extend(f"  - {u}" for u in shown)
            if len(urls) > 20:
                lines.append(f"  ... and {len(urls) - 20} more")

        if lines:
            lines.insert(0, "DO NOT re-search or re-visit these. Use different queries/URLs or proceed with findings.")
        return "\n".join(lines)

    def add_finding(self, finding: str) -> None:
        """Add a key finding"""
        if finding and finding not in self.key_findings:
            self.key_findings.append(finding)
            # Keep findings list manageable
            if len(self.key_findings) > 10:
                self.key_findings = self.key_findings[-10:]
        self.last_updated = datetime.now()

    def get_current_step(self) -> dict[str, Any] | None:
        """Get the current step being worked on"""
        for step in self.steps:
            if step["status"] == "in_progress":
                return step
        # If no in_progress step, return first pending
        for step in self.steps:
            if step["status"] == "pending":
                return step
        return None

    def to_markdown(self) -> str:
        """Convert task state to markdown for file storage and context injection"""
        # Format progress section
        progress_lines = []
        for step in self.steps:
            status_icon = STEP_STATUS_ICONS.get(step["status"], "[ ]")
            desc = step["description"]
            if step["status"] == "in_progress":
                desc += " (IN PROGRESS)"
            progress_lines.append(f"- {status_icon} Step {step['id']}: {desc}")

        progress = "\n".join(progress_lines) if progress_lines else "No steps defined"

        # Format findings section
        findings = "\n".join(f"- {f}" for f in self.key_findings) if self.key_findings else "None yet"

        # Current focus
        current = self.get_current_step()
        current_focus = current["description"] if current else "Awaiting next step"

        return TASK_STATE_TEMPLATE.format(
            objective=self.objective or "Not specified",
            progress=progress,
            findings=findings,
            current_focus=current_focus,
            timestamp=self.last_updated.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def to_context_signal(self) -> str:
        """Generate a compact context signal for prompt injection.

        Shows running steps count to provide accurate progress even when
        steps are actively being executed.
        """
        completed = sum(1 for s in self.steps if s["status"] == "completed")
        running = sum(1 for s in self.steps if s["status"] == "in_progress")
        failed = sum(1 for s in self.steps if s["status"] == "failed")
        total = len(self.steps)
        current = self.get_current_step()

        lines = [
            f"OBJECTIVE: {self.objective[:100]}..." if len(self.objective) > 100 else f"OBJECTIVE: {self.objective}",
        ]

        # Build progress string with running indicator for better visibility
        progress_parts = []
        if running > 0:
            progress_parts.append(f"{running} running")
        progress_parts.append(f"{completed}/{total} completed")
        if failed > 0:
            progress_parts.append(f"{failed} failed")
        lines.append(f"PROGRESS: {', '.join(progress_parts)}")

        if current:
            lines.append(f"CURRENT: Step {current['id']} - {current['description'][:80]}")

        if self.key_findings:
            lines.append(f"FINDINGS: {len(self.key_findings)} key results captured")

        # Include visited URL/query summary so agent doesn't re-search after token trimming
        visited_summary = self.get_visited_summary()
        if visited_summary:
            lines.append("")
            lines.append(visited_summary)

        return "\n".join(lines)


class TaskStateManager:
    """
    Manages persistent task state for todo recitation.

    Maintains task_state.md in the sandbox and provides state
    for context injection to keep objectives in attention.

    Enhanced with ProgressMetrics for reflection system integration (Phase 2).
    """

    def __init__(self, sandbox=None):
        """
        Initialize the task state manager.

        Args:
            sandbox: Optional sandbox for file operations
        """
        self._sandbox = sandbox
        self._state: TaskState | None = None
        self._file_path = TASK_STATE_PATH
        # Lock to serialize concurrent sandbox writes
        self._write_lock = asyncio.Lock()
        # Progress metrics for reflection integration
        self._progress_metrics: ProgressMetrics | None = None
        # Track recent actions for reflection context
        self._recent_actions: list[dict[str, Any]] = []
        self._max_recent_actions = 10

    def initialize_from_plan(self, objective: str, steps: list[dict[str, Any]]) -> TaskState:
        """
        Initialize task state from a plan.

        Args:
            objective: The user's original goal/request
            steps: List of plan steps with id and description

        Returns:
            Initialized TaskState
        """
        self._state = TaskState(objective=objective)

        for step in steps:
            self._state.add_step(
                description=step.get("description", ""), status="pending", step_id=str(step.get("id", ""))
            )

        # Initialize progress metrics for reflection
        self._progress_metrics = ProgressMetrics(
            steps_completed=0, steps_remaining=len(steps), total_steps=len(steps), started_at=datetime.now()
        )

        # Clear recent actions
        self._recent_actions = []

        logger.info(f"TaskStateManager initialized with {len(steps)} steps")
        return self._state

    async def update_step_status(
        self, step_id: str, status: str, result: str | None = None, findings: list[str] | None = None
    ) -> None:
        """
        Update step status and add any findings.

        Serialized via ``_write_lock`` to prevent mutation races with
        concurrent step execution and sandbox I/O.

        Args:
            step_id: ID of the step to update
            status: New status (completed, in_progress, failed, blocked, skipped)
            result: Optional result summary
            findings: Optional list of key findings from this step
        """
        if not self._state:
            logger.warning("TaskStateManager not initialized")
            return

        async with self._write_lock:
            # Normalize step_id for consistent matching
            step_id = str(step_id)
            found = False

            if status == "completed":
                found = self._state.mark_step_completed(step_id, result)
            elif status == "in_progress":
                found = self._state.mark_step_in_progress(step_id)
            elif status == "failed":
                # Handle failed status by marking step
                for step in self._state.steps:
                    if str(step["id"]) == step_id:
                        step["status"] = "failed"
                        if result:
                            step["result"] = result
                        found = True
                        break
                self._state.last_updated = datetime.now()
            elif status == "blocked":
                # Handle blocked status (dependencies not satisfied or upstream failure)
                for step in self._state.steps:
                    if str(step["id"]) == step_id:
                        step["status"] = "blocked"
                        if result:
                            step["result"] = result
                        found = True
                        break
                self._state.last_updated = datetime.now()
            elif status == "skipped":
                # Handle skipped status (iteration limit reached, etc.)
                for step in self._state.steps:
                    if str(step["id"]) == step_id:
                        step["status"] = "skipped"
                        if result:
                            step["result"] = result
                        found = True
                        break
                self._state.last_updated = datetime.now()

            if not found:
                available_ids = [str(s["id"]) for s in self._state.steps]
                logger.warning(f"Step {step_id} not found in task state. Available step IDs: {available_ids}")

            if findings:
                for finding in findings:
                    self._state.add_finding(finding)

            logger.debug(f"Step {step_id} updated to {status} (found={found})")

    async def add_finding(self, finding: str) -> None:
        """Add a key finding to the task state."""
        if self._state:
            async with self._write_lock:
                self._state.add_finding(finding)

    def record_url(self, url: str) -> bool:
        """Record a visited URL (thread-safe, no async needed since sets are append-only)."""
        if self._state:
            return self._state.record_url(url)
        return False

    def record_query(self, query: str) -> bool:
        """Record a search query (thread-safe, no async needed since sets are append-only)."""
        if self._state:
            return self._state.record_query(query)
        return False

    def get_visited_urls(self) -> set[str]:
        """Get the set of visited URLs."""
        if self._state:
            return self._state.visited_urls
        return set()

    def get_searched_queries(self) -> set[str]:
        """Get the set of searched queries."""
        if self._state:
            return self._state.searched_queries
        return set()

    def get_context_signal(self) -> str | None:
        """Get compact context signal for prompt injection"""
        if not self._state:
            return None
        return self._state.to_context_signal()

    def get_markdown(self) -> str | None:
        """Get full markdown representation"""
        if not self._state:
            return None
        return self._state.to_markdown()

    async def save_to_sandbox(self) -> bool:
        """
        Save current state to sandbox file.

        Uses asyncio.Lock to serialize concurrent writes and prevent
        state corruption from parallel step execution.

        Returns:
            True if save successful
        """
        if not self._state or not self._sandbox:
            return False

        async with self._write_lock:
            try:
                content = self._state.to_markdown()
                await self._sandbox.file_write(self._file_path, content)
                logger.debug(f"Task state saved to {self._file_path}")
                return True
            except Exception as e:
                logger.warning(f"Failed to save task state: {e}")
                return False

    async def load_from_sandbox(self) -> bool:
        """
        Load state from sandbox file (for recovery).

        Uses the same lock as save_to_sandbox to prevent read-write races.

        Returns:
            True if load successful
        """
        if not self._sandbox:
            return False

        async with self._write_lock:
            try:
                result = await self._sandbox.file_read(self._file_path)
                content = result.output if hasattr(result, "output") else str(result)
                # Parse basic info from markdown (simplified)
                if "## Objective" in content:
                    # Extract objective
                    obj_start = content.find("## Objective") + len("## Objective")
                    obj_end = content.find("## Progress")
                    objective = content[obj_start:obj_end].strip()

                    if not self._state:
                        self._state = TaskState(objective=objective)
                    else:
                        self._state.objective = objective

                    logger.debug(f"Task state loaded from {self._file_path}")
                    return True
            except Exception as e:
                logger.debug(f"Could not load task state: {e}")
                return False

    def reset(self) -> None:
        """Reset task state"""
        self._state = None
        self._progress_metrics = None
        self._recent_actions = []
        logger.debug("TaskStateManager reset")

    def recreate_from_comprehension(
        self,
        original_objective: str,
        comprehension_summary: str,
        new_steps: list[dict[str, Any]],
        preserve_findings: bool = True,
    ) -> TaskState:
        """
        Recreate task state after comprehending a long/complex message.

        This allows the agent to first understand a complex request fully,
        then recreate the task list with better-structured steps based on
        that understanding.

        Args:
            original_objective: The user's original message/request
            comprehension_summary: Agent's summarized understanding of the request
            new_steps: New list of steps based on comprehension
            preserve_findings: Whether to keep existing key findings

        Returns:
            New TaskState with recreated steps
        """
        old_findings = []
        if preserve_findings and self._state:
            old_findings = self._state.key_findings.copy()

        # Create fresh state with comprehension context
        self._state = TaskState(
            objective=f"{original_objective}\n\n[Understood as: {comprehension_summary}]"
            if comprehension_summary
            else original_objective
        )

        # Add the new steps
        for step in new_steps:
            self._state.add_step(
                description=step.get("description", ""),
                status="pending",
                step_id=str(step.get("id", "")),
            )

        # Preserve findings from previous work
        for finding in old_findings:
            self._state.add_finding(finding)

        # Reset progress metrics
        self._progress_metrics = ProgressMetrics(
            steps_completed=0,
            steps_remaining=len(new_steps),
            total_steps=len(new_steps),
            started_at=datetime.now(),
        )

        # Clear recent actions (fresh start)
        self._recent_actions = []

        logger.info(f"TaskStateManager recreated with {len(new_steps)} steps after comprehension")
        return self._state

    def should_trigger_comprehension(self, message: str, threshold_chars: int = 500) -> bool:
        """
        Check if a message is long/complex enough to warrant a comprehension phase.

        Args:
            message: The user's input message
            threshold_chars: Character threshold for triggering comprehension

        Returns:
            True if comprehension phase should be triggered
        """
        if len(message) < threshold_chars:
            return False

        # Additional complexity indicators
        import re

        # Count structured elements that indicate complex requirements
        numbered_items = len(re.findall(r"(?:^|\n)\s*\d+[\.\)]\s", message))
        bullet_items = len(re.findall(r"(?:^|\n)\s*[-*]\s", message))
        sections = len(re.findall(r"(?:^|\n)\s*#+\s", message))  # Markdown headers

        # Many structured items suggest complex requirements
        if numbered_items >= 5 or bullet_items >= 5 or sections >= 3:
            return True

        # Long unstructured text also warrants comprehension
        if len(message) > threshold_chars * 2:
            return True

        return len(message) >= threshold_chars

    # =========================================================================
    # Progress Metrics for Reflection (Phase 2)
    # =========================================================================

    def get_progress_metrics(self) -> ProgressMetrics | None:
        """Get current progress metrics for reflection."""
        return self._progress_metrics

    async def record_action(
        self, function_name: str, success: bool, result: Any = None, error: str | None = None
    ) -> None:
        """Record a tool action for progress tracking and reflection context.

        Serialized via ``_write_lock`` to prevent mutation races.

        Args:
            function_name: Name of the tool function called
            success: Whether the action succeeded
            result: The result of the action (optional)
            error: Error message if failed (optional)
        """
        if not self._progress_metrics:
            return

        async with self._write_lock:
            # Record in progress metrics
            if success:
                self._progress_metrics.record_success()
            else:
                self._progress_metrics.record_failure(error or "Unknown error")

            # Track recent actions for reflection context
            action_record = {
                "function_name": function_name,
                "success": success,
                "result": str(result)[:200] if result else None,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            }
            self._recent_actions.append(action_record)

            # Keep only recent actions
            if len(self._recent_actions) > self._max_recent_actions:
                self._recent_actions = self._recent_actions[-self._max_recent_actions :]

    async def record_step_complete(self, step_id: str, success: bool = True) -> None:
        """Record step completion for progress tracking.

        Args:
            step_id: ID of the completed step
            success: Whether the step was successful
        """
        if self._progress_metrics:
            self._progress_metrics.record_step_completed()

        # Also update task state
        await self.update_step_status(step_id, "completed" if success else "failed")

    def record_no_progress(self) -> None:
        """Record that an action made no meaningful progress (for stall detection)."""
        if self._progress_metrics:
            self._progress_metrics.record_no_progress()

    def get_recent_actions(self) -> list[dict[str, Any]]:
        """Get recent actions for reflection context."""
        return self._recent_actions.copy()

    def get_last_error(self) -> str | None:
        """Get the most recent error message."""
        if self._progress_metrics and self._progress_metrics.errors:
            return self._progress_metrics.errors[-1]
        return None


# Singleton for global access
_task_state_manager: TaskStateManager | None = None


def get_task_state_manager(sandbox=None) -> TaskStateManager:
    """Get or create the global task state manager"""
    global _task_state_manager
    if _task_state_manager is None:
        _task_state_manager = TaskStateManager(sandbox)
    elif sandbox and not _task_state_manager._sandbox:
        _task_state_manager._sandbox = sandbox
    return _task_state_manager
