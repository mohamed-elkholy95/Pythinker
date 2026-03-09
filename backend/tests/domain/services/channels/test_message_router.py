"""Tests for MessageRouter — the channel-to-AgentService bridge."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.channel import ChannelType, InboundMessage, MediaAttachment
from app.domain.models.event import MessageEvent, StreamEvent, SuggestionEvent
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


class _FakeGotItAckEvent:
    type = "message"
    role = "assistant"
    message = (
        "Got it! I'll search Reddit and other sources to find current coupon codes and offers for GLM coding plan "
        "and compile a research report for you."
    )


class _DynamicMessageEvent:
    type = "message"
    role = "assistant"

    def __init__(self, message: str) -> None:
        self.message = message


class _DynamicReportEvent:
    type = "report"

    def __init__(self, title: str, content: str) -> None:
        self.title = title
        self.content = content


class SessionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class _FakeSession:
    def __init__(
        self,
        session_id: str = "sess-123",
        status: SessionStatus = SessionStatus.RUNNING,
        reasoning_visibility: str | None = None,
        thinking_level: str | None = None,
        verbose_mode: str | None = None,
        elevated_mode: str | None = None,
    ) -> None:
        self.id = session_id
        self.status = status
        self.created_at = datetime(2026, 3, 2, 12, 0, 0, tzinfo=UTC)
        self.reasoning_visibility = reasoning_visibility
        self.thinking_level = thinking_level
        self.verbose_mode = verbose_mode
        self.elevated_mode = elevated_mode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_inbound(
    content: str = "What is Python?",
    channel: ChannelType = ChannelType.TELEGRAM,
    sender_id: str = "tg-user-42",
    chat_id: str = "tg-chat-99",
    session_key_override: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        chat_id=chat_id,
        content=content,
        session_key_override=session_key_override,
        metadata=metadata or {},
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
    repo.link_channel_to_user = AsyncMock(return_value=None)
    repo.migrate_sessions = AsyncMock()
    repo.migrate_session_ownership = AsyncMock()
    repo.touch_last_inbound_at = AsyncMock()
    repo.touch_last_outbound_at = AsyncMock()
    repo.get_session_activity = AsyncMock(return_value=None)
    repo.set_session_context_summary = AsyncMock()
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
        create_kwargs = agent_svc.create_session.await_args.kwargs
        assert create_kwargs["user_id"] == "user-abc"
        assert create_kwargs["source"] == "telegram"
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
    async def test_route_passes_inbound_media_as_agent_attachments(self) -> None:
        """Telegram media attachments must survive into AgentService.chat()."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        recorded_chat_kwargs: dict[str, Any] = {}

        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])

        async def _recording_chat(**kwargs: Any):
            recorded_chat_kwargs.update(kwargs)
            yield _FakeMessageEvent()

        agent_svc.chat = _recording_chat
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Describe this sticker")
        msg.media = [
            MediaAttachment(
                url="/tmp/sticker.webp",
                mime_type="image/webp",
                filename="sticker.webp",
                size_bytes=321,
                metadata={
                    "type": "sticker",
                    "telegram": {
                        "file_id": "sticker-file-id",
                        "file_unique_id": "unique-sticker",
                        "emoji": "🔥",
                        "set_name": "reactions",
                    },
                },
            ),
            MediaAttachment(
                url="/tmp/voice.ogg",
                mime_type="audio/ogg",
                filename="voice.ogg",
                size_bytes=654,
                metadata={"type": "voice"},
            ),
        ]

        replies = [reply async for reply in router.route_inbound(msg)]

        assert len(replies) == 1
        assert recorded_chat_kwargs["attachments"] == [
            {
                "file_path": "/tmp/sticker.webp",
                "filename": "sticker.webp",
                "content_type": "image/webp",
                "size": 321,
                "type": "sticker",
                "metadata": {
                    "telegram": {
                        "file_id": "sticker-file-id",
                        "file_unique_id": "unique-sticker",
                        "emoji": "🔥",
                        "set_name": "reactions",
                    }
                },
            },
            {
                "file_path": "/tmp/voice.ogg",
                "filename": "voice.ogg",
                "content_type": "audio/ogg",
                "size": 654,
                "type": "voice",
                "metadata": {},
            },
        ]

    @pytest.mark.asyncio
    async def test_route_passes_follow_up_metadata_to_agent_service_chat(self) -> None:
        """Telegram follow-up button taps must reach AgentService.chat() as structured follow_up metadata."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        recorded_chat_kwargs: dict[str, Any] = {}

        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])

        async def _recording_chat(**kwargs: Any):
            recorded_chat_kwargs.update(kwargs)
            yield _FakeMessageEvent()

        agent_svc.chat = _recording_chat
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound(
            "Add examples",
            metadata={
                "message_id": 333,
                "follow_up": {
                    "selected_suggestion": "Add examples",
                    "anchor_event_id": "evt-followup-123",
                    "source": "suggestion_click",
                },
            },
        )
        _ = [reply async for reply in router.route_inbound(msg)]

        assert recorded_chat_kwargs["message"] == "Add examples"
        assert recorded_chat_kwargs["follow_up"] == {
            "selected_suggestion": "Add examples",
            "anchor_event_id": "evt-followup-123",
            "source": "suggestion_click",
        }

    @pytest.mark.asyncio
    async def test_route_prepends_telegram_reply_context_for_agent(self) -> None:
        """Telegram reply metadata should become explicit untrusted context for the agent prompt."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        recorded_chat_kwargs: dict[str, Any] = {}

        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])

        async def _recording_chat(**kwargs: Any):
            recorded_chat_kwargs.update(kwargs)
            yield _FakeMessageEvent()

        agent_svc.chat = _recording_chat
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound(
            "Sure, see below",
            metadata={
                "message_id": 333,
                "reply_to_id": 9001,
                "reply_to_body": "summarize this",
                "reply_to_sender": "Ada",
                "reply_to_is_quote": True,
            },
        )

        _ = [reply async for reply in router.route_inbound(msg)]

        assert agent_svc.create_session.await_args.kwargs["initial_message"] == "Sure, see below"
        assert recorded_chat_kwargs["message"] == (
            "Conversation info (untrusted metadata):\n"
            "```json\n"
            "{\n"
            '  "message_id": 333,\n'
            '  "reply_to_id": 9001\n'
            "}\n"
            "```\n\n"
            "Replied message (untrusted, for context):\n"
            "```json\n"
            "{\n"
            '  "sender_label": "Ada",\n'
            '  "is_quote": true,\n'
            '  "body": "summarize this"\n'
            "}\n"
            "```\n\n"
            "Sure, see below"
        )

    @pytest.mark.asyncio
    async def test_route_reuses_completed_session_for_telegram(self) -> None:
        """Telegram keeps continuity by reusing completed sessions."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="existing-sess")
        completed = _FakeSession("existing-sess", status=SessionStatus.COMPLETED)
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()], session=completed)
        agent_svc.get_session = AsyncMock(return_value=completed)
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Continue in Telegram")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        agent_svc.create_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_route_reuses_completed_session_for_telegram_with_naive_activity_timestamp(self) -> None:
        """Naive activity timestamps should not break Telegram session reuse."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="existing-sess")
        repo.get_session_activity = AsyncMock(
            return_value={
                "last_inbound_at": datetime(2026, 3, 4, 10, 0, 0),  # noqa: DTZ001 - explicit naive-timestamp test case
            }
        )

        completed = _FakeSession("existing-sess", status=SessionStatus.COMPLETED)
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()], session=completed)
        agent_svc.get_session = AsyncMock(return_value=completed)
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Continue in Telegram")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "could not start a session" not in replies[0].content.lower()
        agent_svc.create_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_route_persists_generated_telegram_pdf_artifact(self, tmp_path: Path) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        report_event = _DynamicReportEvent("Research Report", "A" * 500)
        agent_svc = _make_agent_service(events=[report_event])
        agent_svc.persist_generated_artifact = AsyncMock()
        telegram_policy = MagicMock()
        telegram_policy.build_for_event = AsyncMock(
            return_value=[
                MagicMock(
                    content="",
                    channel=ChannelType.TELEGRAM,
                    chat_id="tg-chat-99",
                    reply_to="reply-1",
                    metadata={
                        "delivery_mode": "pdf_only",
                        "content_hash": "abc123",
                        "event_type": "report",
                        "report_title": "Research Report",
                    },
                    media=[
                        MagicMock(
                            url=str(tmp_path / "report.pdf"),
                            mime_type="application/pdf",
                            filename="report.pdf",
                            size_bytes=12,
                        )
                    ],
                )
            ]
        )
        (tmp_path / "report.pdf").write_bytes(b"%PDF-1.4 test")
        router = MessageRouter(agent_svc, repo, telegram_delivery_policy=telegram_policy)

        replies = [r async for r in router.route_inbound(_make_inbound("Create report"))]

        assert len(replies) == 1
        agent_svc.persist_generated_artifact.assert_awaited_once()
        call = agent_svc.persist_generated_artifact.await_args.kwargs
        assert call["session_id"] == "sess-123"
        assert call["content_type"] == "application/pdf"
        assert call["virtual_path"].endswith("/telegram_pdf_abc123.pdf")

    @pytest.mark.asyncio
    async def test_route_completed_session_not_reused_for_non_telegram(self) -> None:
        """Non-Telegram channels keep existing terminal-session rotation behavior."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="existing-sess")
        completed = _FakeSession("existing-sess", status=SessionStatus.COMPLETED)
        new_session = _FakeSession("new-sess", status=SessionStatus.RUNNING)
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()], session=completed)
        agent_svc.get_session = AsyncMock(return_value=completed)
        agent_svc.create_session = AsyncMock(return_value=new_session)
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Continue on web", channel=ChannelType.WEB, chat_id="web-chat-1")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        agent_svc.create_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_route_failed_session_rotates_for_telegram(self) -> None:
        """Failed/cancelled sessions are terminal for Telegram as well."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="existing-sess")
        failed = _FakeSession("existing-sess", status=SessionStatus.FAILED)
        new_session = _FakeSession("new-sess", status=SessionStatus.RUNNING)
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()], session=failed)
        agent_svc.get_session = AsyncMock(return_value=failed)
        agent_svc.create_session = AsyncMock(return_value=new_session)
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Retry after failure")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        agent_svc.create_session.assert_awaited_once()

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
        """Only message, report, error, progress events produce outbound messages."""
        events = [
            _FakePlanEvent(),
            _FakeStepEvent(),
            _FakeToolEvent(),
            _FakeProgressEvent(),
            _FakeMessageEvent(),  # produces visible output
            _FakeDoneEvent(),
        ]
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(events=events)
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Research something")
        replies = [r async for r in router.route_inbound(msg)]

        # Progress events produce heartbeat outbounds (not user-visible)
        visible_replies = [r for r in replies if not r.metadata.get("_progress_heartbeat")]
        assert len(visible_replies) == 1
        assert visible_replies[0].content == "Hello from the agent!"

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

    @pytest.mark.asyncio
    async def test_route_records_inbound_and_outbound_activity(self) -> None:
        """Router records channel-session activity timestamps via repository hooks."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Track activity")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        repo.touch_last_inbound_at.assert_awaited_once_with("user-abc", ChannelType.TELEGRAM, "tg-chat-99")
        repo.touch_last_outbound_at.assert_awaited_once_with("user-abc", ChannelType.TELEGRAM, "tg-chat-99")

    @pytest.mark.asyncio
    async def test_route_sends_long_research_ack_before_agent_reply(self) -> None:
        """Long Telegram research-report prompts receive an immediate 10-15 minute estimate."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound(
            "Create a comprehensive research report comparing GLM, Kimi, MiniMax, Claude, Codex, and Qwen pricing and coding capabilities"
        )
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 2
        assert replies[0].content == (
            "I'm working on the research report and will send it here when it's ready. "
            "This should take about 10-15 minutes."
        )
        assert replies[0].metadata["_telegram_keep_typing"] is True
        assert "This should take about" in replies[0].content
        assert "10-15 minutes" in replies[0].content
        assert replies[1].content == "Hello from the agent!"

    @pytest.mark.asyncio
    async def test_route_sends_short_research_ack_with_faster_estimate(self) -> None:
        """Shorter Telegram research-report prompts receive a faster estimate."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Create a research report about Docker setup basics")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 2
        assert replies[0].content == (
            "I'm working on the research report and will send it here when it's ready. "
            "This should take about 5-10 minutes."
        )
        assert "5-10 minutes" in replies[0].content
        assert replies[1].content == "Hello from the agent!"

    @pytest.mark.asyncio
    async def test_route_sends_coupon_research_ack_with_longer_estimate(self) -> None:
        """Coupon/deal report prompts use the 10-15 minute estimate."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound(
            "Create a research report about latest coupon codes and offers for GLM coding plan from Reddit and other sources"
        )
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 2
        assert "reddit" not in replies[0].content.lower()
        assert "other sources" not in replies[0].content.lower()
        assert "10-15 minutes" in replies[0].content
        assert replies[1].content == "Hello from the agent!"

    @pytest.mark.asyncio
    async def test_route_keeps_research_ack_generic_when_topic_has_no_source_context(self) -> None:
        """Research ack stays generic instead of inferring or expanding source coverage."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Create a research report about GLM coding plan setup")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 2
        assert replies[0].content == (
            "I'm working on the research report and will send it here when it's ready. "
            "This should take about 5-10 minutes."
        )
        assert "5-10 minutes" in replies[0].content
        assert replies[1].content == "Hello from the agent!"

    @pytest.mark.asyncio
    async def test_route_suppresses_generic_agent_got_it_after_router_ack(self) -> None:
        """When router sends ETA acknowledgement, suppress generic first agent 'Got it!' message."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        final_event = _FakeMessageEvent()
        final_event.message = "Final report is ready."
        agent_svc = _make_agent_service(events=[_FakeGotItAckEvent(), final_event])
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound(
            "Create a comprehensive research report comparing GLM pricing plans with coupon sources and references"
        )
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 2
        assert "10-15 minutes" in replies[0].content
        assert "Got it! I'll search Reddit" not in replies[1].content
        assert replies[1].content == "Final report is ready."

    @pytest.mark.asyncio
    async def test_telegram_final_only_emits_only_final_report(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(
            events=[
                _DynamicMessageEvent("Thinking..."),
                _DynamicMessageEvent("Collecting sources..."),
                _DynamicReportEvent("Final Report", "Done."),
            ]
        )
        router = MessageRouter(agent_svc, repo, telegram_final_delivery_only=True)

        msg = _make_inbound("Run task")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "Final Report" in replies[0].content
        assert "Thinking..." not in replies[0].content

    @pytest.mark.asyncio
    async def test_telegram_final_only_falls_back_to_last_message(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(
            events=[
                _DynamicMessageEvent("Phase 1"),
                _DynamicMessageEvent("Phase 2"),
                _DynamicMessageEvent("Final answer"),
            ]
        )
        router = MessageRouter(agent_svc, repo, telegram_final_delivery_only=True)

        msg = _make_inbound("Run task")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert replies[0].content == "Final answer"

    @pytest.mark.asyncio
    async def test_non_telegram_still_streams_intermediate_messages(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(
            events=[
                _DynamicMessageEvent("Step 1"),
                _DynamicMessageEvent("Step 2"),
            ]
        )
        router = MessageRouter(agent_svc, repo, telegram_final_delivery_only=True)

        msg = _make_inbound("Run task", channel=ChannelType.WEB, chat_id="web-chat-42")
        replies = [r async for r in router.route_inbound(msg)]

        assert [reply.content for reply in replies] == ["Step 1", "Step 2"]

    @pytest.mark.asyncio
    async def test_telegram_streaming_emits_preview_outbounds_before_final(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(
            events=[
                StreamEvent(content="Thinking", is_final=False, phase="thinking"),
                StreamEvent(content=" more", is_final=False, phase="thinking"),
                _DynamicMessageEvent("Final answer"),
            ]
        )
        router = MessageRouter(
            agent_svc,
            repo,
            telegram_final_delivery_only=True,
            telegram_streaming="partial",
        )

        inbound = _make_inbound("Run task")
        inbound.metadata["message_id"] = 777
        replies = [r async for r in router.route_inbound(inbound)]

        assert len(replies) == 3
        assert replies[0].content == "Thinking"
        assert replies[0].metadata["message_id"] == 777
        assert replies[0].metadata["_progress"] is True
        assert replies[0].metadata["_telegram_stream"] is True
        assert replies[0].metadata["_telegram_stream_phase"] == "thinking"
        assert replies[0].metadata["_telegram_stream_final"] is False
        assert "_telegram_stream_preview_text" not in replies[0].metadata
        assert replies[1].content == " more"
        assert replies[1].metadata["message_id"] == 777
        assert "_telegram_stream_preview_text" not in replies[1].metadata
        assert replies[-1].metadata["message_id"] == 777
        assert replies[-1].content == "Final answer"

    @pytest.mark.asyncio
    async def test_telegram_streaming_progress_alias_matches_partial_behavior(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(
            events=[
                StreamEvent(content="Thinking", is_final=False, phase="thinking"),
                _DynamicMessageEvent("Final answer"),
            ]
        )
        router = MessageRouter(
            agent_svc,
            repo,
            telegram_final_delivery_only=True,
            telegram_streaming="progress",
        )

        inbound = _make_inbound("Run task", metadata={"message_id": 777})
        replies = [r async for r in router.route_inbound(inbound)]

        assert len(replies) == 2
        assert replies[0].content == "Thinking"
        assert replies[0].metadata["_telegram_stream"] is True
        assert replies[0].metadata["_telegram_stream_final"] is False
        assert replies[1].content == "Final answer"

    @pytest.mark.asyncio
    async def test_telegram_streaming_rotates_preview_across_multiple_assistant_messages(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(
            events=[
                StreamEvent(content="Draft one", is_final=False, phase="thinking"),
                _DynamicMessageEvent("First answer"),
                StreamEvent(content="Draft two", is_final=False, phase="thinking"),
                _DynamicMessageEvent("Second answer"),
            ]
        )
        router = MessageRouter(
            agent_svc,
            repo,
            telegram_final_delivery_only=True,
            telegram_streaming="partial",
        )

        inbound = _make_inbound("Run task", metadata={"message_id": 777})
        replies = [r async for r in router.route_inbound(inbound)]

        assert [reply.content for reply in replies] == [
            "Draft one",
            "First answer",
            "Draft two",
            "Second answer",
        ]

    @pytest.mark.asyncio
    async def test_telegram_streaming_off_preserves_existing_final_only_behavior(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        agent_svc = _make_agent_service(
            events=[
                StreamEvent(content="Thinking", is_final=False, phase="thinking"),
                _DynamicMessageEvent("Final answer"),
            ]
        )
        router = MessageRouter(
            agent_svc,
            repo,
            telegram_final_delivery_only=True,
            telegram_streaming="off",
        )

        replies = [r async for r in router.route_inbound(_make_inbound("Run task"))]

        assert len(replies) == 1
        assert replies[0].content == "Final answer"


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
# Tests — Telegram strict account-link requirement
# ---------------------------------------------------------------------------


class TestTelegramLinkRequiredMode:
    @pytest.mark.asyncio
    async def test_unlinked_telegram_message_is_blocked_when_link_required(self) -> None:
        """Strict mode blocks unlinked Telegram messages before auto-registration."""
        repo = _make_user_channel_repo(user_id=None, session_id=None)
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(
            agent_svc,
            repo,
            telegram_require_linked_account=True,
        )

        msg = _make_inbound("hello from unlinked telegram")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "link your telegram account" in replies[0].content.lower()
        repo.create_channel_user.assert_not_awaited()
        agent_svc.create_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unlinked_telegram_link_command_allowed_when_link_required(self) -> None:
        """Strict mode still allows /link for unlinked Telegram senders."""
        import json

        repo = _make_user_channel_repo(user_id=None, session_id=None)
        agent_svc = _make_agent_service()

        link_code = "ABC123"
        web_user_id = "web-user-xyz"
        mock_store = AsyncMock()
        mock_store.get = AsyncMock(return_value=json.dumps({"user_id": web_user_id, "channel": "telegram"}))
        mock_store.delete = AsyncMock()

        router = MessageRouter(
            agent_svc,
            repo,
            link_code_store=mock_store,
            telegram_require_linked_account=True,
        )

        msg = _make_inbound(f"/link {link_code}")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert "linked" in replies[0].content.lower()
        repo.link_channel_to_user.assert_awaited_once_with(
            ChannelType.TELEGRAM,
            "tg-user-42",
            web_user_id,
        )
        repo.create_channel_user.assert_not_awaited()
        agent_svc.create_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_linked_telegram_user_routes_normally_when_link_required(self) -> None:
        """Linked Telegram users continue normal chat flow in strict mode."""
        repo = _make_user_channel_repo(user_id="user-linked-1", session_id=None)
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(
            agent_svc,
            repo,
            telegram_require_linked_account=True,
        )

        msg = _make_inbound("hello once linked")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert replies[0].content == "Hello from the agent!"
        repo.create_channel_user.assert_not_awaited()
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

    @pytest.mark.asyncio
    async def test_commands_alias_returns_command_list(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc")
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("/commands")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        assert replies[0].content == HELP_TEXT


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


class TestSlashPdf:
    @pytest.mark.asyncio
    async def test_pdf_without_recent_response_returns_hint(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc")
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/pdf"))]

        assert len(replies) == 1
        assert "No recent assistant response" in replies[0].content

    @pytest.mark.asyncio
    async def test_pdf_uses_last_response_and_returns_document(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-1")
        long_reply = _FakeMessageEvent()
        long_reply.message = "Research summary. " * 250
        agent_svc = _make_agent_service(events=[long_reply])
        router = MessageRouter(agent_svc, repo)

        # Prime the latest response cache.
        primed_replies = [r async for r in router.route_inbound(_make_inbound("generate report"))]

        pdf_replies = [r async for r in router.route_inbound(_make_inbound("/pdf"))]
        assert len(pdf_replies) == 1
        assert pdf_replies[0].media
        assert pdf_replies[0].metadata["delivery_mode"] == "pdf_only"

        for reply in [*primed_replies, *pdf_replies]:
            for media in reply.media:
                Path(media.url).unlink(missing_ok=True)


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

    def test_stream_event_preserves_real_partial_text_and_thread_metadata(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock(), telegram_streaming="partial")
        source = _make_inbound(
            metadata={
                "message_id": 777,
                "message_thread_id": 42,
                "is_forum": True,
            }
        )

        result = router._event_to_outbound(
            StreamEvent(content="Thinking", is_final=False, phase="thinking"),
            source,
        )

        assert result is not None
        assert result.content == "Thinking"
        assert result.reply_to == source.id
        assert result.metadata == {
            "message_id": 777,
            "message_thread_id": 42,
            "is_forum": True,
            "_progress": True,
            "_telegram_stream": True,
            "_telegram_stream_phase": "thinking",
            "_telegram_stream_lane": "answer",
            "_telegram_stream_final": False,
        }

    def test_stream_event_reasoning_lane_passes_through_for_telegram(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock(), telegram_streaming="partial")
        source = _make_inbound(metadata={"message_id": 100})

        result = router._event_to_outbound(
            StreamEvent(content="Planning step 1", is_final=False, phase="thinking", lane="reasoning"),
            source,
        )

        assert result is not None
        assert result.metadata["_telegram_stream_lane"] == "reasoning"
        assert result.content == "Planning step 1"

    def test_stream_event_reasoning_lane_suppressed_for_non_telegram(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock(), telegram_streaming="partial")
        source = _make_inbound(metadata={"message_id": 100})
        source.channel = ChannelType.WEB  # type: ignore[assignment]

        result = router._event_to_outbound(
            StreamEvent(content="Planning", is_final=False, phase="thinking", lane="reasoning"),
            source,
        )

        assert result is None

    def test_message_event_preserves_telegram_message_and_thread_metadata(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock(), telegram_streaming="partial")
        source = _make_inbound(
            metadata={
                "message_id": 888,
                "message_thread_id": 99,
                "is_group": True,
                "is_forum": True,
            }
        )

        result = router._event_to_outbound(_FakeMessageEvent(), source)

        assert result is not None
        assert result.metadata["message_id"] == 888
        assert result.metadata["message_thread_id"] == 99
        assert result.metadata["is_group"] is True
        assert result.metadata["is_forum"] is True

    def test_message_event_merges_delivery_metadata_with_telegram_reply_context(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock(), telegram_streaming="partial")
        source = _make_inbound(
            metadata={
                "message_id": 321,
                "message_thread_id": 12,
                "is_group": True,
            }
        )
        event = MessageEvent(
            message="Choose a mode",
            delivery_metadata={
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "Fast", "callback_data": "mode:fast"}],
                    ]
                }
            },
        )

        result = router._event_to_outbound(event, source)

        assert result is not None
        assert result.metadata == {
            "message_id": 321,
            "message_thread_id": 12,
            "is_group": True,
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "Fast", "callback_data": "mode:fast"}],
                ]
            },
        }

    def test_message_event_with_telegram_action_and_no_text_still_produces_outbound(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock(), telegram_streaming="partial")
        source = _make_inbound(metadata={"message_id": 999})
        event = MessageEvent(
            message="",
            delivery_metadata={
                "telegram_action": {
                    "type": "delete",
                    "message_id": 321,
                }
            },
        )

        result = router._event_to_outbound(event, source)

        assert result is not None
        assert result.content == ""
        assert result.metadata == {
            "message_id": 999,
            "telegram_action": {
                "type": "delete",
                "message_id": 321,
            },
        }

    def test_suggestion_event_produces_telegram_follow_up_buttons(self) -> None:
        router = MessageRouter(MagicMock(), MagicMock(), telegram_streaming="partial")
        source = _make_inbound(
            metadata={
                "message_id": 321,
                "message_thread_id": 12,
                "is_group": True,
            }
        )
        event = SuggestionEvent(
            suggestions=["Add examples", "Explain the tradeoffs"],
            source="completion",
            anchor_event_id="evt-followup-123",
        )

        result = router._event_to_outbound(event, source)

        assert result is not None
        assert result.content == "Follow-up options:"
        assert result.metadata == {
            "message_id": 321,
            "message_thread_id": 12,
            "is_group": True,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "Add examples",
                            "callback_data": "telegram:followup:evt-followup-123:0",
                        }
                    ],
                    [
                        {
                            "text": "Explain the tradeoffs",
                            "callback_data": "telegram:followup:evt-followup-123:1",
                        }
                    ],
                ]
            },
        }


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
    async def test_session_creation_failure_still_sends_immediate_research_ack(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        agent_svc = _make_agent_service()
        agent_svc.create_session = AsyncMock(side_effect=RuntimeError("DB is down"))
        agent_svc.get_session = AsyncMock(return_value=None)
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound(
            "Create a comprehensive research report comparing GLM, Kimi, and Claude pricing and coding performance"
        )
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 2
        assert "10-15 minutes" in replies[0].content
        assert "could not start a session" in replies[1].content.lower()

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

    @pytest.mark.asyncio
    async def test_terminal_session_key_creates_new_session_for_non_telegram(self) -> None:
        """Non-Telegram channels still rotate completed sessions."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="finished-sess")
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])

        terminal_session = _FakeSession("finished-sess", status=SessionStatus.COMPLETED)
        new_session = _FakeSession("new-sess", status=SessionStatus.RUNNING)
        agent_svc.get_session = AsyncMock(return_value=terminal_session)
        agent_svc.create_session = AsyncMock(return_value=new_session)

        router = MessageRouter(agent_svc, repo)
        msg = _make_inbound("Start new task", channel=ChannelType.WEB, chat_id="web-chat-1")
        replies = [r async for r in router.route_inbound(msg)]

        assert len(replies) == 1
        agent_svc.create_session.assert_awaited_once()
        repo.set_session_key.assert_awaited_once_with(
            "user-abc",
            ChannelType.WEB,
            "web-chat-1",
            "new-sess",
        )


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


# ---------------------------------------------------------------------------
# /reasoning command tests
# ---------------------------------------------------------------------------


class TestSlashReasoning:
    @pytest.mark.asyncio
    async def test_reasoning_no_arg_shows_current_level(self) -> None:
        """``/reasoning`` with no argument shows current level."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        session = _FakeSession(reasoning_visibility="stream")
        agent_svc = _make_agent_service(session=session)
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/reasoning"))]

        assert len(replies) == 1
        assert "stream" in replies[0].content
        assert "Valid levels" in replies[0].content

    @pytest.mark.asyncio
    async def test_reasoning_no_arg_defaults_to_off(self) -> None:
        """``/reasoning`` with no session reasoning_visibility defaults to 'off'."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        session = _FakeSession(reasoning_visibility=None)
        agent_svc = _make_agent_service(session=session)
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/reasoning"))]

        assert len(replies) == 1
        assert "off" in replies[0].content

    @pytest.mark.asyncio
    async def test_reasoning_set_on(self) -> None:
        """``/reasoning on`` persists the level and acks."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        agent_svc.update_session_fields = AsyncMock()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/reasoning on"))]

        assert len(replies) == 1
        assert "enabled" in replies[0].content.lower()
        agent_svc.update_session_fields.assert_awaited_once_with(
            "sess-123", "user-abc", {"reasoning_visibility": "on"},
        )

    @pytest.mark.asyncio
    async def test_reasoning_set_stream(self) -> None:
        """``/reasoning stream`` persists and returns Telegram-specific ack."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        agent_svc.update_session_fields = AsyncMock()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/reasoning stream"))]

        assert len(replies) == 1
        assert "stream enabled" in replies[0].content.lower()
        assert "Telegram" in replies[0].content
        agent_svc.update_session_fields.assert_awaited_once_with(
            "sess-123", "user-abc", {"reasoning_visibility": "stream"},
        )

    @pytest.mark.asyncio
    async def test_reasoning_set_off(self) -> None:
        """``/reasoning off`` persists and returns disabled ack."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        agent_svc.update_session_fields = AsyncMock()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/reasoning off"))]

        assert len(replies) == 1
        assert "disabled" in replies[0].content.lower()
        agent_svc.update_session_fields.assert_awaited_once_with(
            "sess-123", "user-abc", {"reasoning_visibility": "off"},
        )

    @pytest.mark.asyncio
    async def test_reasoning_invalid_level(self) -> None:
        """``/reasoning banana`` returns an error listing valid levels."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/reasoning banana"))]

        assert len(replies) == 1
        assert "Unrecognized" in replies[0].content
        assert "banana" in replies[0].content

    @pytest.mark.asyncio
    async def test_reasoning_no_session(self) -> None:
        """``/reasoning`` with no active session defaults to 'off'."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/reasoning"))]

        assert len(replies) == 1
        assert "off" in replies[0].content


