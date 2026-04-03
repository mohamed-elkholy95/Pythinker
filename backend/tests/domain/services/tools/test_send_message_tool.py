"""Tests for SendMessageTool."""

from __future__ import annotations

import pytest

from app.domain.services.agents.communication.protocol import CommunicationProtocol
from app.domain.services.tools.send_message_tool import SendMessageTool


def _setup(sender: str = "agent-a", receiver: str = "agent-b") -> tuple[SendMessageTool, CommunicationProtocol]:
    protocol = CommunicationProtocol()
    protocol.register_agent(sender)
    protocol.register_agent(receiver)
    tool = SendMessageTool(protocol=protocol, agent_id=sender, agent_type="test")
    return tool, protocol


# ── send_message ──────────────────────────────────────────────────────────────


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_sends_to_recipient(self):
        tool, _ = _setup()
        r = await tool.send_message(subject="hello", content="world", recipient_id="agent-b")
        assert r.success is True
        assert "message_id" in r.data
        assert r.data["recipient"] == "agent-b"

    @pytest.mark.asyncio
    async def test_broadcast_when_no_recipient(self):
        tool, _ = _setup()
        r = await tool.send_message(subject="broadcast", content="to all")
        assert r.success is True
        assert r.data["recipient"] == "broadcast"

    @pytest.mark.asyncio
    async def test_empty_recipient_treated_as_broadcast(self):
        tool, _ = _setup()
        r = await tool.send_message(subject="s", content="c", recipient_id="  ")
        assert r.success is True
        assert r.data["recipient"] == "broadcast"

    @pytest.mark.asyncio
    async def test_empty_subject_rejected(self):
        tool, _ = _setup()
        r = await tool.send_message(subject="", content="body")
        assert r.success is False

    @pytest.mark.asyncio
    async def test_empty_content_rejected(self):
        tool, _ = _setup()
        r = await tool.send_message(subject="hello", content="")
        assert r.success is False

    @pytest.mark.asyncio
    async def test_invalid_message_type_rejected(self):
        tool, _ = _setup()
        r = await tool.send_message(subject="s", content="c", message_type="bogus")
        assert r.success is False
        assert "invalid" in r.message.lower()

    @pytest.mark.asyncio
    async def test_valid_message_types(self):
        tool, _ = _setup()
        for mtype in ["info", "result", "status", "coordination", "error", "feedback"]:
            r = await tool.send_message(subject="s", content="c", message_type=mtype)
            assert r.success is True, f"message_type={mtype} should succeed"

    @pytest.mark.asyncio
    async def test_priority_high(self):
        tool, protocol = _setup()
        r = await tool.send_message(subject="urgent", content="help", recipient_id="agent-b", priority="high")
        assert r.success is True
        msg_id = r.data["message_id"]
        msg = protocol._message_store[msg_id]
        assert msg.priority.value == "high"

    @pytest.mark.asyncio
    async def test_invalid_priority_falls_back_to_normal(self):
        tool, protocol = _setup()
        r = await tool.send_message(subject="s", content="c", priority="invalid_priority")
        assert r.success is True
        msg = protocol._message_store[r.data["message_id"]]
        assert msg.priority.value == "normal"

    @pytest.mark.asyncio
    async def test_requires_response_flag(self):
        tool, protocol = _setup()
        r = await tool.send_message(subject="s", content="c", recipient_id="agent-b", requires_response=True)
        assert r.success is True
        msg = protocol._message_store[r.data["message_id"]]
        assert msg.requires_response is True

    @pytest.mark.asyncio
    async def test_in_reply_to_stored(self):
        tool, protocol = _setup()
        first = await tool.send_message(subject="q", content="question?", recipient_id="agent-b")
        first_id = first.data["message_id"]
        reply = await tool.send_message(subject="a", content="answer", in_reply_to=first_id)
        msg = protocol._message_store[reply.data["message_id"]]
        assert msg.in_reply_to == first_id

    @pytest.mark.asyncio
    async def test_message_delivered_to_recipient_queue(self):
        tool_a, protocol = _setup("agent-a", "agent-b")
        tool_b = SendMessageTool(protocol=protocol, agent_id="agent-b")
        await tool_a.send_message(subject="s", content="c", recipient_id="agent-b")
        # Protocol marks routed messages DELIVERED; use get_messages (not get_pending_messages)
        r = await tool_b.get_messages()
        assert r.data["total"] >= 1
        assert r.data["messages"][0]["sender_id"] == "agent-a"


# ── get_messages ──────────────────────────────────────────────────────────────


class TestGetMessages:
    @pytest.mark.asyncio
    async def test_empty_queue(self):
        tool, _ = _setup()
        r = await tool.get_messages()
        assert r.success is True
        assert r.data["total"] == 0

    @pytest.mark.asyncio
    async def test_receives_sent_message(self):
        tool_a, protocol = _setup("agent-a", "agent-b")
        tool_b = SendMessageTool(protocol=protocol, agent_id="agent-b", agent_type="test")

        # a sends to b
        await tool_a.send_message(subject="hello", content="world", recipient_id="agent-b")

        r = await tool_b.get_messages()
        assert r.success is True
        assert r.data["total"] == 1
        assert r.data["messages"][0]["sender_id"] == "agent-a"

    @pytest.mark.asyncio
    async def test_limit_capped_at_50(self):
        tool, protocol = _setup("agent-a", "agent-b")
        tool_b = SendMessageTool(protocol=protocol, agent_id="agent-b", agent_type="test")

        # a sends many messages to b
        for i in range(60):
            await tool_a_send(tool, subject=f"msg {i}", content="x", recipient_id="agent-b")

        r = await tool_b.get_messages(limit=100)
        assert len(r.data["messages"]) <= 50

    @pytest.mark.asyncio
    async def test_message_summary_fields(self):
        tool_a, protocol = _setup("agent-a", "agent-b")
        tool_b = SendMessageTool(protocol=protocol, agent_id="agent-b")
        await tool_a.send_message(subject="test subject", content="body", message_type="result")
        r = await tool_b.get_messages()
        msg = r.data["messages"][0]
        assert "message_id" in msg
        assert "sender_id" in msg
        assert "type" in msg
        assert "subject" in msg
        assert msg["subject"] == "test subject"

    @pytest.mark.asyncio
    async def test_broadcast_received_by_non_sender(self):
        tool_a, protocol = _setup("agent-a", "agent-b")
        tool_b = SendMessageTool(protocol=protocol, agent_id="agent-b")
        await tool_a.send_message(subject="broadcast", content="to all")  # no recipient
        r = await tool_b.get_messages()
        assert r.data["total"] >= 1


async def tool_a_send(tool: SendMessageTool, **kwargs) -> None:
    await tool.send_message(**kwargs)
