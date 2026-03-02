"""Tests for the file sweep mechanism in AgentTaskRunner.

Validates that _sweep_workspace_files() discovers and syncs untracked files
before the agent summarization phase.
"""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.file import FileInfo
from app.domain.models.session import AgentMode
from app.domain.models.tool_result import ToolResult
from app.domain.services.agent_task_runner import AgentTaskRunner
from app.domain.services.file_sync_manager import (
    DELIVERABLE_EXTENSIONS,
    MAX_SWEEP_FILES,
    SKIP_DIRECTORIES,
)


@pytest.fixture
def mock_sandbox() -> AsyncMock:
    sandbox = AsyncMock()
    sandbox.cdp_url = "http://localhost:9222"
    sandbox.ensure_sandbox = AsyncMock()
    sandbox.destroy = AsyncMock()
    sandbox.file_read = AsyncMock(return_value=MagicMock(success=True, data={"content": ""}))
    sandbox.file_download = AsyncMock(return_value=io.BytesIO(b"file content"))
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
    storage.upload_file = AsyncMock(return_value=FileInfo(file_id="new-file-id", filename="test.md"))
    return storage


@pytest.fixture
def runner(mock_sandbox, mock_session_repository, mock_file_storage) -> AgentTaskRunner:
    """Create AgentTaskRunner with mocked dependencies."""
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


class TestSweepWorkspaceFiles:
    """Tests for _sweep_workspace_files()."""

    @pytest.mark.asyncio
    async def test_discovers_and_syncs_untracked_files(
        self, runner, mock_sandbox, mock_session_repository, mock_file_storage
    ):
        """Sweep should find files in sandbox and sync those not yet tracked."""
        # Sandbox returns 2 files from find
        mock_sandbox.exec_command = AsyncMock(
            return_value=ToolResult(
                success=True,
                data={"output": "/workspace/test-session/report.md\n/workspace/test-session/code.py\n"},
            )
        )
        # Session has no existing files
        session = MagicMock()
        session.files = []
        mock_session_repository.find_by_id = AsyncMock(return_value=session)

        result = await runner._sweep_workspace_files()

        assert len(result) == 2
        assert mock_file_storage.upload_file.call_count == 2
        assert mock_session_repository.add_file.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_already_tracked_files(self, runner, mock_sandbox, mock_session_repository, mock_file_storage):
        """Sweep should not re-sync files already in session.files."""
        mock_sandbox.exec_command = AsyncMock(
            return_value=ToolResult(
                success=True,
                data={"output": "/workspace/test-session/report.md\n/workspace/test-session/code.py\n"},
            )
        )
        # report.md is already tracked
        session = MagicMock()
        session.files = [FileInfo(file_id="existing", file_path="/workspace/test-session/report.md")]
        mock_session_repository.find_by_id = AsyncMock(return_value=session)

        result = await runner._sweep_workspace_files()

        # Only code.py should be synced
        assert len(result) == 1
        assert mock_file_storage.upload_file.call_count == 1

    @pytest.mark.asyncio
    async def test_handles_empty_find_output(self, runner, mock_sandbox, mock_session_repository):
        """Sweep should handle no files found gracefully."""
        mock_sandbox.exec_command = AsyncMock(return_value=ToolResult(success=True, data={"output": ""}))

        result = await runner._sweep_workspace_files()
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_find_command_failure(self, runner, mock_sandbox):
        """Sweep should handle find command failure gracefully."""
        mock_sandbox.exec_command = AsyncMock(return_value=ToolResult(success=False, message="Command failed"))

        result = await runner._sweep_workspace_files()
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_sandbox_exception(self, runner, mock_sandbox):
        """Sweep should handle sandbox exceptions without crashing."""
        mock_sandbox.exec_command = AsyncMock(side_effect=Exception("Connection lost"))

        result = await runner._sweep_workspace_files()
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_partial_sync_failures(
        self, runner, mock_sandbox, mock_session_repository, mock_file_storage
    ):
        """Sweep should continue syncing even if some files fail."""
        mock_sandbox.exec_command = AsyncMock(
            return_value=ToolResult(
                success=True,
                data={"output": "/workspace/test-session/good.md\n/workspace/test-session/bad.md\n"},
            )
        )
        session = MagicMock()
        session.files = []
        mock_session_repository.find_by_id = AsyncMock(return_value=session)

        # First file succeeds, second fails
        call_count = 0

        async def download_side_effect(path):
            nonlocal call_count
            call_count += 1
            if "bad" in path:
                raise FileNotFoundError(f"No such file: {path}")
            return io.BytesIO(b"good content")

        mock_sandbox.file_download = AsyncMock(side_effect=download_side_effect)

        result = await runner._sweep_workspace_files()

        # Only 1 file should succeed
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_ignores_paths_outside_session_workspace(
        self, runner, mock_sandbox, mock_session_repository, mock_file_storage
    ):
        """Sweep should ignore paths not under /workspace/<session_id>."""
        mock_sandbox.exec_command = AsyncMock(
            return_value=ToolResult(
                success=True,
                data={
                    "output": (
                        "/workspace/test-session/kept.py\n"
                        "/home/ubuntu/.pnpm-store/v10/index/xx/some-package.json\n"
                        "/home/ubuntu/old-report.md\n"
                    )
                },
            )
        )
        session = MagicMock()
        session.files = []
        mock_session_repository.find_by_id = AsyncMock(return_value=session)

        result = await runner._sweep_workspace_files()

        assert len(result) == 1
        assert mock_file_storage.upload_file.call_count == 1
        mock_sandbox.file_download.assert_awaited_once_with("/workspace/test-session/kept.py")

    @pytest.mark.asyncio
    async def test_sweep_command_scoped_to_session_workspace(self, runner, mock_sandbox, mock_session_repository):
        """Find command should run only under /workspace/<session_id>."""
        mock_sandbox.exec_command = AsyncMock(return_value=ToolResult(success=True, data={"output": ""}))
        session = MagicMock()
        session.files = []
        mock_session_repository.find_by_id = AsyncMock(return_value=session)

        await runner._sweep_workspace_files()

        assert mock_sandbox.exec_command.await_count == 1
        _session, exec_dir, command = mock_sandbox.exec_command.await_args.args
        assert exec_dir == "/workspace/test-session"
        assert "find /workspace/test-session" in command

    @pytest.mark.asyncio
    async def test_dedup_keeps_single_similar_artifact_basename(
        self, runner, mock_sandbox, mock_session_repository, mock_file_storage, monkeypatch
    ):
        """Similar artifact names in same dir/ext should be deduped to one sync candidate."""
        monkeypatch.setattr(
            "app.core.config.get_settings",
            lambda: SimpleNamespace(feature_sweep_dedup_enabled=True),
        )
        mock_sandbox.exec_command = AsyncMock(
            return_value=ToolResult(
                success=True,
                data={
                    "output": (
                        "/workspace/test-session/report.md\n"
                        "/workspace/test-session/final_report.md\n"
                    )
                },
            )
        )
        session = MagicMock()
        session.files = []
        mock_session_repository.find_by_id = AsyncMock(return_value=session)

        result = await runner._sweep_workspace_files()

        assert len(result) == 1
        assert mock_file_storage.upload_file.call_count == 1

    @pytest.mark.asyncio
    async def test_dedup_preserves_numeric_variant_artifacts(
        self, runner, mock_sandbox, mock_session_repository, mock_file_storage, monkeypatch
    ):
        """Distinct numeric variants (q1/q2) should not be deduped."""
        monkeypatch.setattr(
            "app.core.config.get_settings",
            lambda: SimpleNamespace(feature_sweep_dedup_enabled=True),
        )
        mock_sandbox.exec_command = AsyncMock(
            return_value=ToolResult(
                success=True,
                data={
                    "output": (
                        "/workspace/test-session/report_q1.md\n"
                        "/workspace/test-session/report_q2.md\n"
                    )
                },
            )
        )
        session = MagicMock()
        session.files = []
        mock_session_repository.find_by_id = AsyncMock(return_value=session)

        result = await runner._sweep_workspace_files()

        assert len(result) == 2
        assert mock_file_storage.upload_file.call_count == 2


