"""Tests for AgentDomainService browser timeout recovery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import FlowMode
from app.domain.models.session import AgentMode
from app.domain.services.agent_domain_service import AgentDomainService

_SAFE_FEATURE_FLAGS: dict[str, bool] = {
    "tree_of_thoughts": False,
    "self_consistency": False,
    "structured_outputs": False,
    "taskgroup_enabled": False,
}


@pytest.mark.asyncio
async def test_create_task_recycles_sandbox_on_browser_timeout():
    old_sandbox = AsyncMock()
    old_sandbox.id = "old-sandbox"
    old_sandbox.get_browser = AsyncMock()
    old_sandbox.destroy = AsyncMock()

    new_sandbox = AsyncMock()
    new_sandbox.id = "new-sandbox"
    new_sandbox.get_browser = AsyncMock()

    class FakeSandbox:
        @classmethod
        async def get(cls, _sandbox_id):
            return old_sandbox

        @classmethod
        async def create(cls):
            return new_sandbox

    session = MagicMock()
    session.id = "session-id"
    session.user_id = "user-id"
    session.agent_id = "agent-id"
    session.sandbox_id = "old-sandbox"
    session.mode = AgentMode.AGENT

    session_repo = AsyncMock()
    session_repo.save = AsyncMock()

    settings = SimpleNamespace(
        workspace_auto_init=False,
        workspace_lazy_init=True,
        workspace_default_project_name="default",
        workspace_default_template="default",
        sandbox_framework_enabled=False,
        sandbox_framework_required=False,
        sandbox_pool_enabled=False,
        enable_multi_agent=False,
        resolved_flow_mode=FlowMode.PLAN_ACT,
        browser_init_timeout=1.0,
    )

    task = MagicMock()
    task.id = "task-id"

    task_cls = MagicMock()
    task_cls.create = MagicMock(return_value=task)

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=FakeSandbox,
        task_cls=task_cls,
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value={})),
        search_engine=AsyncMock(),
    )

    async def fake_wait_for(coro, timeout):  # noqa: ASYNC109
        fake_wait_for.calls += 1
        if fake_wait_for.calls == 1:
            # Close coroutine to avoid "never awaited" warnings
            if hasattr(coro, "close"):
                coro.close()
            raise TimeoutError
        return MagicMock()

    fake_wait_for.calls = 0

    with (
        patch("app.core.config.get_settings", return_value=settings),
        patch("app.core.config.get_feature_flags", return_value=_SAFE_FEATURE_FLAGS),
        patch("app.domain.services.agents.agent_task_factory.asyncio.wait_for", side_effect=fake_wait_for),
    ):
        result = await service._create_task(session)

    assert result is task
    old_sandbox.destroy.assert_awaited_once()
    assert session.sandbox_id == "new-sandbox"


@pytest.mark.asyncio
async def test_create_task_recycles_sandbox_on_browser_readiness_failure():
    old_sandbox = AsyncMock()
    old_sandbox.id = "old-sandbox"
    old_sandbox.verify_browser_ready = AsyncMock(return_value=False)
    old_sandbox.get_browser = AsyncMock()
    old_sandbox.destroy = AsyncMock()

    new_sandbox = AsyncMock()
    new_sandbox.id = "new-sandbox"
    new_sandbox.verify_browser_ready = AsyncMock(return_value=True)
    new_sandbox.get_browser = AsyncMock()

    class FakeSandbox:
        @classmethod
        async def get(cls, _sandbox_id):
            return old_sandbox

        @classmethod
        async def create(cls):
            return new_sandbox

    session = MagicMock()
    session.id = "session-id"
    session.user_id = "user-id"
    session.agent_id = "agent-id"
    session.sandbox_id = "old-sandbox"
    session.mode = AgentMode.AGENT

    session_repo = AsyncMock()
    session_repo.save = AsyncMock()

    settings = SimpleNamespace(
        workspace_auto_init=False,
        workspace_lazy_init=True,
        workspace_default_project_name="default",
        workspace_default_template="default",
        sandbox_framework_enabled=False,
        sandbox_framework_required=False,
        sandbox_pool_enabled=False,
        enable_multi_agent=False,
        resolved_flow_mode=FlowMode.PLAN_ACT,
        browser_init_timeout=1.0,
    )

    task = MagicMock()
    task.id = "task-id"

    task_cls = MagicMock()
    task_cls.create = MagicMock(return_value=task)

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=FakeSandbox,
        task_cls=task_cls,
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value={})),
        search_engine=AsyncMock(),
    )

    with (
        patch("app.core.config.get_settings", return_value=settings),
        patch("app.core.config.get_feature_flags", return_value=_SAFE_FEATURE_FLAGS),
        patch(
            "app.domain.services.agents.agent_task_factory.asyncio.wait_for", return_value=MagicMock()
        ) as wait_for_mock,
    ):
        result = await service._create_task(session)

    assert result is task
    old_sandbox.destroy.assert_awaited_once()
    old_sandbox.get_browser.assert_not_awaited()
    wait_for_mock.assert_called_once()
    assert session.sandbox_id == "new-sandbox"


@pytest.mark.asyncio
async def test_create_task_bypasses_sandbox_pool_when_static_addresses_configured():
    created_sandbox = AsyncMock()
    created_sandbox.id = "sandbox-static"
    created_sandbox.verify_browser_ready = AsyncMock(return_value=True)
    created_sandbox.get_browser = AsyncMock(return_value=MagicMock())

    class FakeSandbox:
        @classmethod
        async def get(cls, _sandbox_id):
            return None

        @classmethod
        async def create(cls):
            return created_sandbox

    session = MagicMock()
    session.id = "session-id"
    session.user_id = "user-id"
    session.agent_id = "agent-id"
    session.sandbox_id = None
    session.mode = AgentMode.AGENT

    session_repo = AsyncMock()
    session_repo.save = AsyncMock()

    settings = SimpleNamespace(
        workspace_auto_init=False,
        workspace_lazy_init=True,
        workspace_default_project_name="default",
        workspace_default_template="default",
        sandbox_framework_enabled=False,
        sandbox_framework_required=False,
        sandbox_pool_enabled=True,
        sandbox_address="sandbox,sandbox2",
        enable_multi_agent=False,
        resolved_flow_mode=FlowMode.PLAN_ACT,
        browser_init_timeout=1.0,
    )

    task = MagicMock()
    task.id = "task-id"
    task_cls = MagicMock()
    task_cls.create = MagicMock(return_value=task)

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=FakeSandbox,
        task_cls=task_cls,
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value={})),
        search_engine=AsyncMock(),
    )

    with (
        patch("app.core.config.get_settings", return_value=settings),
        patch("app.core.config.get_feature_flags", return_value=_SAFE_FEATURE_FLAGS),
        patch(
            "app.core.sandbox_pool.get_sandbox_pool",
            new=AsyncMock(side_effect=AssertionError("sandbox pool should not be used in static mode")),
        ),
    ):
        result = await service._create_task(session)

    assert result is task
    created_sandbox.get_browser.assert_awaited_once()
    assert session.sandbox_id == "sandbox-static"
