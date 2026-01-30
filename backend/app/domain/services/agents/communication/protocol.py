"""
Agent Communication Protocol.

This module provides structured agent-to-agent messaging
for collaboration and coordination between agents.
"""

import logging
from typing import Any

from app.domain.models.agent_message import (
    AgentMessage,
    ErrorReportPayload,
    FeedbackPayload,
    InformationRequestPayload,
    MessagePriority,
    MessageQueue,
    MessageStatus,
    MessageThread,
    MessageType,
    ResultSharePayload,
    StatusUpdatePayload,
    TaskDelegationPayload,
)

logger = logging.getLogger(__name__)


class CommunicationProtocol:
    """Protocol for inter-agent communication.

    Manages message queues, routing, and delivery between agents.
    Enables collaborative problem-solving patterns.
    """

    def __init__(self) -> None:
        """Initialize the communication protocol."""
        self._queues: dict[str, MessageQueue] = {}
        self._threads: dict[str, MessageThread] = {}
        self._message_store: dict[str, AgentMessage] = {}
        self._subscribers: dict[str, list[str]] = {}  # topic -> agent_ids

    def register_agent(self, agent_id: str) -> MessageQueue:
        """Register an agent with the communication protocol.

        Args:
            agent_id: Unique agent identifier

        Returns:
            The agent's message queue
        """
        if agent_id not in self._queues:
            self._queues[agent_id] = MessageQueue(agent_id=agent_id)
            logger.info(f"Registered agent for communication: {agent_id}")
        return self._queues[agent_id]

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent from the protocol."""
        if agent_id in self._queues:
            del self._queues[agent_id]
        # Remove from subscribers
        for topic in self._subscribers:
            if agent_id in self._subscribers[topic]:
                self._subscribers[topic].remove(agent_id)

    def send_message(
        self,
        sender_id: str,
        sender_type: str,
        recipient_id: str | None,
        message_type: MessageType,
        subject: str,
        content: str,
        payload: dict[str, Any] | None = None,
        priority: MessagePriority = MessagePriority.NORMAL,
        requires_response: bool = False,
        in_reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> AgentMessage:
        """Send a message to another agent.

        Args:
            sender_id: Sender agent ID
            sender_type: Sender agent type
            recipient_id: Recipient agent ID (None for broadcast)
            message_type: Type of message
            subject: Message subject
            content: Message content
            payload: Optional structured payload
            priority: Message priority
            requires_response: Whether response is needed
            in_reply_to: ID of message being replied to
            thread_id: Optional thread ID

        Returns:
            The sent message
        """
        message = AgentMessage(
            message_type=message_type,
            sender_id=sender_id,
            sender_type=sender_type,
            recipient_id=recipient_id,
            priority=priority,
            subject=subject,
            content=content,
            payload=payload or {},
            requires_response=requires_response,
            in_reply_to=in_reply_to,
            thread_id=thread_id,
            is_broadcast=recipient_id is None,
        )

        # Store message
        self._message_store[message.id] = message

        # Add to sender's outbox
        if sender_id in self._queues:
            self._queues[sender_id].enqueue_outgoing(message)

        # Route message
        self._route_message(message)

        logger.debug(
            f"Message sent: {message.id} from {sender_id} to {recipient_id or 'broadcast'} ({message_type.value})"
        )

        return message

    def _route_message(self, message: AgentMessage) -> None:
        """Route a message to its recipient(s)."""
        if message.is_broadcast:
            # Deliver to all agents except sender
            for agent_id, queue in self._queues.items():
                if agent_id != message.sender_id:
                    queue.enqueue_incoming(message)
                    message.mark_delivered()
        elif message.recipient_id:
            # Deliver to specific recipient
            if message.recipient_id in self._queues:
                self._queues[message.recipient_id].enqueue_incoming(message)
                message.mark_delivered()
            else:
                logger.warning(f"Recipient not found: {message.recipient_id}")
                message.status = MessageStatus.FAILED
        elif message.recipient_type:
            # Deliver to all agents of a type (handled by registry)
            # For now, mark as pending for type-based routing
            message.status = MessageStatus.PENDING

    def get_pending_messages(
        self,
        agent_id: str,
        limit: int = 10,
    ) -> list[AgentMessage]:
        """Get pending messages for an agent.

        Args:
            agent_id: Agent ID
            limit: Maximum messages to return

        Returns:
            List of pending messages
        """
        if agent_id not in self._queues:
            return []
        return self._queues[agent_id].get_pending(limit)

    def get_message(self, message_id: str) -> AgentMessage | None:
        """Get a message by ID."""
        return self._message_store.get(message_id)

    def mark_message_read(self, message_id: str) -> None:
        """Mark a message as read."""
        message = self._message_store.get(message_id)
        if message:
            message.status = MessageStatus.READ

    def mark_message_processed(
        self,
        agent_id: str,
        message_id: str,
    ) -> None:
        """Mark a message as processed by an agent."""
        message = self._message_store.get(message_id)
        if message:
            message.mark_completed()
        if agent_id in self._queues:
            self._queues[agent_id].mark_processed(message_id)

    # Convenience methods for specific message types

    def delegate_task(
        self,
        sender_id: str,
        sender_type: str,
        recipient_id: str,
        task_id: str,
        task_description: str,
        required_capabilities: list[str] | None = None,
        context: dict[str, Any] | None = None,
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> AgentMessage:
        """Delegate a task to another agent.

        Args:
            sender_id: Sender agent ID
            sender_type: Sender agent type
            recipient_id: Recipient agent ID
            task_id: Task ID to delegate
            task_description: Description of the task
            required_capabilities: Required capabilities
            context: Optional context
            priority: Task priority

        Returns:
            The delegation message
        """
        payload = TaskDelegationPayload(
            task_id=task_id,
            task_description=task_description,
            required_capabilities=required_capabilities or [],
            context=context or {},
        ).model_dump()

        return self.send_message(
            sender_id=sender_id,
            sender_type=sender_type,
            recipient_id=recipient_id,
            message_type=MessageType.TASK_DELEGATION,
            subject=f"Task Delegation: {task_id}",
            content=task_description,
            payload=payload,
            priority=priority,
            requires_response=True,
        )

    def request_information(
        self,
        sender_id: str,
        sender_type: str,
        recipient_id: str | None,
        query: str,
        query_type: str = "factual",
        context: str | None = None,
    ) -> AgentMessage:
        """Request information from another agent.

        Args:
            sender_id: Sender agent ID
            sender_type: Sender agent type
            recipient_id: Recipient agent ID (None for any capable agent)
            query: The information query
            query_type: Type of query (factual, procedural, contextual)
            context: Optional context

        Returns:
            The request message
        """
        payload = InformationRequestPayload(
            query=query,
            query_type=query_type,
            context=context,
        ).model_dump()

        return self.send_message(
            sender_id=sender_id,
            sender_type=sender_type,
            recipient_id=recipient_id,
            message_type=MessageType.INFORMATION_REQUEST,
            subject=f"Information Request: {query[:50]}",
            content=query,
            payload=payload,
            requires_response=True,
        )

    def share_result(
        self,
        sender_id: str,
        sender_type: str,
        recipient_id: str | None,
        result_type: str,
        result_data: dict[str, Any],
        confidence: float = 0.5,
        related_task_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> AgentMessage:
        """Share a result with another agent.

        Args:
            sender_id: Sender agent ID
            sender_type: Sender agent type
            recipient_id: Recipient agent ID (None for broadcast)
            result_type: Type of result
            result_data: The result data
            confidence: Confidence in the result
            related_task_id: Related task ID
            in_reply_to: Message being replied to

        Returns:
            The result message
        """
        payload = ResultSharePayload(
            result_type=result_type,
            result_data=result_data,
            confidence=confidence,
            related_task_id=related_task_id,
        ).model_dump()

        return self.send_message(
            sender_id=sender_id,
            sender_type=sender_type,
            recipient_id=recipient_id,
            message_type=MessageType.RESULT_SHARE,
            subject=f"Result: {result_type}",
            content=f"Sharing {result_type} with confidence {confidence:.2f}",
            payload=payload,
            in_reply_to=in_reply_to,
        )

    def send_status_update(
        self,
        sender_id: str,
        sender_type: str,
        recipient_id: str,
        task_id: str,
        status: str,
        progress_percent: int = 0,
        current_step: str | None = None,
        issues: list[str] | None = None,
    ) -> AgentMessage:
        """Send a status update.

        Args:
            sender_id: Sender agent ID
            sender_type: Sender agent type
            recipient_id: Recipient agent ID
            task_id: Task ID
            status: Current status
            progress_percent: Progress percentage
            current_step: Current step description
            issues: Any issues encountered

        Returns:
            The status update message
        """
        payload = StatusUpdatePayload(
            task_id=task_id,
            status=status,
            progress_percent=progress_percent,
            current_step=current_step,
            issues=issues or [],
        ).model_dump()

        return self.send_message(
            sender_id=sender_id,
            sender_type=sender_type,
            recipient_id=recipient_id,
            message_type=MessageType.STATUS_UPDATE,
            subject=f"Status: {task_id} - {status}",
            content=f"Task {task_id} is {status} ({progress_percent}%)",
            payload=payload,
        )

    def report_error(
        self,
        sender_id: str,
        sender_type: str,
        recipient_id: str,
        error_type: str,
        error_message: str,
        task_id: str | None = None,
        recoverable: bool = True,
        suggested_actions: list[str] | None = None,
    ) -> AgentMessage:
        """Report an error.

        Args:
            sender_id: Sender agent ID
            sender_type: Sender agent type
            recipient_id: Recipient agent ID
            error_type: Type of error
            error_message: Error message
            task_id: Related task ID
            recoverable: Whether error is recoverable
            suggested_actions: Suggested recovery actions

        Returns:
            The error report message
        """
        payload = ErrorReportPayload(
            error_type=error_type,
            error_message=error_message,
            task_id=task_id,
            recoverable=recoverable,
            suggested_actions=suggested_actions or [],
        ).model_dump()

        priority = MessagePriority.CRITICAL if not recoverable else MessagePriority.HIGH

        return self.send_message(
            sender_id=sender_id,
            sender_type=sender_type,
            recipient_id=recipient_id,
            message_type=MessageType.ERROR_REPORT,
            subject=f"Error: {error_type}",
            content=error_message,
            payload=payload,
            priority=priority,
            requires_response=not recoverable,
        )

    def send_feedback(
        self,
        sender_id: str,
        sender_type: str,
        recipient_id: str,
        feedback_type: str,
        comments: str,
        target_message_id: str | None = None,
        target_task_id: str | None = None,
        rating: float | None = None,
        actionable_items: list[str] | None = None,
    ) -> AgentMessage:
        """Send feedback to another agent.

        Args:
            sender_id: Sender agent ID
            sender_type: Sender agent type
            recipient_id: Recipient agent ID
            feedback_type: Type of feedback
            comments: Feedback comments
            target_message_id: Message being given feedback on
            target_task_id: Task being given feedback on
            rating: Optional rating (0-1)
            actionable_items: Actionable suggestions

        Returns:
            The feedback message
        """
        payload = FeedbackPayload(
            feedback_type=feedback_type,
            target_message_id=target_message_id,
            target_task_id=target_task_id,
            rating=rating,
            comments=comments,
            actionable_items=actionable_items or [],
        ).model_dump()

        return self.send_message(
            sender_id=sender_id,
            sender_type=sender_type,
            recipient_id=recipient_id,
            message_type=MessageType.FEEDBACK,
            subject=f"Feedback: {feedback_type}",
            content=comments,
            payload=payload,
        )

    def acknowledge(
        self,
        sender_id: str,
        sender_type: str,
        original_message_id: str,
    ) -> AgentMessage:
        """Send an acknowledgment for a received message.

        Args:
            sender_id: Sender agent ID
            sender_type: Sender agent type
            original_message_id: ID of message being acknowledged

        Returns:
            The acknowledgment message
        """
        original = self.get_message(original_message_id)
        if not original:
            raise ValueError(f"Message not found: {original_message_id}")

        return self.send_message(
            sender_id=sender_id,
            sender_type=sender_type,
            recipient_id=original.sender_id,
            message_type=MessageType.ACKNOWLEDGMENT,
            subject=f"ACK: {original.subject}",
            content=f"Acknowledged message: {original_message_id}",
            in_reply_to=original_message_id,
            thread_id=original.thread_id,
        )

    # Thread management

    def create_thread(
        self,
        subject: str,
        initial_participants: list[str] | None = None,
    ) -> MessageThread:
        """Create a new message thread.

        Args:
            subject: Thread subject
            initial_participants: Initial participant agent IDs

        Returns:
            The created thread
        """
        thread = MessageThread(
            subject=subject,
            participants=initial_participants or [],
        )
        self._threads[thread.id] = thread
        return thread

    def get_thread(self, thread_id: str) -> MessageThread | None:
        """Get a thread by ID."""
        return self._threads.get(thread_id)

    def get_thread_messages(self, thread_id: str) -> list[AgentMessage]:
        """Get all messages in a thread."""
        thread = self._threads.get(thread_id)
        if not thread:
            return []
        return [self._message_store[mid] for mid in thread.messages if mid in self._message_store]

    # Topic subscription

    def subscribe_to_topic(self, agent_id: str, topic: str) -> None:
        """Subscribe an agent to a topic."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        if agent_id not in self._subscribers[topic]:
            self._subscribers[topic].append(agent_id)

    def publish_to_topic(
        self,
        sender_id: str,
        sender_type: str,
        topic: str,
        subject: str,
        content: str,
        payload: dict[str, Any] | None = None,
    ) -> list[AgentMessage]:
        """Publish a message to a topic.

        Args:
            sender_id: Sender agent ID
            sender_type: Sender agent type
            topic: Topic to publish to
            subject: Message subject
            content: Message content
            payload: Optional payload

        Returns:
            List of sent messages (one per subscriber)
        """
        subscribers = self._subscribers.get(topic, [])
        messages = []

        for recipient_id in subscribers:
            if recipient_id != sender_id:
                msg = self.send_message(
                    sender_id=sender_id,
                    sender_type=sender_type,
                    recipient_id=recipient_id,
                    message_type=MessageType.COORDINATION,
                    subject=f"[{topic}] {subject}",
                    content=content,
                    payload=payload or {},
                )
                messages.append(msg)

        return messages

    # Statistics

    def get_statistics(self) -> dict[str, Any]:
        """Get protocol statistics."""
        total_messages = len(self._message_store)
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}

        for msg in self._message_store.values():
            by_type[msg.message_type.value] = by_type.get(msg.message_type.value, 0) + 1
            by_status[msg.status.value] = by_status.get(msg.status.value, 0) + 1

        return {
            "total_messages": total_messages,
            "total_threads": len(self._threads),
            "registered_agents": len(self._queues),
            "by_type": by_type,
            "by_status": by_status,
        }


# Global protocol instance
_protocol: CommunicationProtocol | None = None


def get_communication_protocol() -> CommunicationProtocol:
    """Get or create the global communication protocol."""
    global _protocol
    if _protocol is None:
        _protocol = CommunicationProtocol()
    return _protocol


def reset_communication_protocol() -> None:
    """Reset the global communication protocol."""
    global _protocol
    _protocol = None