# ---------------------------------------------------------------------------
# /think, /verbose, /elevated command tests
# ---------------------------------------------------------------------------


class TestSlashThink:
    @pytest.mark.asyncio
    async def test_think_set_high(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        agent_svc.update_session_fields = AsyncMock()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/think high"))]

        assert len(replies) == 1
        assert "high" in replies[0].content.lower()
        agent_svc.update_session_fields.assert_awaited_once_with(
            "sess-123", "user-abc", {"thinking_level": "high"},
        )

    @pytest.mark.asyncio
    async def test_think_alias_t(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        agent_svc.update_session_fields = AsyncMock()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/t medium"))]

        assert len(replies) == 1
        assert "medium" in replies[0].content.lower()

    @pytest.mark.asyncio
    async def test_think_no_arg_shows_current(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        session = _FakeSession(thinking_level="low")
        agent_svc = _make_agent_service(session=session)
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/think"))]

        assert len(replies) == 1
        assert "low" in replies[0].content

    @pytest.mark.asyncio
    async def test_think_invalid_level(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/think extreme"))]

        assert len(replies) == 1
        assert "Unrecognized" in replies[0].content


class TestSlashVerbose:
    @pytest.mark.asyncio
    async def test_verbose_on(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        agent_svc.update_session_fields = AsyncMock()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/verbose on"))]

        assert len(replies) == 1
        assert "enabled" in replies[0].content.lower()
        agent_svc.update_session_fields.assert_awaited_once_with(
            "sess-123", "user-abc", {"verbose_mode": "on"},
        )

    @pytest.mark.asyncio
    async def test_verbose_alias_v(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        agent_svc.update_session_fields = AsyncMock()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/v off"))]

        assert len(replies) == 1
        assert "disabled" in replies[0].content.lower()


class TestSlashElevated:
    @pytest.mark.asyncio
    async def test_elevated_on(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        agent_svc.update_session_fields = AsyncMock()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/elevated on"))]

        assert len(replies) == 1
        assert "enabled" in replies[0].content.lower()

    @pytest.mark.asyncio
    async def test_elevated_alias_elev(self) -> None:
        repo = _make_user_channel_repo(user_id="user-abc", session_id="sess-123")
        agent_svc = _make_agent_service()
        agent_svc.update_session_fields = AsyncMock()
        router = MessageRouter(agent_svc, repo)

        replies = [r async for r in router.route_inbound(_make_inbound("/elev off"))]

        assert len(replies) == 1
        assert "disabled" in replies[0].content.lower()


# ---------------------------------------------------------------------------
# Telegram context prefix — forward and location blocks
# ---------------------------------------------------------------------------


class TestTelegramContextPrefixForwardLocation:
    """_telegram_reply_context_prefix should include forward and location blocks."""

    @pytest.mark.asyncio
    async def test_forwarded_message_context_included_in_prefix(self) -> None:
        """Forwarded message metadata should appear as a context block."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        recorded_chat_kwargs: dict[str, Any] = {}
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])

        async def _recording_chat(**kwargs: Any):
            recorded_chat_kwargs.update(kwargs)
            yield _FakeMessageEvent()

        agent_svc.chat = _recording_chat
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound(
            "Check this forwarded message",
            metadata={
                "message_id": 100,
                "is_forwarded": True,
                "forward_from": "Alice",
                "forward_date": "2026-03-08T12:00:00",
            },
        )
        _ = [reply async for reply in router.route_inbound(msg)]

        content = recorded_chat_kwargs["message"]
        assert "Forwarded message context (untrusted)" in content
        assert '"forwarded": true' in content
        assert '"from": "Alice"' in content
        assert "Check this forwarded message" in content

    @pytest.mark.asyncio
    async def test_location_context_included_in_prefix(self) -> None:
        """Location metadata should appear as a context block."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        recorded_chat_kwargs: dict[str, Any] = {}
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])

        async def _recording_chat(**kwargs: Any):
            recorded_chat_kwargs.update(kwargs)
            yield _FakeMessageEvent()

        agent_svc.chat = _recording_chat
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound(
            "Where am I?",
            metadata={
                "message_id": 200,
                "location": {"latitude": 30.05, "longitude": 31.23},
            },
        )
        _ = [reply async for reply in router.route_inbound(msg)]

        content = recorded_chat_kwargs["message"]
        assert "Location context:" in content
        assert "30.05" in content
        assert "31.23" in content
        assert "Where am I?" in content

    @pytest.mark.asyncio
    async def test_bare_message_id_does_not_produce_prefix(self) -> None:
        """A message with only message_id (no reply/forward/location) should not get a prefix."""
        repo = _make_user_channel_repo(user_id="user-abc", session_id=None)
        recorded_chat_kwargs: dict[str, Any] = {}
        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])

        async def _recording_chat(**kwargs: Any):
            recorded_chat_kwargs.update(kwargs)
            yield _FakeMessageEvent()

        agent_svc.chat = _recording_chat
        router = MessageRouter(agent_svc, repo)

        msg = _make_inbound("Hello", metadata={"message_id": 300})
        _ = [reply async for reply in router.route_inbound(msg)]

        assert recorded_chat_kwargs["message"] == "Hello"
