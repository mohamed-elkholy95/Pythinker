"""SendMessageTool — agent-accessible inter-agent messaging.

Wraps CommunicationProtocol.send_message() and get_pending_messages()
as agent-visible tools so agents can communicate without direct protocol
access.

The agent using this tool is identified by its agent_id, which is set
at construction time by the infrastructure layer.
"""

from __future__ import annotations

import logging

from app.domain.models.agent_message import MessagePriority, MessageStatus, MessageType
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.communication.protocol import CommunicationProtocol
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool

logger = logging.getLogger(__name__)

# Valid message type values exposed to the agent (subset of MessageType)
_VALID_MESSAGE_TYPES: dict[str, MessageType] = {
    "info": MessageType.INFORMATION_REQUEST,
    "result": MessageType.RESULT_SHARE,
    "status": MessageType.STATUS_UPDATE,
    "coordination": MessageType.COORDINATION,
    "error": MessageType.ERROR_REPORT,
    "feedback": MessageType.FEEDBACK,
}

_VALID_PRIORITIES: dict[str, MessagePriority] = {
    "low": MessagePriority.LOW,
    "normal": MessagePriority.NORMAL,
    "high": MessagePriority.HIGH,
    "critical": MessagePriority.CRITICAL,
}


class SendMessageTool(BaseTool):
    """Lets the agent send messages to other agents and read incoming messages.

    Requires a CommunicationProtocol and the caller's agent_id injected at
    construction time. The caller must already be registered with the protocol.
    """

    name: str = "messaging"

    def __init__(
        self,
        protocol: CommunicationProtocol,
        agent_id: str,
        agent_type: str = "agent",
    ) -> None:
        super().__init__(
            defaults=ToolDefaults(
                category="agent",
                user_facing_name="Send Message",
            )
        )
        self._protocol = protocol
        self._agent_id = agent_id
        self._agent_type = agent_type

    # ── Tools ─────────────────────────────────────────────────────────────────

    @tool(
        name="send_message",
        description=(
            "Send a message to another agent or broadcast to all agents. "
            "Leave recipient_id empty to broadcast. "
            f"Types: {', '.join(_VALID_MESSAGE_TYPES)}. "
            f"Priorities: {', '.join(_VALID_PRIORITIES)}."
        ),
        parameters={
            "subject": {"type": "string", "description": "Short message subject."},
            "content": {"type": "string", "description": "Message body."},
            "recipient_id": {
                "type": "string",
                "description": "Target agent ID. Omit or leave empty to broadcast.",
            },
            "message_type": {
                "type": "string",
                "description": "One of: info, result, status, coordination, error, feedback.",
            },
            "priority": {
                "type": "string",
                "description": "One of: low, normal (default), high, critical.",
            },
            "requires_response": {
                "type": "boolean",
                "description": "Set True to request a reply.",
            },
            "in_reply_to": {
                "type": "string",
                "description": "message_id this is replying to.",
            },
        },
        required=["subject", "content"],
        is_destructive=True,
    )
    async def send_message(
        self,
        subject: str,
        content: str,
        recipient_id: str | None = None,
        message_type: str = "info",
        priority: str = "normal",
        requires_response: bool = False,
        in_reply_to: str | None = None,
    ) -> ToolResult:
        """Send a message via the CommunicationProtocol."""
        if not subject or not subject.strip():
            return ToolResult(success=False, message="'subject' must not be empty.")
        if not content or not content.strip():
            return ToolResult(success=False, message="'content' must not be empty.")

        msg_type = _VALID_MESSAGE_TYPES.get(message_type)
        if msg_type is None:
            return ToolResult(
                success=False,
                message=f"Invalid message_type '{message_type}'. Valid: {', '.join(_VALID_MESSAGE_TYPES)}.",
            )

        msg_priority = _VALID_PRIORITIES.get(priority, MessagePriority.NORMAL)

        recipient = recipient_id.strip() if recipient_id and recipient_id.strip() else None

        try:
            message = self._protocol.send_message(
                sender_id=self._agent_id,
                sender_type=self._agent_type,
                recipient_id=recipient,
                message_type=msg_type,
                subject=subject.strip(),
                content=content.strip(),
                priority=msg_priority,
                requires_response=requires_response,
                in_reply_to=in_reply_to or None,
            )
        except Exception as exc:
            logger.exception("send_message failed")
            return ToolResult(success=False, message=f"Failed to send message: {exc}")

        destination = recipient or "broadcast"
        return ToolResult(
            success=True,
            message=f"Message sent to {destination}. message_id={message.id}",
            data={
                "message_id": message.id,
                "recipient": destination,
                "type": message_type,
                "status": message.status,
            },
        )

    @tool(
        name="get_messages",
        description=(
            "Read pending incoming messages for this agent. Returns up to 'limit' messages (default 10, max 50)."
        ),
        parameters={
            "limit": {
                "type": "integer",
                "description": "Maximum messages to return (default 10, max 50).",
            },
        },
        required=[],
        is_read_only=True,
        is_concurrency_safe=True,
    )
    async def get_messages(self, limit: int = 10) -> ToolResult:
        """Retrieve pending messages for this agent."""
        limit = min(max(1, limit), 50)

        try:
            # get_pending_messages filters for PENDING, but the protocol marks messages
            # DELIVERED upon routing. Read from inbox directly for unread (DELIVERED) messages.
            queue = self._protocol._queues.get(self._agent_id)
            if queue is None:
                return ToolResult(success=False, message=f"Agent '{self._agent_id}' not registered.")
            unread_statuses = {MessageStatus.PENDING, MessageStatus.DELIVERED}
            messages = [m for m in queue.inbox if m.status in unread_statuses]
            messages = messages[:limit]
        except Exception as exc:
            logger.exception("get_messages failed")
            return ToolResult(success=False, message=f"Failed to retrieve messages: {exc}")

        summaries = [
            {
                "message_id": m.id,
                "sender_id": m.sender_id,
                "type": m.message_type.value,
                "subject": m.subject,
                "priority": m.priority.value,
                "requires_response": m.requires_response,
                "in_reply_to": m.in_reply_to,
            }
            for m in messages
        ]

        return ToolResult(
            success=True,
            message=f"{len(summaries)} pending message(s).",
            data={"messages": summaries, "total": len(summaries)},
        )
