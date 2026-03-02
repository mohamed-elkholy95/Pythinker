"""Tests for MessageRouter — the channel-to-AgentService bridge."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.channel import ChannelType, InboundMessage
from app.domain.services.channels.message_router import (
    HELP_TEXT,
    MessageRouter,
    UserChannelRepository,
)

# ---------------------------------------------------------------------------
# Helpers — fake event objects (lightweight stand-ins for domain events)
# ---------------------------------------------------------------------------


class _FakeMessageEvent:
    type = "message"
    role = "assistant"
    message = "Hello from the agent!"


class _FakeUserMessageEvent:
    type = "message"
    role = "user"
    message = "User echo"


class _FakeReportEvent:
    type = "report"
    title = "Research Report"
    content = "Here are the findings..."


class _FakeErrorEvent:
    type = "error"
    error = "Something went wrong"


class _FakePlanEvent:
    type = "plan"


class _FakeStepEvent:
    type = "step"


class _FakeToolEvent:
    type = "tool"


class _FakeDoneEvent:
    type = "done"


class _FakeProgressEvent:
    type = "progress"


class SessionStatus(str, Enum):
    RUNNING = "running"


class _FakeSession:
    def __init__(self, session_id: str = "sess-123") -> None:
        self.id = session_id
        self.status = SessionStatus.RUNNING
        self.created_at = datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_inbound(
    content: str = "What is Python?",
    channel: ChannelType = ChannelType.TELEGRAM,
    sender_id: str = "tg-user-42",
    chat_id: str = "tg-chat-99",
    session_key_override: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        chat_id=chat_id,
        content=content,
        session_key_override=session_key_override,
    )


def _make_user_channel_repo(
    user_id: str | None = "user-abc",
    session_id: str | None = None,
) -> AsyncMock:
    """Build an AsyncMock implementing UserChannelRepository."""
    repo = AsyncMock(spec=UserChannelRepository)
    repo.get_user_by_channel = AsyncMock(return_value=user_id)
    repo.create_channel_user = AsyncMock(return_value="user-new-" + uuid.uuid4().hex[:6])
    repo.get_session_key = AsyncMock(return_value=session_id)
    repo.set_session_key = AsyncMock()
    repo.clear_session_key = AsyncMock()
    return repo


def _make_agent_service(
    events: list[Any] | None = None,
    session: Any | None = None,
) -> AsyncMock:
    """Build an AsyncMock for AgentService."""
    svc = AsyncMock()

    # chat() yields events via an async generator
    async def _fake_chat(**kwargs: Any):
        for evt in events or [_FakeMessageEvent()]:
            yield evt

    svc.chat = _fake_chat

    # create_session returns a Session-like object
    fake_session = session or _FakeSession()
    svc.create_session = AsyncMock(return_value=fake_session)
    svc.get_session = AsyncMock(return_value=fake_session)
    svc.stop_session = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# Tests — routing basics
# ---------------------------------------------------------------------------


class TestRouteInbound:
    @pytest.mark.asyncio
    async def test_route_creates_session_and_yields_reply(self) -> None:
        """Happy path: known user, no existing session -> creates session, returns agent reply."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Hello")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert replies[0].content == "Hello from the agent!"
        assert replies[0].channel == ChannelType.TELEGRAM
        assert replies[0].chat_id == "tg-chat-99"
        assert replies[0].reply_to == msg.id

        # Session was created
        agent_svc.create_session.assert_awaited_once()
        repo.set_session_key.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_route_reuses_existing_session(self) -> None:
        """If the user already has an active session, it is reused."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="existing-sess")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Continue talking")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        # create_session should NOT have been called since session already exists
        agent_svc.create_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_route_uses_session_key_override(self) -> None:
        """session_key_override on InboundMessage is used directly."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="other-sess")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Use this session", session_key_override="override-sess")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        # Should not have created a new session or looked up existing one
        agent_svc.create_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_route_filters_internal_events(self) -> None:
        """Only message, report, error events produce outbound messages."""
        events = [
            _FakePlanEvent(),
            _FakeStepEvent(),
            _FakeToolEvent(),
            _FakeProgressEvent(),
            _FakeMessageEvent(),  # only this should produce output
            _FakeDoneEvent(),
        ]
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(events=events)
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Research something")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert replies[0].content == "Hello from the agent!"

    @pytest.mark.asyncio
    async def test_route_skips_user_echo_events(self) -> None:
        """User-role message events should not produce outbound messages."""
        events = [_FakeUserMessageEvent(), _FakeMessageEvent()]
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(events=events)
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Hello")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert replies[0].content == "Hello from the agent!"


# ---------------------------------------------------------------------------
# Tests — auto-registration
# ---------------------------------------------------------------------------


class TestAutoRegistration:
    @pytest.mark.asyncio
    async def test_unknown_user_gets_auto_registered(self) -> None:
        """When get_user_by_channel returns None, create_channel_user is called."""
        repo = _make_user_channel_repo(user_id=None, session_id=None)
        repo.create_channel_user = AsyncMock(return_value="user-new-xyz")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("First message ever")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        repo.create_channel_user.assert_awaited_once_with(ChannelType.TELEGRAM, "tg-user-42", "tg-chat-99")
        # Session was created for the new user
        agent_svc.create_session.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests — slash commands
# ---------------------------------------------------------------------------


