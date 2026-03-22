"""Integration coverage for Telegram delivery-scope remediation."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import ReportEvent
from app.domain.models.file import FileInfo
from app.domain.models.session import AgentMode
from app.domain.models.tool_result import ToolResult
from app.domain.services.agent_task_runner import AgentTaskRunner
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.flows.plan_act import PlanActFlow


@pytest.fixture
def mock_sandbox() -> AsyncMock:
    sandbox = AsyncMock()
    sandbox.cdp_url = "http://localhost:9222"
    sandbox.ensure_sandbox = AsyncMock()
    sandbox.destroy = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=MagicMock(success=True, message="ok"))
    sandbox.file_download = AsyncMock(return_value=io.BytesIO(b"# report"))
    return sandbox


@pytest.fixture
def mock_session_repository() -> AsyncMock:
    repo = AsyncMock()
    repo.add_event = AsyncMock()
    repo.update_status = AsyncMock()
    repo.get_file_by_path = AsyncMock(return_value=None)
    repo.add_file = AsyncMock()
    repo.remove_file = AsyncMock()
    return repo


@pytest.fixture
def mock_file_storage() -> AsyncMock:
    storage = AsyncMock()

    async def upload_side_effect(_file_data, file_name, _user_id, **_kwargs):
        return FileInfo(file_id=f"id-{file_name}", filename=file_name)

    storage.upload_file = AsyncMock(side_effect=upload_side_effect)
    return storage


@pytest.fixture
def runner(mock_sandbox, mock_session_repository, mock_file_storage) -> AgentTaskRunner:
    with patch("app.domain.services.agent_task_runner.PlanActFlow"):
        return AgentTaskRunner(
            session_id="test-session",
            agent_id="test-agent",
            user_id="test-user",
            llm=MagicMock(),
            sandbox=mock_sandbox,
            browser=AsyncMock(),
            agent_repository=AsyncMock(),
            session_repository=mock_session_repository,
            json_parser=MagicMock(),
            file_storage=mock_file_storage,
            mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value={})),
            search_engine=AsyncMock(),
            mode=AgentMode.AGENT,
        )


@pytest.fixture
def executor() -> ExecutionAgent:
    agent_repository = AsyncMock()
    agent_repository.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
    agent_repository.save_memory = AsyncMock()
    llm = MagicMock()
    llm.model_name = "gpt-4"
    llm.ask = AsyncMock()
    executor = ExecutionAgent(
        agent_id="integration-executor",
        agent_repository=agent_repository,
        llm=llm,
        tools=[],
        json_parser=MagicMock(),
        feature_flags={"delivery_integrity_gate": True},
    )
    executor.set_delivery_channel("telegram")
    return executor


@pytest.mark.asyncio
async def test_reused_telegram_session_excludes_stale_artifacts_from_delivery(
    runner: AgentTaskRunner,
    executor: ExecutionAgent,
    mock_sandbox: AsyncMock,
    mock_session_repository: AsyncMock,
) -> None:
    """Scope filtering, summary fallback, and final attachments should ignore stale files."""
    stale_file = FileInfo(
        file_id="stale-1",
        filename="report-old.md",
        file_path="/workspace/test-session/runs/run-1/report-old.md",
        metadata={"delivery_scope": "run-1"},
    )
    current_file = FileInfo(
        file_id="current-1",
        filename="report-current.md",
        file_path="/workspace/test-session/runs/run-2/report-current.md",
        metadata={"delivery_scope": "run-2", "is_report": True},
    )
    weak_summary = (
        "# Final Report\n\n"
        "## Findings\n"
        "This polished summary cites evidence [1] but drops the references section.\n\n"
        "## Conclusion\n"
        "Do not deliver this version."
    )
    grounded_pretrim = (
        "# Final Report\n\n"
        "## Findings\n"
        "Grounded finding tied to source [1].\n\n"
        "## References\n"
        "[1] https://example.com/source"
    )

    runner._set_delivery_scope("run-2", "/workspace/test-session/runs/run-2")
    # Two-step sandbox exec: first call checks directory exists, second runs find
    mock_sandbox.exec_command = AsyncMock(
        side_effect=[
            ToolResult(success=True, data={"output": "exists"}),
            ToolResult(
                success=True,
                data={
                    "output": (
                        "/workspace/test-session/runs/run-1/report-old.md\n"
                        "/workspace/test-session/runs/run-2/report-current.md\n"
                    )
                },
            ),
        ]
    )
    mock_session_repository.find_by_id_with_files = AsyncMock(return_value=SimpleNamespace(files=[]))

    swept_files = await runner._sweep_workspace_files()
    assert [file_info.filename for file_info in swept_files] == ["report-current.md"]

    scoped_files = PlanActFlow._filter_files_for_delivery_scope(
        [stale_file, current_file],
        runner._delivery_scope_id,
        runner._delivery_scope_root,
    )
    assert [file_info.filename for file_info in scoped_files] == ["report-current.md"]

    executor._user_request = "Provide a grounded Telegram final report."
    executor._extract_report_from_file_write_memory = MagicMock(return_value=grounded_pretrim)
    executor._needs_verification = MagicMock(return_value=False)
    executor._can_auto_repair_delivery_integrity = MagicMock(return_value=False)
    executor.llm.ask.return_value = {"content": '["Follow-up question?"]'}

    async def weak_summary_stream(*_args, **_kwargs):
        executor.llm.last_stream_metadata = {
            "finish_reason": "stop",
            "truncated": False,
            "provider": "test",
        }
        yield weak_summary

    executor.llm.ask_stream = weak_summary_stream

    events = [event async for event in executor.summarize(all_steps_completed=True)]
    report = next(event for event in events if isinstance(event, ReportEvent))
    assert report.content == grounded_pretrim

    report.attachments = scoped_files
    runner._plan_act_flow = SimpleNamespace(executor=executor)
    await runner._ensure_report_file(report)

    assert report.attachments is not None
    attachment_paths = {attachment.file_path for attachment in report.attachments if attachment.file_path}
    attachment_names = {attachment.filename for attachment in report.attachments}

    assert "report-old.md" not in attachment_names
    assert "report-current.md" in attachment_names
    assert "/workspace/test-session/runs/run-1/report-old.md" not in attachment_paths
    assert f"{runner._delivery_scope_root}/report-{report.id}.md" in attachment_paths
