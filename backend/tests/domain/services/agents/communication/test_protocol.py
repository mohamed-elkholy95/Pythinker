"""Tests for CommunicationProtocol inter-agent messaging."""

import pytest

from app.domain.exceptions.base import MessageNotFoundException
from app.domain.models.agent_message import (
    MessagePriority,
    MessageStatus,
    MessageType,
)
from app.domain.services.agents.communication.protocol import (
    CommunicationProtocol,
)


@pytest.fixture
def proto():
    return CommunicationProtocol()


@pytest.fixture
def proto_with_agents(proto):
    proto.register_agent("agent-a")
    proto.register_agent("agent-b")
    proto.register_agent("agent-c")
    return proto


# ─────────────────────────────────────────────────────────────
# Agent registration
# ─────────────────────────────────────────────────────────────


class TestRegistration:
    def test_register_agent(self, proto):
        q = proto.register_agent("a1")
        assert q.agent_id == "a1"

    def test_register_idempotent(self, proto):
        q1 = proto.register_agent("a1")
        q2 = proto.register_agent("a1")
        assert q1 is q2

    def test_unregister(self, proto):
        proto.register_agent("a1")
        proto.unregister_agent("a1")
        assert proto.get_pending_messages("a1") == []

    def test_unregister_nonexistent(self, proto):
        proto.unregister_agent("nope")  # Should not raise


# ─────────────────────────────────────────────────────────────
# Sending messages
# ─────────────────────────────────────────────────────────────


class TestSendMessage:
    def test_send_direct(self, proto_with_agents):
        msg = proto_with_agents.send_message(
            sender_id="agent-a",
            sender_type="worker",
            recipient_id="agent-b",
            message_type=MessageType.INFORMATION_REQUEST,
            subject="Test",
            content="Hello",
        )
        assert msg.sender_id == "agent-a"
        assert msg.recipient_id == "agent-b"
        # Message is delivered (status changes from PENDING to DELIVERED)
        assert msg.status == MessageStatus.DELIVERED
        # Check recipient's inbox directly
        queue = proto_with_agents._queues["agent-b"]
        assert len(queue.inbox) == 1
        assert queue.inbox[0].id == msg.id

    def test_send_broadcast(self, proto_with_agents):
        msg = proto_with_agents.send_message(
            sender_id="agent-a",
            sender_type="worker",
            recipient_id=None,
            message_type=MessageType.STATUS_UPDATE,
            subject="Update",
            content="I'm done",
        )
        assert msg.is_broadcast is True
        # Both b and c should receive, not a
        assert len(proto_with_agents._queues["agent-b"].inbox) == 1
        assert len(proto_with_agents._queues["agent-c"].inbox) == 1
        assert len(proto_with_agents._queues["agent-a"].inbox) == 0

    def test_send_to_unregistered_recipient(self, proto_with_agents):
        msg = proto_with_agents.send_message(
            sender_id="agent-a",
            sender_type="worker",
            recipient_id="unknown",
            message_type=MessageType.INFORMATION_REQUEST,
            subject="Test",
            content="Hello",
        )
        assert msg.status == MessageStatus.FAILED

    def test_message_stored(self, proto_with_agents):
        msg = proto_with_agents.send_message(
            sender_id="agent-a",
            sender_type="worker",
            recipient_id="agent-b",
            message_type=MessageType.COORDINATION,
            subject="Stored",
            content="Check storage",
        )
        assert proto_with_agents.get_message(msg.id) is msg


# ─────────────────────────────────────────────────────────────
# Message status management
# ─────────────────────────────────────────────────────────────


class TestMessageStatus:
    def test_mark_read(self, proto_with_agents):
        msg = proto_with_agents.send_message(
            sender_id="agent-a",
            sender_type="w",
            recipient_id="agent-b",
            message_type=MessageType.COORDINATION,
            subject="S",
            content="C",
        )
        proto_with_agents.mark_message_read(msg.id)
        assert proto_with_agents.get_message(msg.id).status == MessageStatus.READ

    def test_mark_processed(self, proto_with_agents):
        msg = proto_with_agents.send_message(
            sender_id="agent-a",
            sender_type="w",
            recipient_id="agent-b",
            message_type=MessageType.COORDINATION,
            subject="S",
            content="C",
        )
        proto_with_agents.mark_message_processed("agent-b", msg.id)
        assert proto_with_agents.get_message(msg.id).status == MessageStatus.COMPLETED

    def test_get_nonexistent_message(self, proto):
        assert proto.get_message("nope") is None


# ─────────────────────────────────────────────────────────────
# Convenience methods
# ─────────────────────────────────────────────────────────────


