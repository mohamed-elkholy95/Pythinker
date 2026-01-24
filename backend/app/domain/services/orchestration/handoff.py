"""Handoff protocol for transferring work between agents.

Provides a structured way for agents to:
1. Request handoffs to other agents
2. Transfer context and state
3. Handle handoff responses
4. Track handoff history for debugging
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from pydantic import BaseModel, Field
import logging
import uuid
import json

from app.domain.services.orchestration.agent_types import AgentType, AgentCapability

logger = logging.getLogger(__name__)


class HandoffReason(str, Enum):
    """Reasons for agent handoffs."""
    SPECIALIZATION = "specialization"       # Need specialized skills
    CAPABILITY_REQUIRED = "capability"      # Specific capability needed
    TASK_COMPLETE = "task_complete"         # This agent's part is done
    STUCK = "stuck"                         # Agent is stuck, need help
    VERIFICATION = "verification"           # Need output verified
    ERROR_RECOVERY = "error_recovery"       # Handoff due to error
    PARALLEL_EXECUTION = "parallel"         # Spawn parallel agent
    USER_REQUEST = "user_request"           # User requested specific agent


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
    """
    # Task information
    task_description: str
    original_request: str
    current_progress: str

    # Context data
    relevant_files: List[str] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    decisions_made: List[str] = field(default_factory=list)

    # State transfer
    memory_summary: Optional[str] = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_prompt(self) -> str:
        """Convert context to a prompt string for the receiving agent."""
        sections = [
            f"## Handoff Context\n",
            f"**Original Request:** {self.original_request}\n",
            f"**Task:** {self.task_description}\n",
            f"**Progress:** {self.current_progress}\n",
        ]

        if self.relevant_files:
            sections.append(f"\n**Relevant Files:**\n")
            for f in self.relevant_files:
                sections.append(f"- {f}\n")

        if self.key_findings:
            sections.append(f"\n**Key Findings:**\n")
            for finding in self.key_findings:
                sections.append(f"- {finding}\n")

        if self.decisions_made:
            sections.append(f"\n**Decisions Made:**\n")
            for decision in self.decisions_made:
                sections.append(f"- {decision}\n")

        if self.memory_summary:
            sections.append(f"\n**Summary of Previous Work:**\n{self.memory_summary}\n")

        return "".join(sections)


@dataclass
class Handoff:
    """A handoff request from one agent to another.

    Represents the complete handoff including request, context, and result.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Source and target
    source_agent: AgentType = AgentType.EXECUTOR
    target_agent: Optional[AgentType] = None
    target_capability: Optional[AgentCapability] = None

    # Handoff details
    reason: HandoffReason = HandoffReason.SPECIALIZATION
    context: Optional[HandoffContext] = None
    priority: int = 0  # Higher = more urgent

    # Instructions for target
    instructions: str = ""
    expected_output: str = ""

    # Status tracking
    status: HandoffStatus = HandoffStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

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
    artifacts: List[str] = Field(default_factory=list)  # File paths, etc.
    summary: str = ""
    next_steps: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HandoffProtocol:
    """Protocol for managing handoffs between agents.

    Provides methods for:
    - Creating handoff requests
    - Routing handoffs to appropriate agents
    - Tracking handoff history
    - Aggregating results from multiple handoffs
    """

    def __init__(self, max_history: int = 100):
        self._history: List[Handoff] = []
        self._pending: Dict[str, Handoff] = {}
        self._max_history = max_history

        # Callbacks for handoff events
        self._on_handoff_created: List[Callable[[Handoff], Awaitable[None]]] = []
        self._on_handoff_completed: List[Callable[[Handoff], Awaitable[None]]] = []

    def create_handoff(
        self,
        source_agent: AgentType,
        reason: HandoffReason,
        context: HandoffContext,
        target_agent: Optional[AgentType] = None,
        target_capability: Optional[AgentCapability] = None,
        instructions: str = "",
        expected_output: str = "",
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
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
            raise ValueError("Either target_agent or target_capability must be specified")

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
        subtasks: List[Dict[str, Any]],
        shared_context: HandoffContext,
    ) -> List[Handoff]:
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

    def get_pending(self, target_agent: Optional[AgentType] = None) -> List[Handoff]:
        """Get pending handoffs, optionally filtered by target agent."""
        pending = list(self._pending.values())

        if target_agent:
            pending = [h for h in pending if h.target_agent == target_agent]

        # Sort by priority (descending)
        pending.sort(key=lambda h: h.priority, reverse=True)
        return pending

    def get_handoff(self, handoff_id: str) -> Optional[Handoff]:
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
        artifacts: Optional[List[str]] = None,
        summary: str = "",
        next_steps: Optional[List[str]] = None,
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
            raise ValueError(f"Handoff {handoff_id} not found or not pending")

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
            raise ValueError(f"Handoff {handoff_id} not found or not pending")

        handoff.fail(error)
        del self._pending[handoff_id]

        return HandoffResult(
            handoff_id=handoff_id,
            success=False,
            output="",
            summary=f"Handoff failed: {error}",
        )

    def aggregate_results(self, handoff_ids: List[str]) -> Dict[str, Any]:
        """Aggregate results from multiple completed handoffs.

        Args:
            handoff_ids: List of handoff IDs to aggregate

        Returns:
            Aggregated results dictionary
        """
        results = []
        all_artifacts = []
        all_summaries = []
        all_next_steps = []

        for hid in handoff_ids:
            handoff = self.get_handoff(hid)
            if handoff and handoff.status == HandoffStatus.COMPLETED:
                results.append({
                    "id": hid,
                    "source": handoff.source_agent.value,
                    "target": handoff.target_agent.value if handoff.target_agent else "unknown",
                    "output": handoff.result,
                })

        return {
            "total": len(handoff_ids),
            "completed": len([h for h in handoff_ids if self.get_handoff(h) and self.get_handoff(h).status == HandoffStatus.COMPLETED]),
            "failed": len([h for h in handoff_ids if self.get_handoff(h) and self.get_handoff(h).status == HandoffStatus.FAILED]),
            "results": results,
        }

    def get_history(
        self,
        limit: int = 50,
        source_agent: Optional[AgentType] = None,
        target_agent: Optional[AgentType] = None,
    ) -> List[Handoff]:
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
            self._history = self._history[-self._max_history:]

    def on_handoff_created(self, callback: Callable[[Handoff], Awaitable[None]]) -> None:
        """Register a callback for when handoffs are created."""
        self._on_handoff_created.append(callback)

    def on_handoff_completed(self, callback: Callable[[Handoff], Awaitable[None]]) -> None:
        """Register a callback for when handoffs complete."""
        self._on_handoff_completed.append(callback)

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
_protocol: Optional[HandoffProtocol] = None


def get_handoff_protocol() -> HandoffProtocol:
    """Get the global handoff protocol instance."""
    global _protocol
    if _protocol is None:
        _protocol = HandoffProtocol()
    return _protocol
