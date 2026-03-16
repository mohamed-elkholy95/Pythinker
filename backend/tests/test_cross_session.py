"""Tests for cross-session intelligence (Phase 5)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFindSimilarTasks:
    """Test similar task retrieval via MemoryService."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_embedding_error(self):
        """Should return empty list when embedding generation fails."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(side_effect=RuntimeError("API down"))

        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=MagicMock(),
        ):
            result = await MemoryService.find_similar_tasks(service, "user-1", "build website")
        assert result == []

    @pytest.mark.asyncio
    async def test_generates_embedding_and_queries(self):
        """Should generate embedding then query task artifact repository."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_task_repo = MagicMock()
        mock_task_repo.find_similar_tasks = AsyncMock(
            return_value=[
                {
                    "artifact_id": "a1",
                    "relevance_score": 0.9,
                    "success": True,
                    "content_summary": "Built React app",
                    "artifact_type": "task_outcome",
                    "session_id": "sess-1",
                },
            ]
        )

        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=mock_task_repo,
        ):
            result = await MemoryService.find_similar_tasks(service, "user-1", "build website")

        assert len(result) == 1
        assert result[0]["success"] is True
        assert result[0]["content_summary"] == "Built React app"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_repo(self):
        """Should return empty list when no task artifact repo is configured."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)

        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=None,
        ):
            result = await MemoryService.find_similar_tasks(service, "user-1", "build website")

        assert result == []

    @pytest.mark.asyncio
    async def test_passes_correct_artifact_types(self):
        """Should search for task_outcome and procedure artifact types."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_task_repo = MagicMock()
        mock_task_repo.find_similar_tasks = AsyncMock(return_value=[])

        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=mock_task_repo,
        ):
            await MemoryService.find_similar_tasks(service, "user-1", "build website")

        call_kwargs = mock_task_repo.find_similar_tasks.call_args.kwargs
        assert "task_outcome" in call_kwargs["artifact_types"]
        assert "procedure" in call_kwargs["artifact_types"]
        assert call_kwargs["user_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self):
        """Should pass limit to the task repository query."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_task_repo = MagicMock()
        mock_task_repo.find_similar_tasks = AsyncMock(return_value=[])

        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=mock_task_repo,
        ):
            await MemoryService.find_similar_tasks(service, "user-1", "build website", limit=3)

        call_kwargs = mock_task_repo.find_similar_tasks.call_args.kwargs
        assert call_kwargs["limit"] == 3

    @pytest.mark.asyncio
    async def test_returns_empty_on_repo_error(self):
        """Should return empty list when repository query fails."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_task_repo = MagicMock()
        mock_task_repo.find_similar_tasks = AsyncMock(side_effect=RuntimeError("Qdrant down"))

        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=mock_task_repo,
        ):
            result = await MemoryService.find_similar_tasks(service, "user-1", "build website")

        assert result == []


class TestStoreTaskArtifact:
    """Test task artifact storage via MemoryService."""

    @pytest.mark.asyncio
    async def test_stores_artifact_with_embedding(self):
        """Should generate embedding and store artifact."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_task_repo = MagicMock()
        mock_task_repo.store_task_artifact = AsyncMock()

        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=mock_task_repo,
        ):
            await MemoryService.store_task_artifact(service, "user-1", "session-1", "build website", "Done", True)

        mock_task_repo.store_task_artifact.assert_called_once()
        call_kwargs = mock_task_repo.store_task_artifact.call_args.kwargs
        assert call_kwargs["user_id"] == "user-1"
        assert call_kwargs["session_id"] == "session-1"
        assert call_kwargs["success"] is True
        assert call_kwargs["artifact_type"] == "task_outcome"
        assert "build website" in call_kwargs["content_summary"]
        assert "Done" in call_kwargs["content_summary"]

    @pytest.mark.asyncio
    async def test_skips_when_no_repo(self):
        """Should silently skip when no task artifact repo is configured."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)

        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=None,
        ):
            # Should not raise
            await MemoryService.store_task_artifact(service, "user-1", "session-1", "task", "result", True)

    @pytest.mark.asyncio
    async def test_stores_with_default_agent_role(self):
        """Should use 'executor' as default agent_role."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_task_repo = MagicMock()
        mock_task_repo.store_task_artifact = AsyncMock()

        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=mock_task_repo,
        ):
            await MemoryService.store_task_artifact(service, "user-1", "session-1", "task", "result", False)

        call_kwargs = mock_task_repo.store_task_artifact.call_args.kwargs
        assert call_kwargs["agent_role"] == "executor"

    @pytest.mark.asyncio
    async def test_stores_with_custom_agent_role(self):
        """Should pass custom agent_role when specified."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_task_repo = MagicMock()
        mock_task_repo.store_task_artifact = AsyncMock()

        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=mock_task_repo,
        ):
            await MemoryService.store_task_artifact(
                service, "user-1", "session-1", "task", "result", True, agent_role="planner"
            )

        call_kwargs = mock_task_repo.store_task_artifact.call_args.kwargs
        assert call_kwargs["agent_role"] == "planner"

    @pytest.mark.asyncio
    async def test_handles_embedding_errors_gracefully(self):
        """Should not raise when embedding generation fails."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(side_effect=RuntimeError("fail"))

        mock_task_repo = MagicMock()
        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=mock_task_repo,
        ):
            # Should not raise
            await MemoryService.store_task_artifact(service, "user-1", "session-1", "task", "result", False)

    @pytest.mark.asyncio
    async def test_generates_uuid_artifact_id(self):
        """Should generate a UUID for the artifact ID."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_task_repo = MagicMock()
        mock_task_repo.store_task_artifact = AsyncMock()

        with patch(
            "app.domain.repositories.vector_repos.get_task_artifact_repository",
            return_value=mock_task_repo,
        ):
            await MemoryService.store_task_artifact(service, "user-1", "session-1", "task", "result", True)

        call_kwargs = mock_task_repo.store_task_artifact.call_args.kwargs
        artifact_id = call_kwargs["artifact_id"]
        # Should be a valid UUID string (36 chars with hyphens)
        assert len(artifact_id) == 36
        assert artifact_id.count("-") == 4


