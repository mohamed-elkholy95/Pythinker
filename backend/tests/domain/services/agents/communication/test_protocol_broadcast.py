"""Tests for CommunicationProtocol.broadcast() and await_response()."""

from __future__ import annotations

import asyncio

import pytest

from app.domain.models.agent_message import MessageType
from app.domain.services.agents.communication.protocol import CommunicationProtocol


@pytest.fixture
def proto() -> CommunicationProtocol:
    p = CommunicationProtocol()
    for agent_id in ("agent-a", "agent-b", "agent-c"):
        p.register_agent(agent_id)
    return p


# ── broadcast ────────────────────────────────────────────────────────────────


class TestBroadcast:
    def test_reaches_all_other_agents(self, proto: CommunicationProtocol):
        msgs = proto.broadcast(
            sender_id="agent-a",
            sender_type="test",
            subject="hello",
            content="world",
        )
        # agent-a is the sender; b and c should receive
        assert len(msgs) == 2
        recipients = {m.recipient_id for m in msgs}
        assert recipients == {"agent-b", "agent-c"}

    def test_sender_not_in_recipients(self, proto: CommunicationProtocol):
        msgs = proto.broadcast(sender_id="agent-b", sender_type="test", subject="s", content="c")
        assert all(m.recipient_id != "agent-b" for m in msgs)

    def test_returns_empty_when_only_sender_registered(self):
        p = CommunicationProtocol()
        p.register_agent("solo")
        msgs = p.broadcast(sender_id="solo", sender_type="test", subject="s", content="c")
        assert msgs == []

    def test_messages_stored_in_store(self, proto: CommunicationProtocol):
        msgs = proto.broadcast(sender_id="agent-a", sender_type="test", subject="s", content="c")
        for m in msgs:
            assert m.id in proto._message_store

    def test_messages_delivered_to_inboxes(self, proto: CommunicationProtocol):
        proto.broadcast(sender_id="agent-a", sender_type="test", subject="s", content="c")
        assert len(proto._queues["agent-b"].inbox) >= 1
        assert len(proto._queues["agent-c"].inbox) >= 1

    def test_sender_inbox_not_affected(self, proto: CommunicationProtocol):
        before = len(proto._queues["agent-a"].inbox)
        proto.broadcast(sender_id="agent-a", sender_type="test", subject="s", content="c")
        assert len(proto._queues["agent-a"].inbox) == before

    def test_custom_message_type(self, proto: CommunicationProtocol):
        msgs = proto.broadcast(
            sender_id="agent-a",
            sender_type="test",
            subject="s",
            content="c",
            message_type=MessageType.STATUS_UPDATE,
        )
        assert all(m.message_type == MessageType.STATUS_UPDATE for m in msgs)

    def test_payload_forwarded(self, proto: CommunicationProtocol):
        msgs = proto.broadcast(
            sender_id="agent-a",
            sender_type="test",
            subject="s",
            content="c",
            payload={"key": "value"},
        )
        assert all(m.payload.get("key") == "value" for m in msgs)


# ── await_response ────────────────────────────────────────────────────────────


class TestAwaitResponse:
    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self, proto: CommunicationProtocol):
        # Send a message but never reply
        msg = proto.send_message(
            sender_id="agent-a",
            sender_type="test",
            recipient_id="agent-b",
            message_type=MessageType.INFORMATION_REQUEST,
            subject="q",
            content="hello?",
            requires_response=True,
        )
        reply = await proto.await_response(
            original_message_id=msg.id,
            agent_id="agent-a",
            timeout_seconds=0.05,
        )
        assert reply is None

    @pytest.mark.asyncio
    async def test_finds_reply_in_inbox(self, proto: CommunicationProtocol):
        # a sends to b
        original = proto.send_message(
            sender_id="agent-a",
            sender_type="test",
            recipient_id="agent-b",
            message_type=MessageType.INFORMATION_REQUEST,
            subject="q",
            content="hello?",
            requires_response=True,
        )

        # b replies asynchronously after a short delay
        async def _reply_after_delay():
            await asyncio.sleep(0.02)
            proto.send_message(
                sender_id="agent-b",
                sender_type="test",
                recipient_id="agent-a",
                message_type=MessageType.RESULT_SHARE,
                subject="answer",
                content="pong",
                in_reply_to=original.id,
            )

        reply_task = asyncio.create_task(_reply_after_delay())

        reply = await proto.await_response(
            original_message_id=original.id,
            agent_id="agent-a",
            timeout_seconds=1.0,
            poll_interval=0.01,
        )
        await reply_task
        assert reply is not None
        assert reply.in_reply_to == original.id
        assert reply.sender_id == "agent-b"

    @pytest.mark.asyncio
    async def test_unregistered_agent_returns_none(self, proto: CommunicationProtocol):
        reply = await proto.await_response(
            original_message_id="nonexistent",
            agent_id="ghost",
            timeout_seconds=0.05,
        )
        assert reply is None

    @pytest.mark.asyncio
    async def test_existing_reply_found_immediately(self, proto: CommunicationProtocol):
        # Put a reply in a's inbox before calling await_response
        original = proto.send_message(
            sender_id="agent-a",
            sender_type="test",
            recipient_id="agent-b",
            message_type=MessageType.INFORMATION_REQUEST,
            subject="q",
            content="hello?",
            requires_response=True,
        )
        # b sends reply now (synchronously)
        proto.send_message(
            sender_id="agent-b",
            sender_type="test",
            recipient_id="agent-a",
            message_type=MessageType.RESULT_SHARE,
            subject="a",
            content="pong",
            in_reply_to=original.id,
        )

        reply = await proto.await_response(
            original_message_id=original.id,
            agent_id="agent-a",
            timeout_seconds=1.0,
            poll_interval=0.01,
        )
        assert reply is not None
        assert reply.in_reply_to == original.id
