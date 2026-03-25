"""Tests for agent message domain models."""

import pytest

from app.domain.models.agent_message import (
    AgentMessage,
    MessagePriority,
    MessageStatus,
    MessageType,
)


@pytest.mark.unit
class TestMessageTypeEnum:
    def test_all_values(self) -> None:
        expected = {
            "task_delegation",
            "information_request",
            "information_response",
            "result_share",
            "coordination",
            "status_update",
            "error_report",
            "assistance_request",
            "feedback",
            "acknowledgment",
        }
        assert {t.value for t in MessageType} == expected

    def test_member_count(self) -> None:
        assert len(MessageType) == 10


@pytest.mark.unit
class TestMessagePriorityEnum:
    def test_all_values(self) -> None:
        expected = {"critical", "high", "normal", "low"}
        assert {p.value for p in MessagePriority} == expected


@pytest.mark.unit
class TestMessageStatusEnum:
    def test_all_values(self) -> None:
        expected = {"pending", "delivered", "read", "processing", "completed", "failed"}
        assert {s.value for s in MessageStatus} == expected


@pytest.mark.unit
class TestAgentMessage:
    def _make_msg(self, **kwargs) -> AgentMessage:
        defaults = {
            "message_type": MessageType.TASK_DELEGATION,
            "sender_id": "planner_1",
            "sender_type": "planner",
            "subject": "Research task",
            "content": "Please research X",
        }
        defaults.update(kwargs)
        return AgentMessage(**defaults)

    def test_basic_construction(self) -> None:
        msg = self._make_msg()
        assert msg.sender_id == "planner_1"
        assert msg.priority == MessagePriority.NORMAL
        assert msg.status == MessageStatus.PENDING
        assert msg.recipient_id is None

    def test_with_recipient(self) -> None:
        msg = self._make_msg(recipient_id="executor_1", recipient_type="executor")
        assert msg.recipient_id == "executor_1"

    def test_with_priority(self) -> None:
        msg = self._make_msg(priority=MessagePriority.CRITICAL)
        assert msg.priority == MessagePriority.CRITICAL

    def test_thread_support(self) -> None:
        msg = self._make_msg(thread_id="thread_1", in_reply_to="msg_prev")
        assert msg.thread_id == "thread_1"
        assert msg.in_reply_to == "msg_prev"

    def test_payload(self) -> None:
        msg = self._make_msg(payload={"task_id": "123", "deadline": "1h"})
        assert msg.payload["task_id"] == "123"

    def test_defaults(self) -> None:
        msg = self._make_msg()
        assert msg.payload == {}
        assert msg.correlation_id is None
        assert msg.expires_at is None
        assert msg.delivered_at is None