class TestGetErrorContext:
    """Test error context retrieval via MemoryService."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_results(self):
        """Should return empty string when no similar failures found."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_tool_repo = MagicMock()
        mock_tool_repo.find_similar_tool_executions = AsyncMock(return_value=[])

        with patch(
            "app.domain.repositories.vector_repos.get_tool_log_repository",
            return_value=mock_tool_repo,
        ):
            result = await MemoryService.get_error_context(service, "user-1", "shell_exec", "npm install")

        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_repo(self):
        """Should return empty string when no tool log repo is configured."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)

        with patch(
            "app.domain.repositories.vector_repos.get_tool_log_repository",
            return_value=None,
        ):
            result = await MemoryService.get_error_context(service, "user-1", "shell_exec", "npm install")

        assert result == ""

    @pytest.mark.asyncio
    async def test_formats_error_context(self):
        """Should format error context from past failures."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_tool_repo = MagicMock()
        mock_tool_repo.find_similar_tool_executions = AsyncMock(
            return_value=[
                {
                    "input_summary": "npm install --save",
                    "error_type": "EACCES",
                    "outcome": "failure",
                    "log_id": "log-1",
                    "relevance_score": 0.8,
                    "tool_name": "shell_exec",
                },
            ]
        )

        with patch(
            "app.domain.repositories.vector_repos.get_tool_log_repository",
            return_value=mock_tool_repo,
        ):
            result = await MemoryService.get_error_context(service, "user-1", "shell_exec", "npm install")

        assert "EACCES" in result
        assert "failures" in result.lower()

    @pytest.mark.asyncio
    async def test_queries_with_correct_tool_name_and_outcome(self):
        """Should filter by tool_name and failure outcome."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_tool_repo = MagicMock()
        mock_tool_repo.find_similar_tool_executions = AsyncMock(return_value=[])

        with patch(
            "app.domain.repositories.vector_repos.get_tool_log_repository",
            return_value=mock_tool_repo,
        ):
            await MemoryService.get_error_context(service, "user-1", "file_write", "write config.json")

        call_kwargs = mock_tool_repo.find_similar_tool_executions.call_args.kwargs
        assert call_kwargs["user_id"] == "user-1"
        assert call_kwargs["tool_name"] == "file_write"
        assert call_kwargs["outcome"] == "failure"

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self):
        """Should pass limit to tool log query."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_tool_repo = MagicMock()
        mock_tool_repo.find_similar_tool_executions = AsyncMock(return_value=[])

        with patch(
            "app.domain.repositories.vector_repos.get_tool_log_repository",
            return_value=mock_tool_repo,
        ):
            await MemoryService.get_error_context(service, "user-1", "shell_exec", "npm install", limit=5)

        call_kwargs = mock_tool_repo.find_similar_tool_executions.call_args.kwargs
        assert call_kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_returns_empty_on_embedding_error(self):
        """Should return empty string when embedding generation fails."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(side_effect=RuntimeError("API down"))

        mock_tool_repo = MagicMock()
        with patch(
            "app.domain.repositories.vector_repos.get_tool_log_repository",
            return_value=mock_tool_repo,
        ):
            result = await MemoryService.get_error_context(service, "user-1", "shell_exec", "npm install")
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_on_repo_error(self):
        """Should return empty string when repository query fails."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_tool_repo = MagicMock()
        mock_tool_repo.find_similar_tool_executions = AsyncMock(side_effect=RuntimeError("Qdrant down"))

        with patch(
            "app.domain.repositories.vector_repos.get_tool_log_repository",
            return_value=mock_tool_repo,
        ):
            result = await MemoryService.get_error_context(service, "user-1", "shell_exec", "npm install")

        assert result == ""

    @pytest.mark.asyncio
    async def test_formats_multiple_errors(self):
        """Should format multiple past failures into context."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_tool_repo = MagicMock()
        mock_tool_repo.find_similar_tool_executions = AsyncMock(
            return_value=[
                {
                    "input_summary": "npm install --save react",
                    "error_type": "EACCES",
                    "outcome": "failure",
                },
                {
                    "input_summary": "npm install --global typescript",
                    "error_type": "ENOENT",
                    "outcome": "failure",
                },
            ]
        )

        with patch(
            "app.domain.repositories.vector_repos.get_tool_log_repository",
            return_value=mock_tool_repo,
        ):
            result = await MemoryService.get_error_context(service, "user-1", "shell_exec", "npm install")

        assert "EACCES" in result
        assert "ENOENT" in result

    @pytest.mark.asyncio
    async def test_generates_embedding_from_tool_context(self):
        """Should embed the combination of tool_name and context."""
        from app.domain.services.memory_service import MemoryService

        service = MagicMock(spec=MemoryService)
        service._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_tool_repo = MagicMock()
        mock_tool_repo.find_similar_tool_executions = AsyncMock(return_value=[])

        with patch(
            "app.domain.repositories.vector_repos.get_tool_log_repository",
            return_value=mock_tool_repo,
        ):
            await MemoryService.get_error_context(service, "user-1", "shell_exec", "npm install")

        # Should embed "shell_exec: npm install"
        call_args = service._generate_embedding.call_args[0][0]
        assert "shell_exec" in call_args
        assert "npm install" in call_args
