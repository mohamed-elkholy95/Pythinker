"""
Task state management for todo recitation.

Maintains a persistent task_state.md file in the sandbox to keep
objectives and progress in the agent's recent attention span.
Based on Manus's recitation approach for improved goal focus.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

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
    steps: List[Dict[str, Any]] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    current_step_index: int = 0
    last_updated: datetime = field(default_factory=datetime.now)

    def add_step(
        self,
        description: str,
        status: str = "pending",
        step_id: Optional[str] = None
    ) -> None:
        """Add a step to the task"""
        self.steps.append({
            "id": step_id or str(len(self.steps) + 1),
            "description": description,
            "status": status,
        })

    def mark_step_completed(
        self,
        step_id: str,
        result: Optional[str] = None
    ) -> None:
        """Mark a step as completed"""
        for step in self.steps:
            if step["id"] == step_id:
                step["status"] = "completed"
                if result:
                    step["result"] = result
                break
        self.last_updated = datetime.now()

    def mark_step_in_progress(self, step_id: str) -> None:
        """Mark a step as in progress"""
        for step in self.steps:
            if step["id"] == step_id:
                step["status"] = "in_progress"
                break
        self.last_updated = datetime.now()

    def add_finding(self, finding: str) -> None:
        """Add a key finding"""
        if finding and finding not in self.key_findings:
            self.key_findings.append(finding)
            # Keep findings list manageable
            if len(self.key_findings) > 10:
                self.key_findings = self.key_findings[-10:]
        self.last_updated = datetime.now()

    def get_current_step(self) -> Optional[Dict[str, Any]]:
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
            timestamp=self.last_updated.strftime("%Y-%m-%d %H:%M:%S")
        )

    def to_context_signal(self) -> str:
        """Generate a compact context signal for prompt injection"""
        # Create a more compact version for context injection
        completed = sum(1 for s in self.steps if s["status"] == "completed")
        total = len(self.steps)
        current = self.get_current_step()

        lines = [
            f"OBJECTIVE: {self.objective[:100]}..." if len(self.objective) > 100 else f"OBJECTIVE: {self.objective}",
            f"PROGRESS: {completed}/{total} steps completed",
        ]

        if current:
            lines.append(f"CURRENT: Step {current['id']} - {current['description'][:80]}")

        if self.key_findings:
            lines.append(f"FINDINGS: {len(self.key_findings)} key results captured")

        return "\n".join(lines)


class TaskStateManager:
    """
    Manages persistent task state for todo recitation.

    Maintains task_state.md in the sandbox and provides state
    for context injection to keep objectives in attention.
    """

    def __init__(self, sandbox=None):
        """
        Initialize the task state manager.

        Args:
            sandbox: Optional sandbox for file operations
        """
        self._sandbox = sandbox
        self._state: Optional[TaskState] = None
        self._file_path = TASK_STATE_PATH

    def initialize_from_plan(
        self,
        objective: str,
        steps: List[Dict[str, Any]]
    ) -> TaskState:
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
                description=step.get("description", ""),
                status="pending",
                step_id=str(step.get("id", ""))
            )

        logger.info(f"TaskStateManager initialized with {len(steps)} steps")
        return self._state

    def update_step_status(
        self,
        step_id: str,
        status: str,
        result: Optional[str] = None,
        findings: Optional[List[str]] = None
    ) -> None:
        """
        Update step status and add any findings.

        Args:
            step_id: ID of the step to update
            status: New status (completed, in_progress, failed)
            result: Optional result summary
            findings: Optional list of key findings from this step
        """
        if not self._state:
            logger.warning("TaskStateManager not initialized")
            return

        if status == "completed":
            self._state.mark_step_completed(step_id, result)
        elif status == "in_progress":
            self._state.mark_step_in_progress(step_id)

        if findings:
            for finding in findings:
                self._state.add_finding(finding)

        logger.debug(f"Step {step_id} updated to {status}")

    def add_finding(self, finding: str) -> None:
        """Add a key finding to the task state"""
        if self._state:
            self._state.add_finding(finding)

    def get_context_signal(self) -> Optional[str]:
        """Get compact context signal for prompt injection"""
        if not self._state:
            return None
        return self._state.to_context_signal()

    def get_markdown(self) -> Optional[str]:
        """Get full markdown representation"""
        if not self._state:
            return None
        return self._state.to_markdown()

    async def save_to_sandbox(self) -> bool:
        """
        Save current state to sandbox file.

        Returns:
            True if save successful
        """
        if not self._state or not self._sandbox:
            return False

        try:
            content = self._state.to_markdown()
            await self._sandbox.write_file(self._file_path, content)
            logger.debug(f"Task state saved to {self._file_path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to save task state: {e}")
            return False

    async def load_from_sandbox(self) -> bool:
        """
        Load state from sandbox file (for recovery).

        Returns:
            True if load successful
        """
        if not self._sandbox:
            return False

        try:
            content = await self._sandbox.read_file(self._file_path)
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

        return False

    def reset(self) -> None:
        """Reset task state"""
        self._state = None
        logger.debug("TaskStateManager reset")


# Singleton for global access
_task_state_manager: Optional[TaskStateManager] = None


def get_task_state_manager(sandbox=None) -> TaskStateManager:
    """Get or create the global task state manager"""
    global _task_state_manager
    if _task_state_manager is None:
        _task_state_manager = TaskStateManager(sandbox)
    elif sandbox and not _task_state_manager._sandbox:
        _task_state_manager._sandbox = sandbox
    return _task_state_manager
