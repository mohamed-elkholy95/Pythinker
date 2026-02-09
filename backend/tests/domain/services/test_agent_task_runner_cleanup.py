"""Tests for AgentTaskRunner cleanup behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.session import AgentMode
from app.domain.services.agent_task_runner import AgentTaskRunner


@pytest.fixture
def mock_sandbox() -> AsyncMock:
    sandbox = AsyncMock()
    sandbox.destroy = AsyncMock()
    sandbox.release_pooled_browser = AsyncMock()
    return sandbox


@pytest.fixture
def mock_browser() -> MagicMock:
    return MagicMock()


@pytest.fixture
def runner(mock_sandbox, mock_browser) -> AgentTaskRunner:
    with patch("app.domain.services.agent_task_runner.PlanActFlow"):
        return AgentTaskRunner(
            session_id="test-session",
            agent_id="test-agent",
            user_id="test-user",
            llm=MagicMock(),
            sandbox=mock_sandbox,
            browser=mock_browser,
            agent_repository=AsyncMock(),
            session_repository=AsyncMock(),
            json_parser=MagicMock(),
            file_storage=AsyncMock(),
            mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value={})),
            search_engine=AsyncMock(),
            mode=AgentMode.AGENT,
        )


@pytest.mark.asyncio
async def test_destroy_releases_pooled_browser(runner, mock_sandbox, mock_browser):
    await runner.destroy()

    mock_sandbox.release_pooled_browser.assert_awaited_once_with(mock_browser, had_error=False)
