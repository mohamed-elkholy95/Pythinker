"""
Agent Message domain models for inter-agent communication.

This module defines models for structured agent-to-agent messaging,
enabling collaborative problem-solving between agents.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Types of inter-agent messages."""

    TASK_DELEGATION = "task_delegation"  # Delegate a task to another agent
    INFORMATION_REQUEST = "information_request"  # Request information
    INFORMATION_RESPONSE = "information_response"  # Respond to information request
    RESULT_SHARE = "result_share"  # Share results/findings
    COORDINATION = "coordination"  # Coordination messages
    STATUS_UPDATE = "status_update"  # Progress updates
    ERROR_REPORT = "error_report"  # Report errors
    ASSISTANCE_REQUEST = "assistance_request"  # Request help
    FEEDBACK = "feedback"  # Provide feedback
    ACKNOWLEDGMENT = "acknowledgment"  # Acknowledge receipt


class MessagePriority(str, Enum):
    """Priority levels for messages."""

    CRITICAL = "critical"  # Needs immediate attention
    HIGH = "high"  # Important, handle soon
    NORMAL = "normal"  # Standard priority
    LOW = "low"  # Can wait


class MessageStatus(str, Enum):
    """Status of a message."""

    PENDING = "pending"  # Not yet delivered
    DELIVERED = "delivered"  # Delivered to recipient
    READ = "read"  # Read by recipient
    PROCESSING = "processing"  # Being processed
    COMPLETED = "completed"  # Action completed
    FAILED = "failed"  # Delivery or processing failed


class AgentMessage(BaseModel):
    """A message between agents.

    Represents structured communication between agents
    for collaboration and coordination.
    """

    id: str = Field(default_factory=lambda: f"msg_{datetime.now(UTC).timestamp()}")
    message_type: MessageType
    sender_id: str
    sender_type: str  # planner, executor, critic, etc.
    recipient_id: str | None = None  # None for broadcast
    recipient_type: str | None = None  # Can target by type
    priority: MessagePriority = MessagePriority.NORMAL
    status: MessageStatus = MessageStatus.PENDING

    # Content
    subject: str  # Brief subject/topic
    content: str  # Main message content
    payload: dict[str, Any] = Field(default_factory=dict)  # Structured data

    # References
    in_reply_to: str | None = None  # ID of message being replied to
    thread_id: str | None = None  # Conversation thread ID
    correlation_id: str | None = None  # For tracking related messages

    # Timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    delivered_at: datetime | None = None
    expires_at: datetime | None = None

    # Flags
    requires_response: bool = False
    is_broadcast: bool = False

    def is_expired(self) -> bool:
        """Check if the message has expired."""
        if self.expires_at:
            return datetime.now(UTC) > self.expires_at
        return False

    def mark_delivered(self) -> None:
        """Mark message as delivered."""
        self.status = MessageStatus.DELIVERED
        self.delivered_at = datetime.now(UTC)

    def mark_completed(self) -> None:
        """Mark message as completed."""
        self.status = MessageStatus.COMPLETED


class TaskDelegationPayload(BaseModel):
    """Payload for task delegation messages."""

    task_id: str
    task_description: str
    parent_task_id: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    deadline: datetime | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class InformationRequestPayload(BaseModel):
    """Payload for information request messages."""

    query: str
    query_type: str  # factual, procedural, contextual
    context: str | None = None
    expected_format: str | None = None
    sources_preferred: list[str] = Field(default_factory=list)


class ResultSharePayload(BaseModel):
    """Payload for result sharing messages."""

    result_type: str  # finding, output, analysis, etc.
    result_data: dict[str, Any]
    confidence: float = 0.5
    sources: list[str] = Field(default_factory=list)
    related_task_id: str | None = None


class StatusUpdatePayload(BaseModel):
    """Payload for status update messages."""

    task_id: str
    status: str  # started, in_progress, blocked, completed, failed
    progress_percent: int = 0
    current_step: str | None = None
    issues: list[str] = Field(default_factory=list)
    eta_seconds: float | None = None


class ErrorReportPayload(BaseModel):
    """Payload for error report messages."""

    error_type: str
    error_message: str
    task_id: str | None = None
    recoverable: bool = True
    suggested_actions: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class FeedbackPayload(BaseModel):
    """Payload for feedback messages."""

    feedback_type: str  # review, suggestion, correction
    target_message_id: str | None = None
    target_task_id: str | None = None
    rating: float | None = None  # 0-1 rating if applicable
    comments: str
    actionable_items: list[str] = Field(default_factory=list)


class MessageThread(BaseModel):
    """A thread of related messages.

    Groups related messages together for conversation tracking.
    """

    id: str = Field(default_factory=lambda: f"thread_{datetime.now(UTC).timestamp()}")
    subject: str
    participants: list[str] = Field(default_factory=list)  # Agent IDs
    messages: list[str] = Field(default_factory=list)  # Message IDs
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_closed: bool = False

    def add_message(self, message_id: str) -> None:
        """Add a message to the thread."""
        self.messages.append(message_id)
        self.last_activity = datetime.now(UTC)

    def add_participant(self, agent_id: str) -> None:
        """Add a participant to the thread."""
        if agent_id not in self.participants:
            self.participants.append(agent_id)


class MessageQueue(BaseModel):
    """Queue of messages for an agent.

    Manages incoming and outgoing messages for an agent.
    """

    agent_id: str
    inbox: list[AgentMessage] = Field(default_factory=list)
    outbox: list[AgentMessage] = Field(default_factory=list)
    processed: list[str] = Field(default_factory=list)  # Processed message IDs

    def enqueue_incoming(self, message: AgentMessage) -> None:
        """Add a message to the inbox."""
        self.inbox.append(message)

    def enqueue_outgoing(self, message: AgentMessage) -> None:
        """Add a message to the outbox."""
        self.outbox.append(message)

    def get_pending(self, limit: int = 10) -> list[AgentMessage]:
        """Get pending messages from inbox."""
        pending = [m for m in self.inbox if m.status == MessageStatus.PENDING]
        # Sort by priority
        priority_order = {
            MessagePriority.CRITICAL: 0,
            MessagePriority.HIGH: 1,
            MessagePriority.NORMAL: 2,
            MessagePriority.LOW: 3,
        }
        pending.sort(key=lambda m: priority_order.get(m.priority, 2))
        return pending[:limit]

    def mark_processed(self, message_id: str) -> None:
        """Mark a message as processed."""
        self.processed.append(message_id)

    def clear_expired(self) -> int:
        """Remove expired messages and return count removed."""
        before = len(self.inbox)
        self.inbox = [m for m in self.inbox if not m.is_expired()]
        return before - len(self.inbox)
