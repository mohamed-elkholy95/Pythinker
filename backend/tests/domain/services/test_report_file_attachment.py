"""Tests for auto-saving report events as files."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import ReportEvent
from app.domain.models.session import AgentMode
from app.domain.services.agent_task_runner import AgentTaskRunner


@pytest.fixture
def mock_sandbox() -> AsyncMock:
    sandbox = AsyncMock()
    sandbox.cdp_url = "http://localhost:9222"
    sandbox.ensure_sandbox = AsyncMock()
    sandbox.destroy = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=MagicMock(success=True))
    return sandbox


@pytest.fixture
def runner(mock_sandbox) -> AgentTaskRunner:
    with patch("app.domain.services.agent_task_runner.PlanActFlow"):
        return AgentTaskRunner(
            session_id="test-session",
            agent_id="test-agent",
            user_id="test-user",
            llm=MagicMock(),
            sandbox=mock_sandbox,
            browser=AsyncMock(),
            agent_repository=AsyncMock(),
            session_repository=AsyncMock(),
            json_parser=MagicMock(),
            file_storage=AsyncMock(),
            mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value={})),
            search_engine=AsyncMock(),
            mode=AgentMode.AGENT,
        )


class TestReportFileAttachment:
    @pytest.mark.asyncio
    async def test_report_event_is_written_and_attached(self, runner, mock_sandbox):
        event = ReportEvent(
            id="report-1",
            title="Test Report",
            content="# Hello\n\nReport body.",
            attachments=None,
        )

        await runner._ensure_report_file(event)

        mock_sandbox.file_write.assert_called_once()
        assert event.attachments is not None
        assert len(event.attachments) == 1
        assert event.attachments[0].file_path == "/home/ubuntu/report-report-1.md"
