"""Tests for syncing code_executor artifacts into session files."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import ToolEvent, ToolStatus
from app.domain.models.session import AgentMode
from app.domain.models.tool_result import ToolResult
from app.domain.services.agent_task_runner import AgentTaskRunner


@pytest.fixture
def mock_sandbox() -> AsyncMock:
    sandbox = AsyncMock()
    sandbox.cdp_url = "http://localhost:9222"
    sandbox.ensure_sandbox = AsyncMock()
    sandbox.destroy = AsyncMock()
    return sandbox


@pytest.fixture
def runner(mock_sandbox: AsyncMock) -> AgentTaskRunner:
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


class TestCodeExecutorArtifactSync:
    @pytest.mark.asyncio
    async def test_code_save_artifact_syncs_to_storage(self, runner: AgentTaskRunner) -> None:
        runner._sync_file_to_storage = AsyncMock(return_value=None)

        event = ToolEvent(
            tool_call_id="call-1",
            tool_name="code_executor",
            function_name="code_save_artifact",
            function_args={"content": "# Report"},
            status=ToolStatus.CALLED,
            function_result=ToolResult(success=True, data={"path": "/workspace/test-session/report.md"}),
        )

        await runner._handle_tool_event(event)

        runner._sync_file_to_storage.assert_called_once_with("/workspace/test-session/report.md")
