import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.session import Session, SessionStatus
from app.domain.models.source_citation import SourceCitation
from app.domain.services.agent_domain_service import AgentDomainService
from app.domain.services.skill_activation_framework import SkillActivationResult


@pytest.mark.asyncio
async def test_reactivation_context_sent_to_task_input_but_not_persisted_as_message_event() -> None:
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.COMPLETED,
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
        input_stream=SimpleNamespace(put=AsyncMock(side_effect=["ctx-evt", "user-evt"])),
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
    service._build_reactivation_context = AsyncMock(
        return_value="[Session history for context]\n[assistant] previous summary"
    )

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
            "app.core.config.get_settings",
            return_value=SimpleNamespace(
                skill_auto_trigger_enabled=True,
                redis_stream_poll_block_ms=100,
            ),
        ),
        patch(
            "app.domain.services.skill_activation_framework.get_skill_activation_framework",
            return_value=framework,
        ),
    ):
        _events = [
            event
            async for event in service.chat(
                session_id="session-id",
                user_id="user-id",
                message="claude code sonnet 5",
            )
        ]

    put_payloads = [json.loads(call.args[0]) for call in task.input_stream.put.await_args_list]
    assert len(put_payloads) >= 2
    assert put_payloads[0]["type"] == "message"
    assert put_payloads[0]["role"] == "assistant"
    assert put_payloads[0]["message"].startswith("[Session history for context]")
    assert put_payloads[1]["role"] == "user"
    assert put_payloads[1]["message"] == "claude code sonnet 5"

    for call in session_repo.add_event.await_args_list:
        evt = call.args[1]
        if getattr(evt, "type", None) != "message":
            continue
        assert not (
            getattr(evt, "role", None) == "assistant"
            and str(getattr(evt, "message", "")).startswith("[Session history for context]")
        )


@pytest.mark.asyncio
async def test_reactivation_hydrates_prior_report_sources_into_new_task() -> None:
    """Verify that persisted sources from prior report events are hydrated
    into the new task during session reactivation."""
    prior_source = SourceCitation(
        url="https://example.com/project",
        title="Example Project",
        snippet="Grounding text from the prior completed run.",
        access_time=datetime(2026, 3, 8, tzinfo=UTC),
        source_type="search",
    )

    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.COMPLETED,
    )

    session_repo = AsyncMock()
    session_repo.find_by_id_and_user_id = AsyncMock(return_value=session)
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.update_latest_message = AsyncMock()
    session_repo.add_event = AsyncMock()
    session_repo.update_mode = AsyncMock()
    session_repo.update_unread_message_count = AsyncMock()

    task = MagicMock()
    task.id = "task-id"
    task.input_stream.put = AsyncMock(return_value="evt-1")
    task.output_stream.get = AsyncMock()
    task.run = AsyncMock()
    task.done = True
    task.hydrate_reactivation_sources = MagicMock()

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
    service._build_reactivation_context = AsyncMock(return_value=None)
    service._build_reactivation_sources = AsyncMock(return_value=[prior_source])

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
            "app.core.config.get_settings",
            return_value=SimpleNamespace(
                skill_auto_trigger_enabled=True,
                redis_stream_poll_block_ms=100,
            ),
        ),
        patch(
            "app.domain.services.skill_activation_framework.get_skill_activation_framework",
            return_value=framework,
        ),
    ):
        _events = [
            event
            async for event in service.chat(
                session_id="session-id",
                user_id="user-id",
                message="Continue the work",
            )
        ]

    task.hydrate_reactivation_sources.assert_called_once()
    hydrated_sources = task.hydrate_reactivation_sources.call_args.args[0]
    assert len(hydrated_sources) == 1
    assert hydrated_sources[0].url == "https://example.com/project"
