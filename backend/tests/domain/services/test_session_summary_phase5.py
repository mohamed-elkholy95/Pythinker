"""Tests for Phase 5 session summary persistence.

Tests session summary generation and storage as critical memories.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.long_term_memory import MemoryImportance, MemorySource, MemoryType


class TestSessionSummaryPersistence:
    """Test session summary generation and storage."""

    @pytest.mark.asyncio
    async def test_store_session_summary_success(self):
        """Test storing session summary with LLM-generated content."""
        from app.domain.services.memory_service import MemoryService

        # Mock repository and LLM
        repo_mock = MagicMock()
        llm_mock = MagicMock()
        llm_mock.ask = AsyncMock(
            return_value={"content": "• User requested feature X\n• Implemented successfully\n• Tests passing"}
        )

        # Mock store_memory to return a created memory
        memory_entry_mock = MagicMock()
        memory_entry_mock.id = "mem-123"

        service = MemoryService(repository=repo_mock, llm=llm_mock)
        service.store_memory = AsyncMock(return_value=memory_entry_mock)

        conversation = [
            {"role": "user", "content": "Add feature X"},
            {"role": "assistant", "content": "I'll implement feature X"},
            {"role": "user", "content": "Great!"},
        ]

        result = await service.store_session_summary(
            user_id="user-123",
            session_id="session-456",
            conversation=conversation,
            outcome="Feature X implemented successfully",
            success=True,
        )

        assert result == memory_entry_mock

        # Verify store_memory was called with correct params
        service.store_memory.assert_called_once()
        call_kwargs = service.store_memory.call_args.kwargs
        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["session_id"] == "session-456"
        assert call_kwargs["memory_type"] == MemoryType.PROJECT_CONTEXT
        assert call_kwargs["importance"] == MemoryImportance.CRITICAL
        assert call_kwargs["source"] == MemorySource.SYSTEM
        assert "success" in call_kwargs["tags"]
        assert "session_summary" in call_kwargs["tags"]
        assert call_kwargs["metadata"]["success"] is True
        assert call_kwargs["metadata"]["outcome"] == "Feature X implemented successfully"
        assert call_kwargs["generate_embedding"] is True

    @pytest.mark.asyncio
    async def test_session_summary_failure_outcome(self):
        """Test session summary with failure outcome."""
        from app.domain.services.memory_service import MemoryService

        repo_mock = MagicMock()
        llm_mock = MagicMock()
        llm_mock.ask = AsyncMock(return_value={"content": "Summary of failed session"})

        service = MemoryService(repository=repo_mock, llm=llm_mock)
        service.store_memory = AsyncMock(return_value=MagicMock())

        await service.store_session_summary(
            user_id="user-123",
            session_id="session-456",
            conversation=[],
            outcome="Task failed",
            success=False,
        )

        call_kwargs = service.store_memory.call_args.kwargs
        assert "failure" in call_kwargs["tags"]
        assert call_kwargs["metadata"]["success"] is False

    @pytest.mark.asyncio
    async def test_summary_generation_fallback_on_llm_failure(self):
        """Test fallback summary when LLM fails."""
        from app.domain.services.memory_service import MemoryService

        repo_mock = MagicMock()
        llm_mock = MagicMock()
        llm_mock.ask = AsyncMock(side_effect=Exception("LLM error"))

        service = MemoryService(repository=repo_mock, llm=llm_mock)
        service.store_memory = AsyncMock(return_value=MagicMock())

        conversation = [{"role": "user", "content": "Test"}]

        await service.store_session_summary(
            user_id="user-123",
            session_id="session-456",
            conversation=conversation,
            outcome="Test outcome",
            success=True,
        )

        # Verify fallback summary was created
        call_kwargs = service.store_memory.call_args.kwargs
        assert "Test outcome" in call_kwargs["content"]
        assert str(len(conversation)) in call_kwargs["content"]

    @pytest.mark.asyncio
    async def test_summary_generation_without_llm(self):
        """Test summary generation when LLM is not available."""
        from app.domain.services.memory_service import MemoryService

        repo_mock = MagicMock()
        service = MemoryService(repository=repo_mock, llm=None)  # No LLM

        summary = await service._generate_session_summary(
            conversation=[{"role": "user", "content": "Test"}],
            outcome="Test outcome",
        )

        # Should return simple fallback
        assert "Test outcome" in summary
        assert "Messages: 1" in summary

    @pytest.mark.asyncio
    async def test_summary_includes_recent_messages_only(self):
        """Test summary uses last 20 messages to avoid overwhelming LLM."""
        from app.domain.services.memory_service import MemoryService

        repo_mock = MagicMock()
        llm_mock = MagicMock()
        llm_mock.ask = AsyncMock(return_value={"content": "Summary"})

        service = MemoryService(repository=repo_mock, llm=llm_mock)

        # 30 messages
        conversation = [{"role": "user", "content": f"Message {i}"} for i in range(30)]

        await service._generate_session_summary(conversation=conversation, outcome="Outcome")

        # Verify LLM was called
        llm_mock.ask.assert_called_once()
        prompt = llm_mock.ask.call_args.kwargs["messages"][0]["content"]

        # Should only include last 20 messages
        assert "Message 29" in prompt  # Last message
        assert "Message 10" in prompt  # 20th from end
        assert "Message 0" not in prompt  # First message excluded

    @pytest.mark.asyncio
    async def test_summary_content_truncation(self):
        """Test message content is truncated to 200 chars."""
        from app.domain.services.memory_service import MemoryService

        repo_mock = MagicMock()
        llm_mock = MagicMock()
        llm_mock.ask = AsyncMock(return_value={"content": "Summary"})

        service = MemoryService(repository=repo_mock, llm=llm_mock)

        long_message = "x" * 300
        conversation = [{"role": "user", "content": long_message}]

        await service._generate_session_summary(conversation=conversation, outcome="Outcome")

        prompt = llm_mock.ask.call_args.kwargs["messages"][0]["content"]
        # Should be truncated to 200 chars
        assert "x" * 200 in prompt
        assert "x" * 201 not in prompt

    @pytest.mark.asyncio
    async def test_session_id_preview_in_content(self):
        """Test session ID is previewed in summary content."""
        from app.domain.services.memory_service import MemoryService

        repo_mock = MagicMock()
        llm_mock = MagicMock()
        llm_mock.ask = AsyncMock(return_value={"content": "Test summary"})

        service = MemoryService(repository=repo_mock, llm=llm_mock)
        service.store_memory = AsyncMock(return_value=MagicMock())
        session_id = "session-abcd1234"

        await service.store_session_summary(
            user_id="user-123",
            session_id=session_id,
            conversation=[],
            outcome="Test",
            success=True,
        )

        call_kwargs = service.store_memory.call_args.kwargs
        # Session ID should be shortened to first 8 chars
        assert f"Session {session_id[:8]} summary:" in call_kwargs["content"]

    @pytest.mark.asyncio
    async def test_metadata_contains_all_required_fields(self):
        """Test summary metadata includes all required fields."""
        from app.domain.services.memory_service import MemoryService

        repo_mock = MagicMock()
        llm_mock = MagicMock()
        llm_mock.ask = AsyncMock(return_value={"content": "Summary"})

        service = MemoryService(repository=repo_mock, llm=llm_mock)
        service.store_memory = AsyncMock(return_value=MagicMock())

        conversation = [{"role": "user", "content": "Test"}]

        await service.store_session_summary(
            user_id="user-123",
            session_id="session-456",
            conversation=conversation,
            outcome="Test outcome",
            success=True,
        )

        call_kwargs = service.store_memory.call_args.kwargs
        metadata = call_kwargs["metadata"]

        assert "outcome" in metadata
        assert "success" in metadata
        assert "message_count" in metadata
        assert "summary_timestamp" in metadata
        assert metadata["message_count"] == 1
