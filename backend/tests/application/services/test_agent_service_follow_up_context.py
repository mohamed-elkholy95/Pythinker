"""Test follow_up context propagation through agent_service."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.services.agent_service import AgentService


class DummyLLM:
    model_name = "test"
    temperature = 0.0
    max_tokens = 100


class DummyTask:
    @classmethod
    def create(cls, *_args, **_kwargs):
        raise AssertionError("Task creation should not be invoked in follow_up tests")


class FakeSessionRepository:
    async def save(self, _session) -> None:
        return None

    async def find_by_id(self, _session_id: str):
        return None

    async def find_by_user_id(self, _user_id: str):
        return []


def _build_service() -> AgentService:
    """Build an AgentService with mocked dependencies."""
    agent_repo = AsyncMock()
    agent_repo.save = AsyncMock()

    return AgentService(
        llm=DummyLLM(),
        agent_repository=agent_repo,
        session_repository=FakeSessionRepository(),
        sandbox_cls=MagicMock(),
        task_cls=DummyTask,
        json_parser=MagicMock(),
        file_storage=MagicMock(),
        mcp_repository=MagicMock(),
        search_engine=None,
        memory_service=None,
        mongodb_db=None,
    )


async def _collect_events(generator):
    """Collect all events from an async generator."""
    return [event async for event in generator]


@pytest.mark.asyncio
async def test_chat_accepts_follow_up_parameter():
    """Test that agent_service.chat() accepts follow_up parameter."""
    service = _build_service()

    # Track calls to agent_domain_service.chat
    domain_chat_calls = []

    async def _mock_domain_chat(*args, **kwargs):
        domain_chat_calls.append({"args": args, "kwargs": kwargs})
        if False:  # pragma: no cover
            yield None

    service._agent_domain_service = SimpleNamespace(chat=_mock_domain_chat)

    # Mock settings to avoid validation errors
    mock_settings = MagicMock()
    mock_settings.skill_auto_trigger_enabled = False

    # Call with follow_up parameter
    with patch("app.application.services.agent_service.get_settings", return_value=mock_settings):
        await asyncio.wait_for(
            _collect_events(
                service.chat(
                    session_id="session-1",
                    user_id="user-1",
                    message="hello",
                    follow_up={
                        "selected_suggestion": "Test suggestion",
                        "anchor_event_id": "event-123",
                        "source": "suggestion_click",
                    },
                )
            ),
            timeout=0.5,
        )

    # Verify domain service was called with follow_up fields
    assert len(domain_chat_calls) == 1
    call_kwargs = domain_chat_calls[0]["kwargs"]
    assert call_kwargs["follow_up_selected_suggestion"] == "Test suggestion"
    assert call_kwargs["follow_up_anchor_event_id"] == "event-123"
    assert call_kwargs["follow_up_source"] == "suggestion_click"


@pytest.mark.asyncio
async def test_chat_without_follow_up_maintains_backwards_compatibility():
    """Test that chat works without follow_up (backwards compatibility)."""
    service = _build_service()

    # Track calls to agent_domain_service.chat
    domain_chat_calls = []

    async def _mock_domain_chat(*args, **kwargs):
        domain_chat_calls.append({"args": args, "kwargs": kwargs})
        if False:  # pragma: no cover
            yield None

    service._agent_domain_service = SimpleNamespace(chat=_mock_domain_chat)

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.skill_auto_trigger_enabled = False

    # Call WITHOUT follow_up parameter
    with patch("app.application.services.agent_service.get_settings", return_value=mock_settings):
        await asyncio.wait_for(
            _collect_events(
                service.chat(
                    session_id="session-2",
                    user_id="user-2",
                    message="please analyze this request",
                )
            ),
            timeout=0.5,
        )

    # Verify domain service was called with follow_up fields as None
    assert len(domain_chat_calls) == 1
    call_kwargs = domain_chat_calls[0]["kwargs"]
    assert call_kwargs["follow_up_selected_suggestion"] is None
    assert call_kwargs["follow_up_anchor_event_id"] is None
    assert call_kwargs["follow_up_source"] is None


@pytest.mark.asyncio
async def test_chat_with_empty_follow_up_dict():
    """Test that empty follow_up dict results in None values."""
    service = _build_service()

    # Track calls to agent_domain_service.chat
    domain_chat_calls = []

    async def _mock_domain_chat(*args, **kwargs):
        domain_chat_calls.append({"args": args, "kwargs": kwargs})
        if False:  # pragma: no cover
            yield None

    service._agent_domain_service = SimpleNamespace(chat=_mock_domain_chat)

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.skill_auto_trigger_enabled = False

    # Call with empty follow_up dict
    with patch("app.application.services.agent_service.get_settings", return_value=mock_settings):
        await asyncio.wait_for(
            _collect_events(
                service.chat(
                    session_id="session-3",
                    user_id="user-3",
                    message="hello",
                    follow_up={},
                )
            ),
            timeout=0.5,
        )

    # Verify domain service was called with follow_up fields as None (empty dict)
    assert len(domain_chat_calls) == 1
    call_kwargs = domain_chat_calls[0]["kwargs"]
    assert call_kwargs["follow_up_selected_suggestion"] is None
    assert call_kwargs["follow_up_anchor_event_id"] is None
    assert call_kwargs["follow_up_source"] is None
