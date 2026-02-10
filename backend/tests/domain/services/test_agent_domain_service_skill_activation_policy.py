"""Tests for AgentDomainService skill activation policy wiring."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.session import Session
from app.domain.services.agent_domain_service import AgentDomainService
from app.domain.services.skill_activation_framework import SkillActivationResult


@pytest.mark.asyncio
async def test_chat_uses_configured_auto_trigger_policy():
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
    )

    session_repo = AsyncMock()
    session_repo.find_by_id_and_user_id = AsyncMock(return_value=session)
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.update_latest_message = AsyncMock()
    session_repo.add_event = AsyncMock()
    session_repo.update_mode = AsyncMock()
    session_repo.update_unread_message_count = AsyncMock()

    task = SimpleNamespace(
        id="task-id",
        input_stream=SimpleNamespace(put=AsyncMock(return_value="evt-1")),
        output_stream=SimpleNamespace(get=AsyncMock()),
        run=AsyncMock(),
        done=True,
    )

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=MagicMock(),
        task_cls=MagicMock(),
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
        search_engine=AsyncMock(),
    )
    service._create_task = AsyncMock(return_value=task)
    service._classify_intent_with_context = AsyncMock(return_value=None)
    service._resolve_user_attachments = AsyncMock(return_value=None)

    framework = AsyncMock()
    framework.resolve = AsyncMock(
        return_value=SkillActivationResult(
            skill_ids=[],
            activation_sources={},
            command_skill_id=None,
            auto_trigger_enabled=True,
            auto_triggered_skill_ids=[],
        )
    )

    with (
        patch(
            "app.domain.services.agent_domain_service.get_settings",
            return_value=SimpleNamespace(skill_auto_trigger_enabled=True),
        ),
        patch(
            "app.domain.services.skill_activation_framework.get_skill_activation_framework",
            return_value=framework,
        ),
    ):
        events = [
            event
            async for event in service.chat(
                session_id="session-id",
                user_id="user-id",
                message="plan this implementation",
                skills=["writing-plans"],
            )
        ]

    framework.resolve.assert_awaited_once()
    assert framework.resolve.await_args.kwargs["auto_trigger_enabled"] is True
    task.run.assert_awaited_once()
    assert events
