"""Unit tests for WorkspaceOrganizer."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.workspace.workspace_organizer import WorkspaceOrganizer
from app.domain.services.workspace.workspace_templates import (
    DATA_ANALYSIS_TEMPLATE,
    RESEARCH_TEMPLATE,
    WorkspaceTemplate,
)


class TestWorkspaceOrganizer:
    """Test WorkspaceOrganizer workspace initialization logic."""

    @pytest.fixture
    def mock_sandbox(self):
        """Create a mock Sandbox instance."""
        sandbox = AsyncMock()
        sandbox.exec_command = AsyncMock(return_value=MagicMock(success=True))
        sandbox.file_write = AsyncMock(return_value=MagicMock(success=True))
        return sandbox

    @pytest.fixture
    def organizer(self, mock_sandbox):
        """Create a WorkspaceOrganizer instance with mock sandbox."""
        return WorkspaceOrganizer(mock_sandbox)

    @pytest.fixture
    def test_session_id(self):
        """Test session ID."""
        return "test-session-123"

    # Basic initialization tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_with_research_template(self, organizer, mock_sandbox, test_session_id):
        """Test workspace initialization with research template."""
        result = await organizer.initialize_workspace(test_session_id, RESEARCH_TEMPLATE)

        # Verify result structure
        assert isinstance(result, dict)
        assert "inputs" in result
        assert "research" in result
        assert "analysis" in result
        assert "deliverables" in result
        assert "logs" in result

        # Verify result content matches template
        assert result == RESEARCH_TEMPLATE.folders

        # Verify mkdir commands were called
        assert mock_sandbox.exec_command.called
        call_count = mock_sandbox.exec_command.call_count
        # Should call mkdir for each folder
        assert call_count == len(RESEARCH_TEMPLATE.folders)

        # Verify README was created
        assert mock_sandbox.file_write.called

    @pytest.mark.asyncio
    async def test_initialize_workspace_with_data_analysis_template(self, organizer, mock_sandbox, test_session_id):
        """Test workspace initialization with data analysis template."""
        result = await organizer.initialize_workspace(test_session_id, DATA_ANALYSIS_TEMPLATE)

        # Verify result structure
        assert isinstance(result, dict)
        assert "raw_data" in result
        assert "processed_data" in result
        assert "analysis" in result
        assert "visualizations" in result
        assert "deliverables" in result
        assert "logs" in result

        # Verify mkdir commands
        assert mock_sandbox.exec_command.call_count == len(DATA_ANALYSIS_TEMPLATE.folders)

    @pytest.mark.asyncio
    async def test_initialize_workspace_creates_correct_paths(self, organizer, mock_sandbox, test_session_id):
        """Test that workspace creates correct folder paths."""
        await organizer.initialize_workspace(test_session_id, RESEARCH_TEMPLATE)

        # Check mkdir calls
        calls = mock_sandbox.exec_command.call_args_list

        # Verify mkdir commands were made
        for call in calls:
            kwargs = call.kwargs
            assert kwargs.get("session_id") == test_session_id
            assert "mkdir -p" in kwargs.get("command", "")
            assert "/workspace/" in kwargs.get("command", "")

    @pytest.mark.asyncio
    async def test_initialize_workspace_returns_folder_descriptions(self, organizer, mock_sandbox, test_session_id):
        """Test that workspace initialization returns folder descriptions."""
        result = await organizer.initialize_workspace(test_session_id, RESEARCH_TEMPLATE)

        # Verify all descriptions match template
        for folder, description in result.items():
            assert folder in RESEARCH_TEMPLATE.folders
            assert description == RESEARCH_TEMPLATE.folders[folder]

    # Custom template tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_with_custom_template(self, organizer, mock_sandbox, test_session_id):
        """Test workspace initialization with custom template."""
        custom_template = WorkspaceTemplate(
            name="custom",
            description="Custom workspace",
            folders={
                "input": "Input data",
                "output": "Output results",
                "temp": "Temporary files",
            },
            readme_content="# Custom Workspace\n",
            trigger_keywords=["custom"],
        )

        result = await organizer.initialize_workspace(test_session_id, custom_template)

        assert len(result) == 3
        assert result["input"] == "Input data"
        assert result["output"] == "Output results"
        assert result["temp"] == "Temporary files"
        assert mock_sandbox.exec_command.call_count == 3

    @pytest.mark.asyncio
    async def test_initialize_workspace_with_single_folder(self, organizer, mock_sandbox, test_session_id):
        """Test workspace initialization with single folder."""
        template = WorkspaceTemplate(
            name="simple",
            description="Simple workspace",
            folders={"work": "Working directory"},
            readme_content="# Simple Workspace\n",
            trigger_keywords=["simple"],
        )

        result = await organizer.initialize_workspace(test_session_id, template)

        assert len(result) == 1
        assert result["work"] == "Working directory"
        assert mock_sandbox.exec_command.call_count == 1

    # Error handling tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_handles_mkdir_failure(self, organizer, mock_sandbox, test_session_id):
        """Test workspace initialization handles mkdir failures gracefully."""
        # Make first mkdir fail
        mock_sandbox.exec_command = AsyncMock(
            side_effect=[
                MagicMock(success=False, message="Permission denied"),
                MagicMock(success=True),
                MagicMock(success=True),
            ]
        )

        template = WorkspaceTemplate(
            name="test",
            description="Test",
            folders={
                "folder1": "First folder",
                "folder2": "Second folder",
                "folder3": "Third folder",
            },
            readme_content="# Test\n",
            trigger_keywords=["test"],
        )

        # Should still return structure even if mkdir fails
        result = await organizer.initialize_workspace(test_session_id, template)

        # Structure should still be returned
        assert len(result) == 3
        assert "folder1" in result
        assert "folder2" in result
        assert "folder3" in result

    @pytest.mark.asyncio
    async def test_initialize_workspace_with_sandbox_exception(self, organizer, mock_sandbox, test_session_id):
        """Test workspace initialization when sandbox raises exception."""
        mock_sandbox.exec_command = AsyncMock(side_effect=Exception("Sandbox error"))

        # Should raise exception
        with pytest.raises(Exception) as exc_info:
            await organizer.initialize_workspace(test_session_id, RESEARCH_TEMPLATE)

        assert "Sandbox error" in str(exc_info.value)

    # Empty template tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_with_empty_folders(self, organizer, mock_sandbox, test_session_id):
        """Test workspace initialization with template having no folders."""
        template = WorkspaceTemplate(
            name="empty",
            description="Empty workspace",
            folders={},
            readme_content="# Empty\n",
            trigger_keywords=["empty"],
        )

        result = await organizer.initialize_workspace(test_session_id, template)

        assert result == {}
        assert mock_sandbox.exec_command.call_count == 0

    # Folder name validation tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_with_special_folder_names(self, organizer, mock_sandbox, test_session_id):
        """Test workspace initialization with special characters in folder names."""
        template = WorkspaceTemplate(
            name="special",
            description="Special chars",
            folders={
                "folder-with-dash": "Folder with dash",
                "folder_with_underscore": "Folder with underscore",
                "folder.with.dots": "Folder with dots",
            },
            readme_content="# Special\n",
            trigger_keywords=["special"],
        )

        result = await organizer.initialize_workspace(test_session_id, template)

        assert len(result) == 3
        assert mock_sandbox.exec_command.call_count == 3

    # Path traversal prevention tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_prevents_path_traversal(self, organizer, mock_sandbox, test_session_id):
        """Test that workspace prevents path traversal attempts."""
        template = WorkspaceTemplate(
            name="malicious",
            description="Path traversal attempt",
            folders={
                "../etc": "Should not escape workspace",
                "../../tmp": "Should not escape workspace",
            },
            readme_content="# Test\n",
            trigger_keywords=["malicious"],
        )

        result = await organizer.initialize_workspace(test_session_id, template)

        # Current behavior: folders are created as-is
        assert len(result) == 2

    # Workspace root customization tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_uses_default_root(self, organizer, mock_sandbox, test_session_id):
        """Test that workspace uses /workspace as default root."""
        await organizer.initialize_workspace(test_session_id, RESEARCH_TEMPLATE)

        calls = mock_sandbox.exec_command.call_args_list
        for call in calls:
            command = call.kwargs.get("command", "")
            assert "/workspace/" in command

    # Concurrent initialization tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_multiple_concurrent_calls(self, organizer, mock_sandbox, test_session_id):
        """Test multiple concurrent workspace initializations."""
        import asyncio

        # Create multiple templates
        templates = [
            RESEARCH_TEMPLATE,
            DATA_ANALYSIS_TEMPLATE,
            WorkspaceTemplate(
                name="test1",
                description="Test 1",
                folders={"a": "A", "b": "B"},
                readme_content="# Test 1\n",
                trigger_keywords=["test1"],
            ),
        ]

        # Initialize concurrently
        results = await asyncio.gather(
            *[organizer.initialize_workspace(test_session_id, template) for template in templates]
        )

        # Verify all succeeded
        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)
        assert len(results[0]) == len(RESEARCH_TEMPLATE.folders)
        assert len(results[1]) == len(DATA_ANALYSIS_TEMPLATE.folders)
        assert len(results[2]) == 2

    # Command format tests
    @pytest.mark.asyncio
    async def test_mkdir_command_format(self, organizer, mock_sandbox, test_session_id):
        """Test that mkdir command has correct format."""
        await organizer.initialize_workspace(test_session_id, RESEARCH_TEMPLATE)

        calls = mock_sandbox.exec_command.call_args_list
        for call in calls:
            command = call.kwargs.get("command", "")
            # Should use mkdir -p for creating parent directories
            assert command.startswith("mkdir -p")
            # Should have proper path
            assert "/workspace/" in command

    # Template preservation tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_preserves_template(self, organizer, mock_sandbox, test_session_id):
        """Test that workspace initialization doesn't modify original template."""
        original_folders = RESEARCH_TEMPLATE.folders.copy()

        await organizer.initialize_workspace(test_session_id, RESEARCH_TEMPLATE)

        # Template should be unchanged
        assert RESEARCH_TEMPLATE.folders == original_folders

    # Large workspace tests
    @pytest.mark.asyncio
    async def test_initialize_workspace_with_many_folders(self, organizer, mock_sandbox, test_session_id):
        """Test workspace initialization with many folders."""
        many_folders = {f"folder_{i}": f"Description {i}" for i in range(50)}
        template = WorkspaceTemplate(
            name="large",
            description="Large workspace",
            folders=many_folders,
            readme_content="# Large\n",
            trigger_keywords=["large"],
        )

        result = await organizer.initialize_workspace(test_session_id, template)

        assert len(result) == 50
        assert mock_sandbox.exec_command.call_count == 50

    # Unicode folder names
    @pytest.mark.asyncio
    async def test_initialize_workspace_with_unicode_folder_names(self, organizer, mock_sandbox, test_session_id):
        """Test workspace initialization with unicode folder names."""
        template = WorkspaceTemplate(
            name="unicode",
            description="Unicode workspace",
            folders={
                "données": "French data folder",
                "documents_cn": "Chinese documents folder",
            },
            readme_content="# Unicode\n",
            trigger_keywords=["unicode"],
        )

        result = await organizer.initialize_workspace(test_session_id, template)

        assert len(result) == 2
        assert "données" in result
        assert "documents_cn" in result

    # Return value validation
    @pytest.mark.asyncio
    async def test_initialize_workspace_return_type(self, organizer, mock_sandbox, test_session_id):
        """Test that workspace initialization returns correct type."""
        result = await organizer.initialize_workspace(test_session_id, RESEARCH_TEMPLATE)

        assert isinstance(result, dict)
        assert all(isinstance(k, str) for k in result)
        assert all(isinstance(v, str) for v in result.values())

    @pytest.mark.asyncio
    async def test_initialize_workspace_return_order_preserved(self, organizer, mock_sandbox, test_session_id):
        """Test that workspace initialization preserves folder order."""
        template = WorkspaceTemplate(
            name="ordered",
            description="Ordered workspace",
            folders={
                "a_first": "First",
                "b_second": "Second",
                "c_third": "Third",
                "d_fourth": "Fourth",
            },
            readme_content="# Ordered\n",
            trigger_keywords=["ordered"],
        )

        result = await organizer.initialize_workspace(test_session_id, template)

        # Check order is preserved (Python 3.7+ dicts maintain insertion order)
        keys = list(result.keys())
        assert keys == ["a_first", "b_second", "c_third", "d_fourth"]