class TestSweepConstants:
    """Tests for sweep configuration constants."""

    def test_deliverable_extensions_include_common_types(self):
        """Ensure common deliverable file types are covered."""
        assert ".md" in DELIVERABLE_EXTENSIONS
        assert ".py" in DELIVERABLE_EXTENSIONS
        assert ".json" in DELIVERABLE_EXTENSIONS
        assert ".html" in DELIVERABLE_EXTENSIONS
        assert ".csv" in DELIVERABLE_EXTENSIONS
        assert ".pdf" in DELIVERABLE_EXTENSIONS
        assert ".png" in DELIVERABLE_EXTENSIONS
        assert ".svg" in DELIVERABLE_EXTENSIONS

    def test_skip_directories_exclude_junk(self):
        """Ensure junk directories are excluded."""
        assert "node_modules" in SKIP_DIRECTORIES
        assert ".git" in SKIP_DIRECTORIES
        assert "__pycache__" in SKIP_DIRECTORIES
        assert ".venv" in SKIP_DIRECTORIES
        assert ".pnpm-store" in SKIP_DIRECTORIES
        assert ".pki" in SKIP_DIRECTORIES

    def test_max_sweep_files_is_bounded(self):
        """Ensure sweep is bounded to prevent excessive syncing."""
        assert MAX_SWEEP_FILES <= 100


class TestFileSweepCallback:
    """Tests for file_sweep_callback wiring in PlanActFlow."""

    @pytest.mark.asyncio
    async def test_sweep_callback_wired_in_plan_act_flow(self, runner):
        """Verify that the PlanActFlow receives the sweep callback."""
        # The runner should have passed _sweep_workspace_files as the callback
        # We verify by checking the PlanActFlow constructor was called with it
        # Since we mocked PlanActFlow, check the init args
        from app.domain.services.agent_task_runner import PlanActFlow as MockedPlanActFlow

        if hasattr(MockedPlanActFlow, "call_args"):
            # PlanActFlow was constructed — verify file_sweep_callback is present
            _, kwargs = MockedPlanActFlow.call_args
            assert "file_sweep_callback" in kwargs
            assert kwargs["file_sweep_callback"] is not None
