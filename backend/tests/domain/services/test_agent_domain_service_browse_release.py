"""Tests for AgentDomainService browse_url cleanup behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import DoneEvent
from app.domain.services.agent_domain_service import AgentDomainService


@pytest.mark.asyncio
async def test_browse_url_releases_pooled_browser():
    mock_browser = MagicMock()
    mock_sandbox = AsyncMock()
    mock_sandbox.get_browser = AsyncMock(return_value=mock_browser)
    mock_sandbox.release_pooled_browser = AsyncMock()

    class FakeSandbox:
        @classmethod
        async def get(cls, _sandbox_id):
            return mock_sandbox

    session = MagicMock()
    session.sandbox_id = "sandbox-id"

    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.add_event = AsyncMock()

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=FakeSandbox,
        task_cls=MagicMock(),
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value={})),
        search_engine=AsyncMock(),
    )

    class FakeFastPathRouter:
        def __init__(self, browser, search_engine):
            self.browser = browser

        async def execute_fast_browse(self, url):
            yield DoneEvent()

    with patch("app.domain.services.flows.fast_path.FastPathRouter", FakeFastPathRouter):
        events = [event async for event in service.browse_url("session-id", "http://example.com")]

    assert events
    mock_sandbox.release_pooled_browser.assert_awaited_once_with(
        mock_browser, had_error=False
    )
