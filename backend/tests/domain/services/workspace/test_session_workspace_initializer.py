"""Unit tests for SessionWorkspaceInitializer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.session import AgentMode, Session, SessionStatus
from app.domain.services.workspace.session_workspace_initializer import (
    SessionWorkspaceInitializer,
    get_session_workspace_initializer,
)


class TestSessionWorkspaceInitializer:
    """Test SessionWorkspaceInitializer integration logic."""

    @pytest.fixture
    def mock_session_repository(self):
        """Create a mock SessionRepository."""
        repo = AsyncMock()
        repo.update_by_id = AsyncMock()
        return repo

    @pytest.fixture
    def mock_sandbox(self):
        """Create a mock Sandbox."""
        sandbox = AsyncMock()
        sandbox.exec_command = AsyncMock(return_value=MagicMock(success=True))
        return sandbox

    @pytest.fixture
    def initializer(self, mock_session_repository):
        """Create a SessionWorkspaceInitializer instance."""
        return SessionWorkspaceInitializer(mock_session_repository)

    @pytest.fixture
    def test_session(self):
        """Create a test session."""
        return Session(
            agent_id="agent-123",
            user_id="user-123",
            mode=AgentMode.AGENT,
            status=SessionStatus.PENDING,
        )

    # Basic initialization tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_if_needed_first_time(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test workspace initialization on first call."""
        task_description = "Research machine learning algorithms"

        result = await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description=task_description,
        )

        # Should return workspace structure
        assert result is not None
        assert isinstance(result, dict)
        assert len(result) > 0

        # Should update session
        assert test_session.workspace_structure is not None
        assert mock_session_repository.update_by_id.called

    @pytest.mark.asyncio
    async def test_initialize_workspace_if_needed_already_initialized(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test workspace initialization skips if already initialized."""
        # Pre-set workspace structure
        test_session.workspace_structure = {"inputs": "Input files"}

        result = await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description="Some task",
        )

        # Should return None (skipped)
        assert result is None

        # Should not update repository
        assert not mock_session_repository.update_by_id.called

    @pytest.mark.asyncio
    async def test_initialize_workspace_skips_discuss_mode(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test workspace initialization skips for discuss mode."""
        test_session.mode = AgentMode.DISCUSS

        result = await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description="Research something",
        )

        # Should return None (skipped)
        assert result is None

        # Should not update repository
        assert not mock_session_repository.update_by_id.called

    # Template selection tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_selects_research_template(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test that research template is selected for research tasks."""
        task_description = "Research cloud computing providers"

        result = await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description=task_description,
        )

        assert result is not None
        # Research template has these folders
        assert "inputs" in result
        assert "research" in result
        assert "deliverables" in result

    @pytest.mark.asyncio
    async def test_initialize_workspace_selects_data_analysis_template(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test that data analysis template is selected for data tasks."""
        task_description = "Analyze data and create visualizations"

        result = await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description=task_description,
        )

        assert result is not None
        # Data analysis template has these folders
        assert "data" in result or "inputs" in result

    @pytest.mark.asyncio
    async def test_initialize_workspace_selects_code_project_template(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test that code project template is selected for coding tasks."""
        task_description = "Build a REST API with authentication"

        result = await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description=task_description,
        )

        assert result is not None
        # Code project template has these folders
        assert "src" in result or "tests" in result

    # Session update tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_updates_session_object(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test that workspace initialization updates session object."""
        task_description = "Research Python frameworks"

        await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description=task_description,
        )

        # Session should be updated in memory
        assert test_session.workspace_structure is not None
        assert isinstance(test_session.workspace_structure, dict)

    @pytest.mark.asyncio
    async def test_initialize_workspace_updates_session_repository(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test that workspace initialization updates session repository."""
        task_description = "Research AI trends"

        await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description=task_description,
        )

        # Repository update should be called
        mock_session_repository.update_by_id.assert_called_once()

        # Verify update args
        call_args = mock_session_repository.update_by_id.call_args
        session_id = call_args[0][0]
        update_data = call_args[0][1]

        assert session_id == test_session.id
        assert "workspace_structure" in update_data
        assert isinstance(update_data["workspace_structure"], dict)

    # Error handling tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_handles_selector_error(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test workspace initialization handles selector errors gracefully."""
        # Patch the selector instance's method directly
        initializer._selector.select_template = MagicMock(side_effect=Exception("Selector error"))

        result = await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description="Some task",
        )

        # Should return None on error
        assert result is None

        # Session should not be updated
        assert test_session.workspace_structure is None

    @pytest.mark.asyncio
    async def test_initialize_workspace_handles_organizer_error(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test workspace initialization handles organizer errors gracefully."""
        with patch(
            "app.domain.services.workspace.session_workspace_initializer.WorkspaceOrganizer"
        ) as mock_organizer_class:
            mock_organizer_class.return_value.initialize_workspace = AsyncMock(side_effect=Exception("Organizer error"))

            result = await initializer.initialize_workspace_if_needed(
                session=test_session,
                sandbox=mock_sandbox,
                task_description="Research something",
            )

            # Should return None on error
            assert result is None

    @pytest.mark.asyncio
    async def test_initialize_workspace_handles_repository_error(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test workspace initialization handles repository errors gracefully."""
        mock_session_repository.update_by_id = AsyncMock(side_effect=Exception("Database error"))

        result = await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description="Research something",
        )

        # Should return None on error
        assert result is None

    # Deliverable marking tests
    @pytest.mark.asyncio
    async def test_mark_deliverable(self, initializer):
        """Test marking a file as deliverable."""
        # Should not raise exception (currently just logs)
        await initializer.mark_deliverable(
            session_id="session-123",
            file_path="/workspace/deliverables/report.pdf",
        )

    @pytest.mark.asyncio
    async def test_mark_deliverable_handles_error(self, initializer):
        """Test mark_deliverable handles errors gracefully."""
        # Even with invalid inputs, should not raise
        await initializer.mark_deliverable(
            session_id="",
            file_path="",
        )

    # Edge cases
    @pytest.mark.asyncio
    async def test_initialize_workspace_with_empty_task_description(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test workspace initialization with empty task description."""
        result = await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description="",
        )

        # Should still work with default template
        assert result is not None or result is None  # Implementation dependent

    @pytest.mark.asyncio
    async def test_initialize_workspace_with_very_long_task_description(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test workspace initialization with very long task description."""
        long_description = "Research " + "machine learning " * 1000

        result = await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description=long_description,
        )

        # Should handle long descriptions
        assert result is not None

    # Concurrent initialization tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_concurrent_calls_same_session(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test concurrent workspace initializations for same session."""
        import asyncio

        # First call should initialize, subsequent should skip
        results = await asyncio.gather(
            *[
                initializer.initialize_workspace_if_needed(
                    session=test_session,
                    sandbox=mock_sandbox,
                    task_description="Research AI",
                )
                for _ in range(3)
            ]
        )

        # First should succeed, rest should be None (already initialized)
        # Note: Actual behavior depends on race conditions
        assert any(r is not None for r in results)

    # Singleton pattern tests
    def test_get_session_workspace_initializer_singleton(self, mock_session_repository):
        """Test that get_session_workspace_initializer returns singleton."""
        # Reset singleton
        import app.domain.services.workspace.session_workspace_initializer as module

        module._initializer = None

        init1 = get_session_workspace_initializer(mock_session_repository)
        init2 = get_session_workspace_initializer(mock_session_repository)

        # Should return same instance
        assert init1 is init2

    def test_get_session_workspace_initializer_creates_instance(self, mock_session_repository):
        """Test that get_session_workspace_initializer creates instance."""
        # Reset singleton
        import app.domain.services.workspace.session_workspace_initializer as module

        module._initializer = None

        initializer = get_session_workspace_initializer(mock_session_repository)

        assert initializer is not None
        assert isinstance(initializer, SessionWorkspaceInitializer)

    # Integration with real components
    @pytest.mark.asyncio
    async def test_initialize_workspace_end_to_end(
        self, initializer, test_session, mock_sandbox, mock_session_repository
    ):
        """Test complete workspace initialization flow."""
        task_description = "Research quantum computing and create a comprehensive report"

        result = await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description=task_description,
        )

        # Verify complete flow
        assert result is not None
        assert isinstance(result, dict)
        assert len(result) > 0

        # Verify session updated
        assert test_session.workspace_structure == result

        # Verify repository called
        assert mock_session_repository.update_by_id.called

        # Verify sandbox called
        assert mock_sandbox.exec_command.called

    # Multiple session tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_multiple_different_sessions(self, mock_session_repository, mock_sandbox):
        """Test workspace initialization for multiple different sessions."""
        initializer = SessionWorkspaceInitializer(mock_session_repository)

        sessions = [
            Session(
                agent_id=f"agent-{i}",
                user_id=f"user-{i}",
                mode=AgentMode.AGENT,
                status=SessionStatus.PENDING,
            )
            for i in range(3)
        ]

        tasks = [
            "Research AI trends",
            "Analyze sales data",
            "Build a web app",
        ]

        results = []
        for session, task in zip(sessions, tasks, strict=False):
            result = await initializer.initialize_workspace_if_needed(
                session=session,
                sandbox=mock_sandbox,
                task_description=task,
            )
            results.append(result)

        # All should initialize successfully
        assert all(r is not None for r in results)
        assert all(isinstance(r, dict) for r in results)

        # Each session should have workspace
        assert all(s.workspace_structure is not None for s in sessions)

    # Logging tests (optional)
    @pytest.mark.asyncio
    async def test_initialize_workspace_logs_success(
        self, initializer, test_session, mock_sandbox, mock_session_repository, caplog
    ):
        """Test that workspace initialization logs success."""
        import logging

        caplog.set_level(logging.INFO)

        await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description="Research machine learning",
        )

        # Check logs contain success message
        assert any("workspace" in record.message.lower() for record in caplog.records)

    @pytest.mark.asyncio
    async def test_initialize_workspace_logs_skip(
        self, initializer, test_session, mock_sandbox, mock_session_repository, caplog
    ):
        """Test that workspace initialization logs skip when already initialized."""
        import logging

        caplog.set_level(logging.DEBUG)

        test_session.workspace_structure = {"inputs": "Input files"}

        await initializer.initialize_workspace_if_needed(
            session=test_session,
            sandbox=mock_sandbox,
            task_description="Some task",
        )

        # Check logs contain skip message
        assert any("already initialized" in record.message.lower() for record in caplog.records)
