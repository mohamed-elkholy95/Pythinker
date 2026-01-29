"""
Tests for the ContextEngineeringService (Phase 4: Dynamic Context Engineering).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.memory import Memory, MemoryConfig
from app.domain.services.memory_service import (
    ContextChunk,
    ContextEngineeringService,
    ContextServiceConfig,
)


class TestContextChunk:
    """Tests for ContextChunk dataclass"""

    def test_initialization(self):
        """Test chunk initialization"""
        chunk = ContextChunk(
            id="ctx_1",
            summary="Task completed step 1",
            message_range=(0, 10),
            token_estimate=100,
            relevance_tags=["search", "file"]
        )

        assert chunk.id == "ctx_1"
        assert chunk.message_range == (0, 10)
        assert "search" in chunk.relevance_tags

    def test_created_at_default(self):
        """Test created_at default value"""
        chunk = ContextChunk(
            id="ctx_1",
            summary="Test",
            message_range=(0, 5)
        )

        assert chunk.created_at is not None


class TestContextServiceConfig:
    """Tests for ContextServiceConfig"""

    def test_default_config(self):
        """Test default configuration values"""
        config = ContextServiceConfig()

        assert config.enabled is True
        assert config.auto_summarize_threshold == 20
        assert config.summarize_after_steps == 3
        assert config.max_injected_tokens == 2000
        assert config.max_chunks_to_retrieve == 3

    def test_custom_config(self):
        """Test custom configuration"""
        config = ContextServiceConfig(
            enabled=False,
            auto_summarize_threshold=10,
            max_injected_tokens=1000
        )

        assert config.enabled is False
        assert config.auto_summarize_threshold == 10
        assert config.max_injected_tokens == 1000


class TestContextEngineeringService:
    """Tests for ContextEngineeringService"""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM"""
        llm = MagicMock()
        llm.ask = AsyncMock(return_value={
            "content": "Summarized context: completed search and file operations"
        })
        return llm

    @pytest.fixture
    def test_memory(self):
        """Create test memory with messages"""
        memory = Memory()
        memory.add_messages([
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Search for Python tutorials"},
            {"role": "assistant", "content": "I'll search for that"},
            {"role": "tool", "function_name": "search", "content": "Results..."},
            {"role": "assistant", "content": "Found several tutorials"},
            {"role": "user", "content": "Read the first one"},
            {"role": "assistant", "content": "Reading the tutorial"},
            {"role": "tool", "function_name": "file_read", "content": "File content..."},
            {"role": "assistant", "content": "Here is the content"},
            {"role": "user", "content": "Summarize it"},
            {"role": "assistant", "content": "Summary of the tutorial"},
        ])
        return memory

    def test_initialization(self, mock_llm):
        """Test service initialization"""
        service = ContextEngineeringService(llm=mock_llm)

        assert service._llm == mock_llm
        assert service.config.enabled is True
        assert len(service._context_chunks) == 0

    def test_should_summarize_disabled(self, mock_llm, test_memory):
        """Test summarization disabled"""
        config = ContextServiceConfig(enabled=False)
        service = ContextEngineeringService(llm=mock_llm, config=config)

        result = service.should_summarize(test_memory)
        assert result is False

    def test_should_summarize_message_threshold(self, mock_llm, test_memory):
        """Test summarization triggered by message threshold"""
        config = ContextServiceConfig(
            enabled=True,
            auto_summarize_threshold=5
        )
        service = ContextEngineeringService(llm=mock_llm, config=config)
        service._messages_since_summary = 10

        result = service.should_summarize(test_memory)
        assert result is True

    def test_should_summarize_step_threshold(self, mock_llm, test_memory):
        """Test summarization triggered by step threshold"""
        config = ContextServiceConfig(
            enabled=True,
            auto_summarize_threshold=100,  # High to not trigger
            summarize_after_steps=2
        )
        service = ContextEngineeringService(llm=mock_llm, config=config)
        service._steps_since_summary = 3

        result = service.should_summarize(test_memory)
        assert result is True

    def test_should_summarize_token_pressure(self, mock_llm):
        """Test summarization triggered by token pressure"""
        # Create memory with high token count
        memory = Memory()
        memory.config = MemoryConfig(auto_compact_token_threshold=1000)
        # Add many messages to increase token count
        for i in range(50):
            memory.add_message({
                "role": "assistant",
                "content": "This is a longer message with more content " * 10
            })

        config = ContextServiceConfig(
            enabled=True,
            auto_summarize_threshold=100,
            summarize_after_steps=100
        )
        service = ContextEngineeringService(llm=mock_llm, config=config)

        result = service.should_summarize(memory)
        assert result is True

    @pytest.mark.asyncio
    async def test_summarize_and_store(self, mock_llm, test_memory):
        """Test summarizing and storing context"""
        service = ContextEngineeringService(llm=mock_llm)

        chunk = await service.summarize_and_store(test_memory, preserve_recent=3)

        assert chunk is not None
        assert chunk.id.startswith("ctx_")
        assert chunk.summary is not None
        assert len(service._context_chunks) == 1

    @pytest.mark.asyncio
    async def test_summarize_and_store_preserves_recent(self, mock_llm, test_memory):
        """Test that summarization preserves recent messages"""
        service = ContextEngineeringService(llm=mock_llm)

        # Preserve last 5 messages
        chunk = await service.summarize_and_store(test_memory, preserve_recent=5)

        # Should have summarized messages before the last 5
        assert chunk is not None
        # Message range should not include last 5
        assert chunk.message_range[1] <= len(test_memory.messages) - 5

    @pytest.mark.asyncio
    async def test_summarize_and_store_too_few_messages(self, mock_llm):
        """Test summarization with too few messages"""
        memory = Memory()
        memory.add_messages([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ])

        service = ContextEngineeringService(llm=mock_llm)

        chunk = await service.summarize_and_store(memory, preserve_recent=3)

        # Should return None - not enough messages to summarize
        assert chunk is None

    @pytest.mark.asyncio
    async def test_summarize_and_store_resets_counters(self, mock_llm, test_memory):
        """Test that summarization resets tracking counters"""
        service = ContextEngineeringService(llm=mock_llm)
        service._messages_since_summary = 20
        service._steps_since_summary = 5

        await service.summarize_and_store(test_memory, preserve_recent=3)

        assert service._messages_since_summary == 0
        assert service._steps_since_summary == 0

    @pytest.mark.asyncio
    async def test_get_relevant_context_empty(self, mock_llm):
        """Test getting context when no chunks exist"""
        service = ContextEngineeringService(llm=mock_llm)

        result = await service.get_relevant_context("Search for data")

        assert result == ""

    @pytest.mark.asyncio
    async def test_get_relevant_context_recent_fallback(self, mock_llm):
        """Test getting context with recent fallback"""
        config = ContextServiceConfig(
            use_semantic_retrieval=False,
            fallback_to_recent=True,
            max_chunks_to_retrieve=2
        )
        service = ContextEngineeringService(llm=mock_llm, config=config)

        # Add some context chunks
        service._context_chunks = [
            ContextChunk(id="ctx_1", summary="First chunk", message_range=(0, 5), token_estimate=50),
            ContextChunk(id="ctx_2", summary="Second chunk", message_range=(5, 10), token_estimate=50),
            ContextChunk(id="ctx_3", summary="Third chunk", message_range=(10, 15), token_estimate=50),
        ]

        result = await service.get_relevant_context("Next step")

        # Should get recent chunks
        assert "Second chunk" in result or "Third chunk" in result

    @pytest.mark.asyncio
    async def test_get_relevant_context_respects_budget(self, mock_llm):
        """Test that context retrieval respects token budget"""
        config = ContextServiceConfig(
            use_semantic_retrieval=False,
            max_injected_tokens=100  # Small budget
        )
        service = ContextEngineeringService(llm=mock_llm, config=config)

        # Add chunks that exceed budget
        service._context_chunks = [
            ContextChunk(id="ctx_1", summary="A" * 200, message_range=(0, 5), token_estimate=100),
            ContextChunk(id="ctx_2", summary="B" * 200, message_range=(5, 10), token_estimate=100),
        ]

        result = await service.get_relevant_context("Next step")

        # Should only include one chunk due to budget
        assert result.count("[Earlier context]") <= 1

    @pytest.mark.asyncio
    async def test_inject_context_disabled(self, mock_llm, test_memory):
        """Test context injection when disabled"""
        config = ContextServiceConfig(enabled=False)
        service = ContextEngineeringService(llm=mock_llm, config=config)

        result = await service.inject_context(test_memory, "Next step")

        assert result is False

    @pytest.mark.asyncio
    async def test_inject_context_no_relevant(self, mock_llm, test_memory):
        """Test context injection with no relevant context"""
        service = ContextEngineeringService(llm=mock_llm)
        # No chunks to inject

        result = await service.inject_context(test_memory, "Next step")

        assert result is False

    @pytest.mark.asyncio
    async def test_inject_context_success(self, mock_llm, test_memory):
        """Test successful context injection"""
        config = ContextServiceConfig(use_semantic_retrieval=False)
        service = ContextEngineeringService(llm=mock_llm, config=config)

        # Add a context chunk
        service._context_chunks = [
            ContextChunk(
                id="ctx_1",
                summary="Previous search found 3 tutorials",
                message_range=(0, 5),
                token_estimate=50
            )
        ]

        original_len = len(test_memory.messages)
        result = await service.inject_context(test_memory, "Next step")

        assert result is True
        # Should have added a message
        assert len(test_memory.messages) == original_len + 1
        # Check it's a system message with context
        injected = test_memory.messages[1]  # After original system message
        assert injected["role"] == "system"
        assert "context" in injected["content"].lower()

    def test_record_step_completed(self, mock_llm):
        """Test recording step completion"""
        service = ContextEngineeringService(llm=mock_llm)
        service._steps_since_summary = 0

        service.record_step_completed()

        assert service._steps_since_summary == 1

    def test_record_messages_added(self, mock_llm):
        """Test recording messages added"""
        service = ContextEngineeringService(llm=mock_llm)
        service._messages_since_summary = 0

        service.record_messages_added(5)

        assert service._messages_since_summary == 5

    def test_get_stats(self, mock_llm):
        """Test getting service statistics"""
        service = ContextEngineeringService(llm=mock_llm)
        service._context_chunks = [
            ContextChunk(id="ctx_1", summary="Test", message_range=(0, 5), token_estimate=100),
            ContextChunk(id="ctx_2", summary="Test2", message_range=(5, 10), token_estimate=150),
        ]
        service._messages_since_summary = 10
        service._steps_since_summary = 3

        stats = service.get_stats()

        assert stats["context_chunks"] == 2
        assert stats["total_chunk_tokens"] == 250
        assert stats["messages_since_summary"] == 10
        assert stats["steps_since_summary"] == 3

    def test_reset(self, mock_llm):
        """Test service reset"""
        service = ContextEngineeringService(llm=mock_llm)
        service._context_chunks = [
            ContextChunk(id="ctx_1", summary="Test", message_range=(0, 5))
        ]
        service._chunk_counter = 5
        service._messages_since_summary = 20
        service._steps_since_summary = 10

        service.reset()

        assert len(service._context_chunks) == 0
        assert service._chunk_counter == 0
        assert service._messages_since_summary == 0
        assert service._steps_since_summary == 0

    def test_extract_tags(self, mock_llm):
        """Test tag extraction from summary"""
        service = ContextEngineeringService(llm=mock_llm)

        tags = service._extract_tags("Performed a search and found error in the file")

        assert "search" in tags
        assert "error" in tags
        assert "file" in tags

    def test_format_messages(self, mock_llm):
        """Test message formatting for summarization"""
        service = ContextEngineeringService(llm=mock_llm)

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        result = service._format_messages(messages)

        assert "USER: Hello" in result
        assert "ASSISTANT: Hi there" in result

    def test_format_messages_truncates_long_content(self, mock_llm):
        """Test that long messages are truncated"""
        service = ContextEngineeringService(llm=mock_llm)

        messages = [
            {"role": "assistant", "content": "A" * 1000},
        ]

        result = service._format_messages(messages)

        # Should be truncated with ...
        assert "..." in result
        assert len(result) < 1000


