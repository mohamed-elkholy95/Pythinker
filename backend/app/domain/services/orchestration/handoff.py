"""Handoff protocol for transferring work between agents.

Provides a structured way for agents to:
1. Request handoffs to other agents
2. Transfer context and state
3. Handle handoff responses
4. Track handoff history for debugging
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.domain.exceptions.base import BusinessRuleViolation, HandoffNotFoundException
from app.domain.services.orchestration.agent_types import AgentCapability, AgentType
from app.domain.utils.task_ids import generate_agent_task_id

logger = logging.getLogger(__name__)


class HandoffReason(str, Enum):
    """Reasons for agent handoffs."""

    SPECIALIZATION = "specialization"  # Need specialized skills
    CAPABILITY_REQUIRED = "capability"  # Specific capability needed
    TASK_COMPLETE = "task_complete"  # This agent's part is done
    STUCK = "stuck"  # Agent is stuck, need help
    VERIFICATION = "verification"  # Need output verified
    ERROR_RECOVERY = "error_recovery"  # Handoff due to error
    PARALLEL_EXECUTION = "parallel"  # Spawn parallel agent
    USER_REQUEST = "user_request"  # User requested specific agent


class HandoffStatus(str, Enum):
    """Status of a handoff request."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class HandoffContext:
    """Context to transfer during a handoff.

    Contains all information the receiving agent needs to continue the work.
    Enhanced with step results, shared resources, and rollback support.
    """

    # Task information
    task_description: str
    original_request: str
    current_progress: str

    # Context data
    relevant_files: list[str] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    decisions_made: list[str] = field(default_factory=list)

    # State transfer
    memory_summary: str | None = None
    tool_results: list[dict[str, Any]] = field(default_factory=list)

    # Enhanced: Previous step results (Phase 3.3)
    step_results: dict[str, Any] = field(default_factory=dict)  # step_id -> result
    step_history: list[dict[str, Any]] = field(default_factory=list)  # Ordered list of completed steps

    # Enhanced: Shared resources between agents (Phase 3.3)
    shared_resources: dict[str, Any] = field(default_factory=dict)  # Named resources
    resource_locks: list[str] = field(default_factory=list)  # Resources locked by this handoff

    # Enhanced: Rollback support (Phase 3.3)
    checkpoint_id: str | None = None  # Checkpoint to rollback to on failure
    rollback_enabled: bool = True
    rollback_steps: list[str] = field(default_factory=list)  # Steps to undo on rollback

    # Enhanced: Progress tracking (Phase 3.3)
    workflow_id: str | None = None
    stage_id: str | None = None
    total_steps: int = 0
    completed_steps: int = 0

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_step_result(self, step_id: str) -> Any | None:
        """Get result from a previous step."""
        return self.step_results.get(step_id)

    def add_step_result(self, step_id: str, result: Any) -> None:
        """Add a step result to the context."""
        self.step_results[step_id] = result
        self.step_history.append(
            {
                "step_id": step_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "result_preview": str(result)[:200] if result else None,
            }
        )
        self.completed_steps += 1

    def get_shared_resource(self, name: str) -> Any | None:
        """Get a shared resource by name."""
        return self.shared_resources.get(name)

    def set_shared_resource(self, name: str, value: Any) -> None:
        """Set a shared resource."""
        self.shared_resources[name] = value

    def lock_resource(self, name: str) -> bool:
        """Lock a resource for exclusive access."""
        if name in self.resource_locks:
            return False
        self.resource_locks.append(name)
        return True

    def unlock_resource(self, name: str) -> None:
        """Unlock a resource."""
        if name in self.resource_locks:
            self.resource_locks.remove(name)

    def get_progress_percent(self) -> float:
        """Get progress as percentage."""
        if self.total_steps == 0:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100

    def to_prompt(self) -> str:
        """Convert context to a prompt string for the receiving agent."""
        sections = [
            "## Handoff Context\n",
            f"**Original Request:** {self.original_request}\n",
            f"**Task:** {self.task_description}\n",
            f"**Progress:** {self.current_progress}\n",
        ]

        # Progress tracking
        if self.total_steps > 0:
            sections.append(
                f"**Overall Progress:** {self.completed_steps}/{self.total_steps} "
                f"({self.get_progress_percent():.0f}%)\n"
            )

        if self.relevant_files:
            sections.append("\n**Relevant Files:**\n")
            sections.extend(f"- {f}\n" for f in self.relevant_files)

        if self.key_findings:
            sections.append("\n**Key Findings:**\n")
            sections.extend(f"- {finding}\n" for finding in self.key_findings)

        if self.decisions_made:
            sections.append("\n**Decisions Made:**\n")
            sections.extend(f"- {decision}\n" for decision in self.decisions_made)

        # Previous step results
        if self.step_results:
            sections.append("\n**Previous Step Results:**\n")
            for step_id, result in list(self.step_results.items())[-5:]:  # Last 5
                result_preview = str(result)[:100] if result else "None"
                sections.append(f"- {step_id}: {result_preview}\n")

        # Shared resources
        if self.shared_resources:
            sections.append("\n**Available Shared Resources:**\n")
            sections.extend(f"- {name}\n" for name in self.shared_resources)

        if self.memory_summary:
            sections.append(f"\n**Summary of Previous Work:**\n{self.memory_summary}\n")

        return "".join(sections)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_description": self.task_description,
            "original_request": self.original_request,
            "current_progress": self.current_progress,
            "relevant_files": self.relevant_files,
            "key_findings": self.key_findings,
            "decisions_made": self.decisions_made,
            "memory_summary": self.memory_summary,
            "tool_results": self.tool_results,
            "step_results": self.step_results,
            "step_history": self.step_history,
            "shared_resources": {k: str(v)[:500] for k, v in self.shared_resources.items()},
            "resource_locks": self.resource_locks,
            "checkpoint_id": self.checkpoint_id,
            "rollback_enabled": self.rollback_enabled,
            "rollback_steps": self.rollback_steps,
            "workflow_id": self.workflow_id,
            "stage_id": self.stage_id,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HandoffContext":
        """Create from dictionary."""
        return cls(
            task_description=data.get("task_description", ""),
            original_request=data.get("original_request", ""),
            current_progress=data.get("current_progress", ""),
            relevant_files=data.get("relevant_files", []),
            key_findings=data.get("key_findings", []),
            decisions_made=data.get("decisions_made", []),
            memory_summary=data.get("memory_summary"),
            tool_results=data.get("tool_results", []),
            step_results=data.get("step_results", {}),
            step_history=data.get("step_history", []),
            shared_resources=data.get("shared_resources", {}),
            resource_locks=data.get("resource_locks", []),
            checkpoint_id=data.get("checkpoint_id"),
            rollback_enabled=data.get("rollback_enabled", True),
            rollback_steps=data.get("rollback_steps", []),
            workflow_id=data.get("workflow_id"),
            stage_id=data.get("stage_id"),
            total_steps=data.get("total_steps", 0),
            completed_steps=data.get("completed_steps", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Handoff:
    """A handoff request from one agent to another.

    Represents the complete handoff including request, context, and result.
    """

    id: str = field(default_factory=generate_agent_task_id)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Source and target
    source_agent: AgentType = AgentType.EXECUTOR
    target_agent: AgentType | None = None
    target_capability: AgentCapability | None = None

    # Handoff details
    reason: HandoffReason = HandoffReason.SPECIALIZATION
    context: HandoffContext | None = None
    priority: int = 0  # Higher = more urgent

    # Instructions for target
    instructions: str = ""
    expected_output: str = ""

    # Status tracking
    status: HandoffStatus = HandoffStatus.PENDING
    result: str | None = None
    error: str | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def accept(self) -> None:
        """Mark the handoff as accepted."""
        self.status = HandoffStatus.ACCEPTED
        logger.info(f"Handoff {self.id[:8]} accepted by {self.target_agent}")

    def reject(self, reason: str) -> None:
        """Mark the handoff as rejected."""
        self.status = HandoffStatus.REJECTED
        self.error = reason
        logger.warning(f"Handoff {self.id[:8]} rejected: {reason}")

    def complete(self, result: str) -> None:
        """Mark the handoff as completed with a result."""
        self.status = HandoffStatus.COMPLETED
        self.result = result
        logger.info(f"Handoff {self.id[:8]} completed")

    def fail(self, error: str) -> None:
        """Mark the handoff as failed."""
        self.status = HandoffStatus.FAILED
        self.error = error
        logger.error(f"Handoff {self.id[:8]} failed: {error}")


class HandoffResult(BaseModel):
    """Result of a completed handoff."""

    handoff_id: str
    success: bool
    output: str = ""
    artifacts: list[str] = Field(default_factory=list)  # File paths, etc.
    summary: str = ""
    next_steps: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HandoffProtocol:
    """Protocol for managing handoffs between agents.

    Provides methods for:
    - Creating handoff requests
    - Routing handoffs to appropriate agents
    - Tracking handoff history
    - Aggregating results from multiple handoffs
    """

    def __init__(self, max_history: int = 100):
        self._history: list[Handoff] = []
        self._pending: dict[str, Handoff] = {}
        self._max_history = max_history

        # Callbacks for handoff events
        self._on_handoff_created: list[Callable[[Handoff], Awaitable[None]]] = []
        self._on_handoff_completed: list[Callable[[Handoff], Awaitable[None]]] = []

    def create_handoff(
        self,
        source_agent: AgentType,
        reason: HandoffReason,
        context: HandoffContext,
        target_agent: AgentType | None = None,
        target_capability: AgentCapability | None = None,
        instructions: str = "",
        expected_output: str = "",
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> Handoff:
        """Create a new handoff request.

        Either target_agent or target_capability must be specified.

        Args:
            source_agent: Agent creating the handoff
            reason: Why the handoff is needed
            context: Context to transfer
            target_agent: Specific agent type to hand off to
            target_capability: Capability needed (will select best agent)
            instructions: Specific instructions for the target
            expected_output: What output is expected
            priority: Urgency of the handoff
            metadata: Additional metadata

        Returns:
            The created Handoff object
        """
        if not target_agent and not target_capability:
            raise BusinessRuleViolation("Either target_agent or target_capability must be specified")

        handoff = Handoff(
            source_agent=source_agent,
            target_agent=target_agent,
            target_capability=target_capability,
            reason=reason,
            context=context,
            instructions=instructions,
            expected_output=expected_output,
            priority=priority,
            metadata=metadata or {},
        )

        self._pending[handoff.id] = handoff
        self._add_to_history(handoff)

        logger.info(
            f"Created handoff {handoff.id[:8]}: {source_agent.value} -> "
            f"{target_agent.value if target_agent else f'[{target_capability.value}]'}"
        )

        return handoff

    def create_parallel_handoffs(
        self,
        source_agent: AgentType,
        subtasks: list[dict[str, Any]],
        shared_context: HandoffContext,
    ) -> list[Handoff]:
        """Create multiple handoffs for parallel execution.

        Args:
            source_agent: Agent creating the handoffs
            subtasks: List of subtask specs with keys:
                - target_agent or target_capability
                - instructions
                - expected_output (optional)
            shared_context: Context shared by all subtasks

        Returns:
            List of created Handoff objects
        """
        handoffs = []

        for subtask in subtasks:
            handoff = self.create_handoff(
                source_agent=source_agent,
                reason=HandoffReason.PARALLEL_EXECUTION,
                context=shared_context,
                target_agent=subtask.get("target_agent"),
                target_capability=subtask.get("target_capability"),
                instructions=subtask.get("instructions", ""),
                expected_output=subtask.get("expected_output", ""),
                priority=subtask.get("priority", 0),
            )
            handoffs.append(handoff)

        logger.info(f"Created {len(handoffs)} parallel handoffs from {source_agent.value}")
        return handoffs

    def get_pending(self, target_agent: AgentType | None = None) -> list[Handoff]:
        """Get pending handoffs, optionally filtered by target agent."""
        pending = list(self._pending.values())

        if target_agent:
            pending = [h for h in pending if h.target_agent == target_agent]

        # Sort by priority (descending)
        pending.sort(key=lambda h: h.priority, reverse=True)
        return pending

    def get_handoff(self, handoff_id: str) -> Handoff | None:
        """Get a handoff by ID."""
        if handoff_id in self._pending:
            return self._pending[handoff_id]

        # Check history
        for h in self._history:
            if h.id == handoff_id:
                return h
        return None

    def complete_handoff(
        self,
        handoff_id: str,
        output: str,
        artifacts: list[str] | None = None,
        summary: str = "",
        next_steps: list[str] | None = None,
    ) -> HandoffResult:
        """Mark a handoff as completed and return the result.

        Args:
            handoff_id: ID of the handoff to complete
            output: The output produced
            artifacts: File paths or other artifacts produced
            summary: Summary of what was done
            next_steps: Suggested next steps

        Returns:
            HandoffResult object
        """
        handoff = self._pending.get(handoff_id)
        if not handoff:
            raise HandoffNotFoundException(handoff_id)

        handoff.complete(output)
        del self._pending[handoff_id]

        result = HandoffResult(
            handoff_id=handoff_id,
            success=True,
            output=output,
            artifacts=artifacts or [],
            summary=summary,
            next_steps=next_steps or [],
        )

        logger.info(f"Completed handoff {handoff_id[:8]}")
        return result

    def fail_handoff(self, handoff_id: str, error: str) -> HandoffResult:
        """Mark a handoff as failed.

        Args:
            handoff_id: ID of the handoff
            error: Error message

        Returns:
            HandoffResult indicating failure
        """
        handoff = self._pending.get(handoff_id)
        if not handoff:
            raise HandoffNotFoundException(handoff_id)

        handoff.fail(error)
        del self._pending[handoff_id]

        return HandoffResult(
            handoff_id=handoff_id,
            success=False,
            output="",
            summary=f"Handoff failed: {error}",
        )

    def aggregate_results(self, handoff_ids: list[str]) -> dict[str, Any]:
        """Aggregate results from multiple completed handoffs.

        Args:
            handoff_ids: List of handoff IDs to aggregate

        Returns:
            Aggregated results dictionary
        """
        results = []

        for hid in handoff_ids:
            handoff = self.get_handoff(hid)
            if handoff and handoff.status == HandoffStatus.COMPLETED:
                results.append(
                    {
                        "id": hid,
                        "source": handoff.source_agent.value,
                        "target": handoff.target_agent.value if handoff.target_agent else "unknown",
                        "output": handoff.result,
                    }
                )

        return {
            "total": len(handoff_ids),
            "completed": len(
                [
                    h
                    for h in handoff_ids
                    if self.get_handoff(h) and self.get_handoff(h).status == HandoffStatus.COMPLETED
                ]
            ),
            "failed": len(
                [h for h in handoff_ids if self.get_handoff(h) and self.get_handoff(h).status == HandoffStatus.FAILED]
            ),
            "results": results,
        }

    def get_history(
        self,
        limit: int = 50,
        source_agent: AgentType | None = None,
        target_agent: AgentType | None = None,
    ) -> list[Handoff]:
        """Get handoff history with optional filters.

        Args:
            limit: Maximum number of results
            source_agent: Filter by source agent
            target_agent: Filter by target agent

        Returns:
            List of historical handoffs
        """
        history = self._history.copy()

        if source_agent:
            history = [h for h in history if h.source_agent == source_agent]

        if target_agent:
            history = [h for h in history if h.target_agent == target_agent]

        return history[-limit:]

    def _add_to_history(self, handoff: Handoff) -> None:
        """Add a handoff to history, maintaining max size."""
        self._history.append(handoff)

        # Trim history if needed
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

    def on_handoff_created(self, callback: Callable[[Handoff], Awaitable[None]]) -> None:
        """Register a callback for when handoffs are created."""
        self._on_handoff_created.append(callback)

    def on_handoff_completed(self, callback: Callable[[Handoff], Awaitable[None]]) -> None:
        """Register a callback for when handoffs complete."""
        self._on_handoff_completed.append(callback)

    async def rollback_handoff(
        self,
        handoff_id: str,
        rollback_func: Callable[[list[str]], Awaitable[bool]] | None = None,
    ) -> bool:
        """Rollback a failed handoff.

        If the handoff has rollback enabled and a checkpoint, attempts to
        undo the work performed by the handoff.

        Args:
            handoff_id: ID of the handoff to rollback
            rollback_func: Optional function to execute rollback steps

        Returns:
            True if rollback successful, False otherwise
        """
        handoff = self.get_handoff(handoff_id)
        if not handoff:
            logger.warning(f"Cannot rollback: handoff {handoff_id} not found")
            return False

        if not handoff.context:
            logger.warning(f"Cannot rollback: handoff {handoff_id} has no context")
            return False

        if not handoff.context.rollback_enabled:
            logger.info(f"Rollback disabled for handoff {handoff_id}")
            return False

        # If there are rollback steps and a function, execute them
        if handoff.context.rollback_steps and rollback_func:
            try:
                success = await rollback_func(handoff.context.rollback_steps)
                if success:
                    logger.info(f"Rolled back {len(handoff.context.rollback_steps)} steps for handoff {handoff_id}")
                    # Update handoff status
                    handoff.metadata["rolled_back"] = True
                    handoff.metadata["rollback_time"] = datetime.now(UTC).isoformat()
                    return True
                logger.error(f"Rollback function failed for handoff {handoff_id}")
                return False
            except Exception as e:
                logger.error(f"Rollback error for handoff {handoff_id}: {e}")
                return False

        # If there's a checkpoint ID, we can restore from checkpoint
        if handoff.context.checkpoint_id:
            logger.info(f"Rollback checkpoint available: {handoff.context.checkpoint_id}")
            handoff.metadata["rollback_checkpoint"] = handoff.context.checkpoint_id
            return True

        return False

    def transfer_context(
        self,
        source_handoff_id: str,
        target_handoff: Handoff,
        merge: bool = True,
    ) -> bool:
        """Transfer context from one handoff to another.

        Used for chaining handoffs where results need to flow between agents.

        Args:
            source_handoff_id: ID of the source handoff
            target_handoff: Target handoff to receive context
            merge: If True, merge contexts; if False, replace

        Returns:
            True if transfer successful, False otherwise
        """
        source = self.get_handoff(source_handoff_id)
        if not source or not source.context:
            logger.warning(f"Cannot transfer: source handoff {source_handoff_id} not found or has no context")
            return False

        if not target_handoff.context:
            target_handoff.context = HandoffContext(
                task_description="",
                original_request="",
                current_progress="",
            )

        source_ctx = source.context
        target_ctx = target_handoff.context

        if merge:
            # Merge step results
            target_ctx.step_results.update(source_ctx.step_results)
            target_ctx.step_history.extend(source_ctx.step_history)

            # Merge shared resources
            target_ctx.shared_resources.update(source_ctx.shared_resources)

            # Merge findings and decisions
            target_ctx.key_findings.extend(source_ctx.key_findings)
            target_ctx.decisions_made.extend(source_ctx.decisions_made)

            # Update progress
            target_ctx.completed_steps = max(target_ctx.completed_steps, source_ctx.completed_steps)
        else:
            # Replace with source context (preserving task info)
            task_desc = target_ctx.task_description
            original_req = target_ctx.original_request
            target_handoff.context = source_ctx
            target_handoff.context.task_description = task_desc
            target_handoff.context.original_request = original_req

        logger.info(f"Transferred context from handoff {source_handoff_id} to {target_handoff.id}")
        return True

    def get_workflow_progress(self, workflow_id: str) -> dict[str, Any]:
        """Get progress tracking across all handoffs in a workflow.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Progress summary dictionary
        """
        workflow_handoffs = [h for h in self._history if h.context and h.context.workflow_id == workflow_id]

        total_handoffs = len(workflow_handoffs)
        completed = sum(1 for h in workflow_handoffs if h.status == HandoffStatus.COMPLETED)
        failed = sum(1 for h in workflow_handoffs if h.status == HandoffStatus.FAILED)
        pending = sum(1 for h in workflow_handoffs if h.status == HandoffStatus.PENDING)

        # Aggregate step progress
        total_steps = 0
        completed_steps = 0
        for h in workflow_handoffs:
            if h.context:
                total_steps = max(total_steps, h.context.total_steps)
                completed_steps = max(completed_steps, h.context.completed_steps)

        return {
            "workflow_id": workflow_id,
            "total_handoffs": total_handoffs,
            "completed_handoffs": completed,
            "failed_handoffs": failed,
            "pending_handoffs": pending,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "progress_percent": (completed_steps / total_steps * 100) if total_steps > 0 else 0,
        }

    def build_handoff_prompt(self, handoff: Handoff) -> str:
        """Build a prompt for the receiving agent based on the handoff.

        Args:
            handoff: The handoff to build a prompt for

        Returns:
            Formatted prompt string
        """
        parts = [
            "# Agent Handoff\n",
            f"**From:** {handoff.source_agent.value}\n",
            f"**Reason:** {handoff.reason.value}\n",
        ]

        if handoff.context:
            parts.append(f"\n{handoff.context.to_prompt()}\n")

        if handoff.instructions:
            parts.append(f"\n## Instructions\n{handoff.instructions}\n")

        if handoff.expected_output:
            parts.append(f"\n## Expected Output\n{handoff.expected_output}\n")

        parts.append(
            "\n## Your Task\n"
            "Complete the requested work based on the context and instructions above. "
            "When done, provide a clear summary of what was accomplished.\n"
        )

        return "".join(parts)


# Global protocol instance
_protocol: HandoffProtocol | None = None


def get_handoff_protocol() -> HandoffProtocol:
    """Get the global handoff protocol instance."""
    global _protocol
    if _protocol is None:
        _protocol = HandoffProtocol()
    return _protocol
