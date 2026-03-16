"""Tests for post-session memory extraction pipeline."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import MessageEvent


class TestSessionMemoryExtraction:
    """Test memory extraction from completed sessions."""

    @pytest.mark.asyncio
    async def test_extract_skips_when_no_memory_service(self):
        """Should silently skip when memory_service is None."""
        from app.domain.services.agent_domain_service import AgentDomainService

        service = MagicMock(spec=AgentDomainService)
        service._memory_service = None
        service._session_repository = MagicMock()

        # Call the actual unbound method with mock self
        await AgentDomainService._extract_session_memories(service, "session-1", "user-1")
        # Should not call session_repository since memory_service is None
        service._session_repository.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_skips_when_no_session_found(self):
        """Should return early when session is not found."""
        from app.domain.services.agent_domain_service import AgentDomainService

        service = MagicMock(spec=AgentDomainService)
        service._memory_service = MagicMock()
        service._session_repository = MagicMock()
        service._session_repository.find_by_id = AsyncMock(return_value=None)

        await AgentDomainService._extract_session_memories(service, "session-1", "user-1")
        service._memory_service.extract_from_conversation.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_skips_when_session_has_no_events(self):
        """Should return early when session has no events."""
        from app.domain.services.agent_domain_service import AgentDomainService

        service = MagicMock(spec=AgentDomainService)
        service._memory_service = MagicMock()

        mock_session = MagicMock()
        mock_session.events = []
        service._session_repository = MagicMock()
        service._session_repository.find_by_id = AsyncMock(return_value=mock_session)

        await AgentDomainService._extract_session_memories(service, "session-1", "user-1")
        service._memory_service.extract_from_conversation.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_builds_conversation_from_message_events(self):
        """Should build conversation from MessageEvent instances."""
        from app.domain.services.agent_domain_service import AgentDomainService

        service = MagicMock(spec=AgentDomainService)
        service._memory_service = MagicMock()
        service._memory_service.extract_from_conversation = AsyncMock(return_value=[])
        service._memory_service.extract_from_task_result = AsyncMock(return_value=[])
        service._memory_service.store_many = AsyncMock()

        mock_session = MagicMock()
        mock_session.events = [
            MessageEvent(message="Build a website", role="user"),
            MessageEvent(message="I'll create a React app", role="assistant"),
        ]
        service._session_repository = MagicMock()
        service._session_repository.find_by_id = AsyncMock(return_value=mock_session)

        await AgentDomainService._extract_session_memories(service, "session-1", "user-1")

        service._memory_service.extract_from_conversation.assert_called_once()
        call_kwargs = service._memory_service.extract_from_conversation.call_args.kwargs
        assert call_kwargs["user_id"] == "user-1"
        assert call_kwargs["session_id"] == "session-1"
        conversation = call_kwargs["conversation"]
        assert len(conversation) == 2
        assert conversation[0] == {"role": "user", "content": "Build a website"}
        assert conversation[1] == {"role": "assistant", "content": "I'll create a React app"}

    @pytest.mark.asyncio
    async def test_extract_stores_extracted_memories(self):
        """Should store extracted memories via store_many."""
        from app.domain.services.agent_domain_service import AgentDomainService

        service = MagicMock(spec=AgentDomainService)
        service._memory_service = MagicMock()

        mock_extracted = [MagicMock(), MagicMock()]
        service._memory_service.extract_from_conversation = AsyncMock(return_value=mock_extracted)
        service._memory_service.extract_from_task_result = AsyncMock(return_value=[])
        service._memory_service.store_many = AsyncMock()

        mock_session = MagicMock()
        mock_session.events = [
            MessageEvent(message="Build a website", role="user"),
            MessageEvent(message="Done!", role="assistant"),
        ]
        service._session_repository = MagicMock()
        service._session_repository.find_by_id = AsyncMock(return_value=mock_session)

        await AgentDomainService._extract_session_memories(service, "session-1", "user-1")

        service._memory_service.store_many.assert_called_once()
        call_kwargs = service._memory_service.store_many.call_args.kwargs
        assert call_kwargs["user_id"] == "user-1"
        assert call_kwargs["session_id"] == "session-1"

    @pytest.mark.asyncio
    async def test_extract_also_extracts_task_result(self):
        """Should extract task result memories from first user + last assistant messages."""
        from app.domain.services.agent_domain_service import AgentDomainService

        service = MagicMock(spec=AgentDomainService)
        service._memory_service = MagicMock()
        service._memory_service.extract_from_conversation = AsyncMock(return_value=[])

        task_memory = MagicMock()
        service._memory_service.extract_from_task_result = AsyncMock(return_value=[task_memory])
        service._memory_service.store_many = AsyncMock()

        mock_session = MagicMock()
        mock_session.events = [
            MessageEvent(message="Build a website", role="user"),
            MessageEvent(message="Working on it...", role="assistant"),
            MessageEvent(message="Website is deployed!", role="assistant"),
        ]
        service._session_repository = MagicMock()
        service._session_repository.find_by_id = AsyncMock(return_value=mock_session)

        await AgentDomainService._extract_session_memories(service, "session-1", "user-1")

        # Should call extract_from_task_result with first user msg and last assistant msg
        service._memory_service.extract_from_task_result.assert_called_once()
        call_kwargs = service._memory_service.extract_from_task_result.call_args.kwargs
        assert call_kwargs["task_description"] == "Build a website"
        assert call_kwargs["task_result"] == "Website is deployed!"
        assert call_kwargs["success"] is True

    @pytest.mark.asyncio
    async def test_extract_handles_errors_gracefully(self):
        """Should log warning but not raise on errors."""
        from app.domain.services.agent_domain_service import AgentDomainService

        service = MagicMock(spec=AgentDomainService)
        service._memory_service = MagicMock()
        service._session_repository = MagicMock()
        service._session_repository.find_by_id = AsyncMock(side_effect=RuntimeError("DB down"))

        # Should not raise
        await AgentDomainService._extract_session_memories(service, "session-1", "user-1")

    @pytest.mark.asyncio
    async def test_extract_skips_non_message_events(self):
        """Should only process MessageEvent instances, skipping other event types."""
        from app.domain.models.event import DoneEvent
        from app.domain.services.agent_domain_service import AgentDomainService

        service = MagicMock(spec=AgentDomainService)
        service._memory_service = MagicMock()
        service._memory_service.extract_from_conversation = AsyncMock(return_value=[])
        service._memory_service.extract_from_task_result = AsyncMock(return_value=[])
        service._memory_service.store_many = AsyncMock()

        mock_session = MagicMock()
        mock_session.events = [
            MessageEvent(message="Hello", role="user"),
            DoneEvent(),  # Non-message event
            MessageEvent(message="Hi there", role="assistant"),
        ]
        service._session_repository = MagicMock()
        service._session_repository.find_by_id = AsyncMock(return_value=mock_session)

        await AgentDomainService._extract_session_memories(service, "session-1", "user-1")

        call_kwargs = service._memory_service.extract_from_conversation.call_args.kwargs
        conversation = call_kwargs["conversation"]
        # Only MessageEvent instances should be in the conversation
        assert len(conversation) == 2

    @pytest.mark.asyncio
    async def test_extract_no_store_when_nothing_extracted(self):
        """Should not call store_many when no memories are extracted."""
        from app.domain.services.agent_domain_service import AgentDomainService

        service = MagicMock(spec=AgentDomainService)
        service._memory_service = MagicMock()
        service._memory_service.extract_from_conversation = AsyncMock(return_value=[])
        service._memory_service.extract_from_task_result = AsyncMock(return_value=[])
        service._memory_service.store_many = AsyncMock()

        mock_session = MagicMock()
        # Only non-user messages, so no task_description found -> no task_result extraction
        mock_session.events = [
            MessageEvent(message="Status update", role="assistant"),
        ]
        service._session_repository = MagicMock()
        service._session_repository.find_by_id = AsyncMock(return_value=mock_session)

        await AgentDomainService._extract_session_memories(service, "session-1", "user-1")

        # No memories extracted -> store_many should NOT be called
        service._memory_service.store_many.assert_not_called()


class TestToolVectorLogging:
    """Test tool execution logging to vector DB.

    log_tool_to_vectors uses domain-layer getters (get_tool_log_repository,
    get_embedding_provider) which are patched for testing.
    """

    @pytest.mark.asyncio
    async def test_log_tool_skips_without_tool_repo(self):
        """Should skip silently when no tool log repo is configured."""
        from app.domain.services.tool_event_handler import ToolEventHandler

        handler = ToolEventHandler()

        with patch(
            "app.domain.repositories.vector_repos.get_tool_log_repository",
            return_value=None,
        ):
            # Should not raise
            await handler.log_tool_to_vectors(
                tool_name="shell_exec",
                input_summary="ls -la",
                outcome="success",
                error_type=None,
                session_id="session-1",
                user_id="user-1",
            )

    @pytest.mark.asyncio
    async def test_log_tool_skips_without_embedding_provider(self):
        """Should skip silently when no embedding provider is configured."""
        from app.domain.services.tool_event_handler import ToolEventHandler

        handler = ToolEventHandler()

        with (
            patch(
                "app.domain.repositories.vector_repos.get_tool_log_repository",
                return_value=MagicMock(),
            ),
            patch(
                "app.domain.repositories.vector_repos.get_embedding_provider",
                return_value=None,
            ),
        ):
            # Should not raise
            await handler.log_tool_to_vectors(
                tool_name="shell_exec",
                input_summary="ls -la",
                outcome="failure",
                error_type="ConnectionError",
                session_id="session-1",
                user_id="user-1",
            )

    @pytest.mark.asyncio
    async def test_log_tool_calls_repository(self):
        """Should call tool log repo when everything is configured."""
        from app.domain.services.tool_event_handler import ToolEventHandler

        handler = ToolEventHandler()

        mock_embedding_provider = MagicMock()
        mock_embedding_provider.embed = AsyncMock(return_value=[0.1] * 1536)

        mock_tool_repo = MagicMock()
        mock_tool_repo.log_tool_execution = AsyncMock()

        with (
            patch(
                "app.domain.repositories.vector_repos.get_tool_log_repository",
                return_value=mock_tool_repo,
            ),
            patch(
                "app.domain.repositories.vector_repos.get_embedding_provider",
                return_value=mock_embedding_provider,
            ),
        ):
            await handler.log_tool_to_vectors(
                tool_name="shell_exec",
                input_summary="npm install react",
                outcome="success",
                error_type=None,
                session_id="session-1",
                user_id="user-1",
            )

            mock_embedding_provider.embed.assert_called_once()
            mock_tool_repo.log_tool_execution.assert_called_once()

            call_kwargs = mock_tool_repo.log_tool_execution.call_args.kwargs
            assert call_kwargs["user_id"] == "user-1"
            assert call_kwargs["session_id"] == "session-1"
            assert call_kwargs["tool_name"] == "shell_exec"
            assert call_kwargs["outcome"] == "success"
            assert call_kwargs["error_type"] is None

    @pytest.mark.asyncio
    async def test_log_tool_truncates_input_summary(self):
        """Should truncate input_summary to 500 chars."""
        from app.domain.services.tool_event_handler import ToolEventHandler

        handler = ToolEventHandler()

        mock_embedding_provider = MagicMock()
        mock_embedding_provider.embed = AsyncMock(return_value=[0.1] * 1536)

        mock_tool_repo = MagicMock()
        mock_tool_repo.log_tool_execution = AsyncMock()

        long_summary = "x" * 1000

        with (
            patch(
                "app.domain.repositories.vector_repos.get_tool_log_repository",
                return_value=mock_tool_repo,
            ),
            patch(
                "app.domain.repositories.vector_repos.get_embedding_provider",
                return_value=mock_embedding_provider,
            ),
        ):
            await handler.log_tool_to_vectors(
                tool_name="shell_exec",
                input_summary=long_summary,
                outcome="success",
                error_type=None,
                session_id="session-1",
                user_id="user-1",
            )

            call_kwargs = mock_tool_repo.log_tool_execution.call_args.kwargs
            assert len(call_kwargs["input_summary"]) == 500