class TestConvenienceMethods:
    def test_delegate_task(self, proto_with_agents):
        msg = proto_with_agents.delegate_task(
            sender_id="agent-a",
            sender_type="coordinator",
            recipient_id="agent-b",
            task_id="task-1",
            task_description="Research quantum computing",
        )
        assert msg.message_type == MessageType.TASK_DELEGATION
        assert msg.requires_response is True
        assert "task_id" in msg.payload

    def test_request_information(self, proto_with_agents):
        msg = proto_with_agents.request_information(
            sender_id="agent-a",
            sender_type="researcher",
            recipient_id="agent-b",
            query="What is the capital of France?",
        )
        assert msg.message_type == MessageType.INFORMATION_REQUEST
        assert msg.requires_response is True

    def test_share_result(self, proto_with_agents):
        msg = proto_with_agents.share_result(
            sender_id="agent-b",
            sender_type="researcher",
            recipient_id="agent-a",
            result_type="research_findings",
            result_data={"answer": "Paris"},
            confidence=0.95,
        )
        assert msg.message_type == MessageType.RESULT_SHARE
        assert msg.payload["confidence"] == 0.95

    def test_send_status_update(self, proto_with_agents):
        msg = proto_with_agents.send_status_update(
            sender_id="agent-b",
            sender_type="worker",
            recipient_id="agent-a",
            task_id="task-1",
            status="in_progress",
            progress_percent=50,
        )
        assert msg.message_type == MessageType.STATUS_UPDATE
        assert msg.payload["progress_percent"] == 50

    def test_report_error_recoverable(self, proto_with_agents):
        msg = proto_with_agents.report_error(
            sender_id="agent-b",
            sender_type="worker",
            recipient_id="agent-a",
            error_type="timeout",
            error_message="Request timed out",
            recoverable=True,
        )
        assert msg.priority == MessagePriority.HIGH

    def test_report_error_unrecoverable(self, proto_with_agents):
        msg = proto_with_agents.report_error(
            sender_id="agent-b",
            sender_type="worker",
            recipient_id="agent-a",
            error_type="fatal",
            error_message="Unrecoverable failure",
            recoverable=False,
        )
        assert msg.priority == MessagePriority.CRITICAL
        assert msg.requires_response is True

    def test_send_feedback(self, proto_with_agents):
        msg = proto_with_agents.send_feedback(
            sender_id="agent-a",
            sender_type="reviewer",
            recipient_id="agent-b",
            feedback_type="quality",
            comments="Good work",
            rating=0.9,
        )
        assert msg.message_type == MessageType.FEEDBACK
        assert msg.payload["rating"] == 0.9

    def test_acknowledge(self, proto_with_agents):
        original = proto_with_agents.send_message(
            sender_id="agent-a",
            sender_type="w",
            recipient_id="agent-b",
            message_type=MessageType.TASK_DELEGATION,
            subject="Task",
            content="Do this",
        )
        ack = proto_with_agents.acknowledge(
            sender_id="agent-b",
            sender_type="worker",
            original_message_id=original.id,
        )
        assert ack.message_type == MessageType.ACKNOWLEDGMENT
        assert ack.in_reply_to == original.id

    def test_acknowledge_nonexistent_raises(self, proto_with_agents):
        with pytest.raises(MessageNotFoundException):
            proto_with_agents.acknowledge(
                sender_id="agent-b",
                sender_type="worker",
                original_message_id="nonexistent",
            )


# ─────────────────────────────────────────────────────────────
# Threads
# ─────────────────────────────────────────────────────────────


class TestThreads:
    def test_create_thread(self, proto):
        thread = proto.create_thread("Design Discussion", initial_participants=["a", "b"])
        assert thread.subject == "Design Discussion"
        assert "a" in thread.participants

    def test_get_thread(self, proto):
        thread = proto.create_thread("Topic")
        fetched = proto.get_thread(thread.id)
        assert fetched is thread

    def test_get_nonexistent_thread(self, proto):
        assert proto.get_thread("nope") is None


# ─────────────────────────────────────────────────────────────
# Topic pub/sub
# ─────────────────────────────────────────────────────────────


class TestTopics:
    def test_subscribe_and_publish(self, proto_with_agents):
        proto_with_agents.subscribe_to_topic("agent-b", "alerts")
        proto_with_agents.subscribe_to_topic("agent-c", "alerts")
        msgs = proto_with_agents.publish_to_topic(
            sender_id="agent-a",
            sender_type="monitor",
            topic="alerts",
            subject="High CPU",
            content="CPU at 95%",
        )
        assert len(msgs) == 2

    def test_publish_excludes_sender(self, proto_with_agents):
        proto_with_agents.subscribe_to_topic("agent-a", "updates")
        proto_with_agents.subscribe_to_topic("agent-b", "updates")
        msgs = proto_with_agents.publish_to_topic(
            sender_id="agent-a",
            sender_type="w",
            topic="updates",
            subject="S",
            content="C",
        )
        assert len(msgs) == 1
        assert msgs[0].recipient_id == "agent-b"

    def test_publish_to_empty_topic(self, proto_with_agents):
        msgs = proto_with_agents.publish_to_topic(
            sender_id="agent-a",
            sender_type="w",
            topic="empty",
            subject="S",
            content="C",
        )
        assert msgs == []

    def test_subscribe_idempotent(self, proto):
        proto.register_agent("a1")
        proto.subscribe_to_topic("a1", "topic")
        proto.subscribe_to_topic("a1", "topic")
        assert proto._subscribers["topic"].count("a1") == 1


# ─────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────


class TestStatistics:
    def test_empty_stats(self, proto):
        stats = proto.get_statistics()
        assert stats["total_messages"] == 0
        assert stats["registered_agents"] == 0

    def test_stats_with_messages(self, proto_with_agents):
        proto_with_agents.send_message(
            sender_id="agent-a",
            sender_type="w",
            recipient_id="agent-b",
            message_type=MessageType.COORDINATION,
            subject="S",
            content="C",
        )
        stats = proto_with_agents.get_statistics()
        assert stats["total_messages"] == 1
        assert stats["registered_agents"] == 3
        assert stats["by_type"]["coordination"] == 1