class TestSlashNew:
    @pytest.mark.asyncio
    async def test_new_clears_session(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="old-sess")
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("/new")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "Session cleared" in replies[0].content
        repo.clear_session_key.assert_awaited_once_with("user-abc", ChannelType.TELEGRAM, "tg-chat-99")
        # No agent interaction
        agent_svc.create_session.assert_not_awaited()


class TestSlashHelp:
    @pytest.mark.asyncio
    async def test_help_returns_command_list(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc")
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("/help")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert replies[0].content == HELP_TEXT
        assert "/new" in replies[0].content
        assert "/stop" in replies[0].content
        assert "/status" in replies[0].content
        assert "/help" in replies[0].content


class TestSlashStatus:
    @pytest.mark.asyncio
    async def test_status_shows_active_session(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("/status")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "sess-123" in replies[0].content
        assert "running" in replies[0].content.lower()

    @pytest.mark.asyncio
    async def test_status_no_active_session(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("/status")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "No active session" in replies[0].content


class TestSlashStop:
    @pytest.mark.asyncio
    async def test_stop_cancels_session(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("/stop")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "stopped" in replies[0].content.lower()
        agent_svc.stop_session.assert_awaited_once_with("sess-123", "user-abc")

    @pytest.mark.asyncio
    async def test_stop_no_session(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("/stop")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "No active session" in replies[0].content


# ---------------------------------------------------------------------------
# Tests — event conversion
# ---------------------------------------------------------------------------


class TestEventToOutbound:
    def test_message_event_produces_reply(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock())
        source = _make_inbound()

        result = router._event_to_outbound(_FakeMessageEvent(), source)

        assert result is not None
        assert result.content == "Hello from the agent!"
        assert result.channel == ChannelType.TELEGRAM

    def test_report_event_produces_reply_with_title(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock())
        source = _make_inbound()

        result = router._event_to_outbound(_FakeReportEvent(), source)

        assert result is not None
        assert "Research Report" in result.content
        assert "Here are the findings" in result.content

    def test_error_event_produces_error_reply(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock())
        source = _make_inbound()

        result = router._event_to_outbound(_FakeErrorEvent(), source)

        assert result is not None
        assert "Error:" in result.content
        assert "Something went wrong" in result.content

    def test_internal_events_return_none(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock())
        source = _make_inbound()

        for evt in [_FakePlanEvent(), _FakeStepEvent(), _FakeToolEvent(), _FakeDoneEvent()]:
            assert router._event_to_outbound(evt, source) is None

    def test_user_role_message_returns_none(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock())
        source = _make_inbound()

        result = router._event_to_outbound(_FakeUserMessageEvent(), source)
        assert result is None


# ---------------------------------------------------------------------------
# Tests — error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_session_creation_failure_returns_error_message(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        agent_svc = _make_agent_service()
        agent_svc.create_session = AsyncMock(side_effect=RuntimeError("DB is down"))
        # Also make get_session return None so the router tries to create
        agent_svc.get_session = AsyncMock(return_value=None)
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Hello")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "could not start a session" in replies[0].content.lower()

    @pytest.mark.asyncio
    async def test_agent_chat_error_returns_error_message(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service()

        async def _failing_chat(**kwargs: Any):
            raise RuntimeError("LLM timeout")
            yield  # unreachable — makes this an async generator

        agent_svc.chat = _failing_chat
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Cause an error")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "error occurred" in replies[0].content.lower()

    @pytest.mark.asyncio
    async def test_stop_failure_returns_error_message(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service()
        agent_svc.stop_session = AsyncMock(side_effect=RuntimeError("Cannot stop"))
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("/stop")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "Failed to stop" in replies[0].content


# ---------------------------------------------------------------------------
# Tests — stale session recovery
# ---------------------------------------------------------------------------


class TestStaleSessionRecovery:
    @pytest.mark.asyncio
    async def test_stale_session_key_creates_new_session(self) -> None:
        """When the stored session_id points to a deleted session, a new one is created."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="dead-sess")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        # First call with "dead-sess" returns None (session deleted),
        # second call with new session id returns the session.
        new_session = _FakeSession("new-sess")
        agent_svc.get_session = AsyncMock(side_effect=[None, new_session])
        agent_svc.create_session = AsyncMock(return_value=new_session)
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Hello after deletion")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        agent_svc.create_session.assert_awaited_once()
        repo.set_session_key.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests — edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_message_content_routes_normally(self) -> None:
        """Empty content should not be treated as a slash command."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("")
        replies = [r async for r in router.route_inbound(msg)]

        # Should route through normally (empty content is valid)
        assert len(replies) == 1

    @pytest.mark.asyncio
    async def test_slash_command_case_insensitive(self) -> None:
        """/HELP, /Help, /help should all work."""
        repo = _make_user_channel_repo(user_id="user-abc")
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        for variant in ["/HELP", "/Help", "/help"]:
            msg = _make_inbound(variant)
            replies = [r async for r in router.route_inbound(msg)]
            assert len(replies) == 1
            assert "/new" in replies[0].content

    @pytest.mark.asyncio
    async def test_slash_command_with_extra_text(self) -> None:
        """/new some extra text should still be treated as /new."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="old-sess")
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("/new please reset everything")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "Session cleared" in replies[0].content

    @pytest.mark.asyncio
    async def test_outbound_message_has_correct_reply_to(self) -> None:
        """OutboundMessage.reply_to should reference the inbound message ID."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Track reply_to")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert replies[0].reply_to == msg.id