class TestMemoryFork:
    """Tests for Memory fork/merge functionality added for ToT"""

    def test_fork_creates_copy(self):
        """Test that fork creates an independent copy"""
        memory = Memory()
        memory.add_messages([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ])

        forked = memory.fork()

        assert len(forked.messages) == 2
        assert forked.messages[0]["content"] == "Hello"

        # Modify forked memory
        forked.add_message({"role": "user", "content": "New message"})

        # Original should be unchanged
        assert len(memory.messages) == 2
        assert len(forked.messages) == 3

    def test_fork_preserves_messages(self):
        """Test fork with preserve_messages parameter"""
        memory = Memory()
        for i in range(10):
            memory.add_message({"role": "user", "content": f"Message {i}"})

        forked = memory.fork(preserve_messages=3)

        assert len(forked.messages) == 3
        assert "Message 7" in forked.messages[0]["content"]
        assert "Message 9" in forked.messages[2]["content"]

    def test_fork_copies_config(self):
        """Test that fork copies memory config"""
        memory = Memory()
        memory.config.auto_compact_threshold = 25
        memory.config.preserve_recent = 5

        forked = memory.fork()

        assert forked.config.auto_compact_threshold == 25
        assert forked.config.preserve_recent == 5

    def test_merge_from_adds_messages(self):
        """Test merging messages from another memory"""
        memory1 = Memory()
        memory1.add_messages([
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"}
        ])

        memory2 = Memory()
        memory2.add_messages([
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"}
        ])

        added = memory1.merge_from(memory2)

        assert added == 2
        assert len(memory1.messages) == 4

    def test_merge_from_deduplicates(self):
        """Test that merge deduplicates messages"""
        memory1 = Memory()
        memory1.add_messages([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ])

        memory2 = Memory()
        memory2.add_messages([
            {"role": "user", "content": "Hello"},  # Duplicate
            {"role": "assistant", "content": "Different response"}
        ])

        added = memory1.merge_from(memory2, deduplicate=True)

        # Only non-duplicate should be added
        assert added == 1
        assert len(memory1.messages) == 3

    def test_merge_from_no_dedup(self):
        """Test merge without deduplication"""
        memory1 = Memory()
        memory1.add_message({"role": "user", "content": "Hello"})

        memory2 = Memory()
        memory2.add_message({"role": "user", "content": "Hello"})

        added = memory1.merge_from(memory2, deduplicate=False)

        assert added == 1
        assert len(memory1.messages) == 2
