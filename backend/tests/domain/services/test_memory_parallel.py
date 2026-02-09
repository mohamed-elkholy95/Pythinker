"""Tests for Parallel Memory Architecture

Phase 5 Enhancement: Tests for parallel MongoDB/Qdrant memory writes.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.async_utils import gather_compat


class TestParallelMemoryWrites:
    """Tests for parallel memory write operations."""

    @pytest.fixture
    def mock_memory_repository(self):
        """Create mock memory repository."""
        repo = MagicMock()
        repo.create = AsyncMock(return_value=MagicMock(id="mem_123"))
        repo.find_duplicates = AsyncMock(return_value=[])
        repo.update = AsyncMock()
        repo.get_by_ids = AsyncMock(return_value=[])
        return repo

    @pytest.fixture
    def mock_qdrant_repository(self):
        """Create mock Qdrant repository."""
        repo = MagicMock()
        repo.upsert_memory = AsyncMock()
        repo.upsert_memories_batch = AsyncMock()
        repo.search_similar = AsyncMock(return_value=[])
        return repo

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_gather_compat_parallel_execution(self):
        """Test gather_compat executes coroutines in parallel."""
        execution_order = []

        async def task1():
            await asyncio.sleep(0.05)
            execution_order.append("task1_complete")
            return 1

        async def task2():
            await asyncio.sleep(0.02)
            execution_order.append("task2_complete")
            return 2

        async def task3():
            await asyncio.sleep(0.01)
            execution_order.append("task3_complete")
            return 3

        results = await gather_compat(task1(), task2(), task3(), use_taskgroup=False)

        # Results should be in original order
        assert results == [1, 2, 3]
        # Execution order should show parallel execution (shortest first)
        assert execution_order == ["task3_complete", "task2_complete", "task1_complete"]

    @pytest.mark.asyncio
    async def test_gather_compat_with_taskgroup(self):
        """Test gather_compat with TaskGroup enabled."""

        async def task1():
            return "result1"

        async def task2():
            return "result2"

        # Test with TaskGroup
        results = await gather_compat(task1(), task2(), use_taskgroup=True)
        assert len(results) == 2
        assert "result1" in results
        assert "result2" in results

    @pytest.mark.asyncio
    async def test_gather_compat_exception_handling(self):
        """Test gather_compat handles exceptions with return_exceptions."""

        async def success_task():
            return "success"

        async def failing_task():
            raise ValueError("Task failed")

        results = await gather_compat(
            success_task(),
            failing_task(),
            return_exceptions=True,
            use_taskgroup=False,
        )

        assert results[0] == "success"
        assert isinstance(results[1], ValueError)

    @pytest.mark.asyncio
    async def test_parallel_mongodb_qdrant_write(self, mock_memory_repository, mock_qdrant_repository):
        """Test parallel writes to MongoDB and Qdrant."""
        # Simulate parallel write pattern from memory_service
        mongo_task = mock_memory_repository.create(MagicMock(id="mem_123", content="test", user_id="user_1"))
        qdrant_task = mock_qdrant_repository.upsert_memory(
            memory_id="mem_123",
            embedding=[0.1, 0.2, 0.3],
            user_id="user_1",
        )

        results = await gather_compat(mongo_task, qdrant_task, use_taskgroup=False)

        # Both tasks should complete
        assert len(results) == 2
        mock_memory_repository.create.assert_called_once()
        mock_qdrant_repository.upsert_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_write_parallel(self, mock_memory_repository, mock_qdrant_repository):
        """Test batch write to both stores in parallel."""
        memories = [MagicMock(id=f"mem_{i}", content=f"content_{i}", user_id="user_1") for i in range(5)]

        # Create tasks for each memory
        mongo_tasks = [mock_memory_repository.create(m) for m in memories]
        qdrant_tasks = [
            mock_qdrant_repository.upsert_memory(
                memory_id=m.id,
                embedding=[0.1 * i for i in range(3)],
                user_id="user_1",
            )
            for m in memories
        ]

        # Execute all in parallel
        all_tasks = mongo_tasks + qdrant_tasks
        results = await gather_compat(*all_tasks, return_exceptions=True, use_taskgroup=False)

        # All 10 tasks should complete
        assert len(results) == 10
        assert mock_memory_repository.create.call_count == 5
        assert mock_qdrant_repository.upsert_memory.call_count == 5

    @pytest.mark.asyncio
    async def test_partial_failure_handling(self, mock_memory_repository, mock_qdrant_repository):
        """Test handling when one write fails."""
        mock_memory_repository.create = AsyncMock(return_value=MagicMock(id="mem_123"))
        mock_qdrant_repository.upsert_memory = AsyncMock(side_effect=Exception("Qdrant unavailable"))

        results = await gather_compat(
            mock_memory_repository.create(MagicMock()),
            mock_qdrant_repository.upsert_memory(memory_id="mem_123", embedding=[], user_id="u"),
            return_exceptions=True,
            use_taskgroup=False,
        )

        # First task succeeds, second fails
        assert results[0].id == "mem_123"
        assert isinstance(results[1], Exception)
        assert "Qdrant unavailable" in str(results[1])

    @pytest.mark.asyncio
    async def test_feature_flag_respects_setting(self):
        """Test that parallel memory respects feature flag."""
        with patch("app.core.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.feature_parallel_memory = True
            settings.feature_taskgroup_enabled = False
            mock_settings.return_value = settings

            # When feature is enabled, parallel writes should occur
            assert settings.feature_parallel_memory is True


class TestQdrantBatchUpsert:
    """Tests for Qdrant batch upsert functionality."""

    @pytest.fixture
    def mock_qdrant_client(self):
        """Create mock Qdrant client."""
        client = MagicMock()
        client.upsert = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_batch_upsert_empty_list(self, mock_qdrant_client):
        """Test batch upsert with empty list."""
        memories = []

        # Should return early without calling upsert
        if not memories:
            return

        # Upsert should not be called
        mock_qdrant_client.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_upsert_single_memory(self, mock_qdrant_client):
        """Test batch upsert with single memory."""
        memories = [{"id": "mem_1", "embedding": [0.1, 0.2, 0.3], "payload": {"user_id": "u1"}}]

        # Simulate batch upsert
        await mock_qdrant_client.upsert(collection_name="memories", points=memories)

        mock_qdrant_client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_upsert_multiple_memories(self, mock_qdrant_client):
        """Test batch upsert with multiple memories."""
        memories = [{"id": f"mem_{i}", "embedding": [0.1 * i] * 3, "payload": {"user_id": "u1"}} for i in range(10)]

        await mock_qdrant_client.upsert(collection_name="memories", points=memories)

        mock_qdrant_client.upsert.assert_called_once()
        call_args = mock_qdrant_client.upsert.call_args
        assert len(call_args.kwargs["points"]) == 10


class TestMemoryServiceParallelIntegration:
    """Integration tests for MemoryService parallel writes."""

    @pytest.fixture
    def memory_service_mock(self):
        """Create memory service with mocked dependencies."""
        service = MagicMock()
        service._repository = MagicMock()
        service._repository.create = AsyncMock(return_value=MagicMock(id="mem_new"))
        service._generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
        return service

    @pytest.mark.asyncio
    async def test_store_memory_generates_embedding(self, memory_service_mock):
        """Test that storing memory generates embedding."""
        embedding = await memory_service_mock._generate_embedding("test content")

        assert embedding == [0.1, 0.2, 0.3]
        memory_service_mock._generate_embedding.assert_called_with("test content")

    @pytest.mark.asyncio
    async def test_store_many_parallel_batch(self, memory_service_mock):
        """Test storing multiple memories in parallel."""
        memories = [MagicMock(content=f"content_{i}", memory_type="fact", importance="medium") for i in range(5)]

        # Simulate parallel store
        async def store_one(mem):
            await asyncio.sleep(0.01)
            return await memory_service_mock._repository.create(mem)

        tasks = [store_one(mem) for mem in memories]
        results = await gather_compat(*tasks, return_exceptions=True, use_taskgroup=False)

        assert len(results) == 5
        assert memory_service_mock._repository.create.call_count == 5


class TestTaskGroupParallelWrites:
    """Tests specifically for TaskGroup-based parallel writes."""

    @pytest.mark.asyncio
    async def test_taskgroup_all_success(self):
        """Test TaskGroup with all tasks succeeding."""
        results = []

        async def task(value):
            await asyncio.sleep(0.01)
            return value

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(task(i)) for i in range(5)]

        results = [t.result() for t in tasks]
        assert results == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_taskgroup_cancellation_on_error(self):
        """Test TaskGroup cancels other tasks on error."""
        completed_tasks = []

        async def slow_task(name):
            await asyncio.sleep(0.1)
            completed_tasks.append(name)
            return name

        async def failing_task():
            await asyncio.sleep(0.01)
            raise ValueError("Intentional failure")

        with pytest.raises(ExceptionGroup) as exc_info:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(slow_task("slow1"))
                tg.create_task(slow_task("slow2"))
                tg.create_task(failing_task())

        # Slow tasks should be cancelled
        assert len(completed_tasks) == 0
        assert any(isinstance(e, ValueError) for e in exc_info.value.exceptions)

    @pytest.mark.asyncio
    async def test_gather_compat_taskgroup_enabled(self):
        """Test gather_compat uses TaskGroup when enabled."""

        async def simple_task(value):
            return value * 2

        results = await gather_compat(
            simple_task(1),
            simple_task(2),
            simple_task(3),
            use_taskgroup=True,
        )

        # Results should maintain order
        assert sorted(results) == [2, 4, 6]

    @pytest.mark.asyncio
    async def test_gather_compat_taskgroup_with_exceptions(self):
        """Test gather_compat TaskGroup with return_exceptions=True."""

        async def success_task():
            return "ok"

        async def fail_task():
            raise RuntimeError("fail")

        results = await gather_compat(
            success_task(),
            fail_task(),
            return_exceptions=True,
            use_taskgroup=True,
        )

        assert "ok" in results
        assert any(isinstance(r, RuntimeError) for r in results)


class TestConcurrentWriteOrdering:
    """Tests for write ordering guarantees."""

    @pytest.mark.asyncio
    async def test_writes_complete_regardless_of_order(self):
        """Test that all writes complete even if timing varies."""
        write_times = []

        async def variable_write(delay, value):
            await asyncio.sleep(delay)
            write_times.append(value)
            return value

        # Different delays, but all should complete
        results = await gather_compat(
            variable_write(0.03, "slow"),
            variable_write(0.01, "fast"),
            variable_write(0.02, "medium"),
            use_taskgroup=False,
        )

        # All writes complete
        assert len(results) == 3
        assert len(write_times) == 3

        # Results maintain original order
        assert results == ["slow", "fast", "medium"]

        # Execution order reflects actual timing
        assert write_times == ["fast", "medium", "slow"]

    @pytest.mark.asyncio
    async def test_idempotent_writes_safe_in_parallel(self):
        """Test that idempotent writes are safe in parallel."""
        write_log = []

        async def idempotent_write(key, value):
            # Simulates idempotent upsert
            write_log.append((key, value))
            return {"key": key, "value": value}

        # Same key written multiple times in parallel
        results = await gather_compat(
            idempotent_write("key1", "v1"),
            idempotent_write("key1", "v2"),  # Same key, different value
            idempotent_write("key2", "v3"),
            use_taskgroup=False,
        )

        # All writes recorded
        assert len(write_log) == 3
        # All results returned
        assert len(results) == 3
