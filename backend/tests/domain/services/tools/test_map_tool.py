"""Tests for MapTool - Generic Parallel Batch Execution.

Tests the MapTool class including:
- Parallel execution with concurrency control
- Error handling without stopping other tasks
- Retry functionality
- Progress callbacks
- Timeout handling
- Duration tracking
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.domain.services.tools.map_tool import (
    MapResult,
    MapTask,
    MapTool,
)


class MockWorker:
    """Mock worker for testing MapTool."""

    def __init__(
        self,
        delay: float = 0.01,
        fail_on_ids: list[str] | None = None,
        return_value: Any = "success",
    ):
        self.delay = delay
        self.fail_on_ids = fail_on_ids or []
        self.return_value = return_value
        self.call_count = 0
        self.call_order: list[str] = []

    async def execute(self, task: MapTask) -> Any:
        """Execute the task with optional delay and failure."""
        self.call_count += 1
        self.call_order.append(task.id)

        if self.delay > 0:
            await asyncio.sleep(self.delay)

        if task.id in self.fail_on_ids:
            raise ValueError(f"Intentional failure for task {task.id}")

        return self.return_value


class CountingWorker:
    """Worker that tracks concurrent executions."""

    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self.current_concurrent = 0
        self.max_concurrent = 0
        self.lock = asyncio.Lock()

    async def execute(self, task: MapTask) -> Any:
        """Execute with concurrent tracking."""
        async with self.lock:
            self.current_concurrent += 1
            if self.current_concurrent > self.max_concurrent:
                self.max_concurrent = self.current_concurrent

        await asyncio.sleep(self.delay)

        async with self.lock:
            self.current_concurrent -= 1

        return f"processed_{task.id}"


@pytest.fixture
def mock_worker() -> MockWorker:
    """Create a mock worker for testing."""
    return MockWorker()


@pytest.fixture
def counting_worker() -> CountingWorker:
    """Create a counting worker for concurrency testing."""
    return CountingWorker()


class TestMapTask:
    """Tests for MapTask Pydantic model."""

    def test_create_map_task(self):
        """Test creating a MapTask with required fields."""
        task = MapTask(id="task-1", input="test input")
        assert task.id == "task-1"
        assert task.input == "test input"
        assert task.metadata == {}

    def test_create_map_task_with_metadata(self):
        """Test creating a MapTask with metadata."""
        task = MapTask(
            id="task-2",
            input={"key": "value"},
            metadata={"priority": "high", "category": "search"},
        )
        assert task.id == "task-2"
        assert task.input == {"key": "value"}
        assert task.metadata["priority"] == "high"
        assert task.metadata["category"] == "search"

    def test_map_task_with_various_input_types(self):
        """Test MapTask accepts various input types."""
        # String input
        task1 = MapTask(id="1", input="string")
        assert task1.input == "string"

        # Dict input
        task2 = MapTask(id="2", input={"url": "https://example.com"})
        assert task2.input["url"] == "https://example.com"

        # List input
        task3 = MapTask(id="3", input=[1, 2, 3])
        assert task3.input == [1, 2, 3]

        # Complex nested input
        task4 = MapTask(id="4", input={"nested": {"deep": {"value": 42}}})
        assert task4.input["nested"]["deep"]["value"] == 42


class TestMapResult:
    """Tests for MapResult Pydantic model."""

    def test_create_successful_result(self):
        """Test creating a successful MapResult."""
        result = MapResult(
            id="task-1",
            success=True,
            output="result data",
            duration_ms=150.5,
        )
        assert result.id == "task-1"
        assert result.success is True
        assert result.output == "result data"
        assert result.error is None
        assert result.duration_ms == 150.5

    def test_create_failed_result(self):
        """Test creating a failed MapResult."""
        result = MapResult(
            id="task-2",
            success=False,
            error="Connection timeout",
            duration_ms=5000.0,
        )
        assert result.id == "task-2"
        assert result.success is False
        assert result.output is None
        assert result.error == "Connection timeout"

    def test_default_duration(self):
        """Test default duration_ms value."""
        result = MapResult(id="task-3", success=True)
        assert result.duration_ms == 0


class TestMapToolParallelExecution:
    """Tests for MapTool parallel execution."""

    @pytest.mark.asyncio
    async def test_map_tool_parallel_execution(self, mock_worker: MockWorker):
        """Test basic parallel execution of tasks."""
        map_tool = MapTool(worker=mock_worker, max_concurrency=5)
        tasks = [MapTask(id=str(i), input=f"Item {i}") for i in range(10)]

        results = await map_tool.execute(tasks)

        assert len(results) == 10
        assert all(r.success for r in results)
        assert mock_worker.call_count == 10

    @pytest.mark.asyncio
    async def test_map_tool_respects_concurrency(self, counting_worker: CountingWorker):
        """Test that concurrency limit is respected."""
        max_concurrency = 2
        map_tool = MapTool(worker=counting_worker, max_concurrency=max_concurrency)
        tasks = [MapTask(id=str(i), input=f"Item {i}") for i in range(6)]

        results = await map_tool.execute(tasks)

        assert len(results) == 6
        assert all(r.success for r in results)
        # Max concurrent should not exceed the limit
        assert counting_worker.max_concurrent <= max_concurrency

    @pytest.mark.asyncio
    async def test_map_tool_handles_failures(self):
        """Test that one failure doesn't stop other tasks."""
        # Fail on task "1" (the middle one)
        worker = MockWorker(fail_on_ids=["1"])
        map_tool = MapTool(worker=worker, max_concurrency=3)
        tasks = [MapTask(id=str(i), input=f"Item {i}") for i in range(3)]

        results = await map_tool.execute(tasks)

        assert len(results) == 3

        # Check individual results by ID
        result_map = {r.id: r for r in results}
        assert result_map["0"].success is True
        assert result_map["1"].success is False
        assert result_map["1"].error is not None
        assert "Intentional failure" in result_map["1"].error
        assert result_map["2"].success is True

    @pytest.mark.asyncio
    async def test_results_preserve_order(self, mock_worker: MockWorker):
        """Test that results are returned in same order as input tasks."""
        mock_worker.delay = 0.01  # Small delay to ensure async execution
        map_tool = MapTool(worker=mock_worker, max_concurrency=3)
        tasks = [MapTask(id=f"task-{i}", input=f"Item {i}") for i in range(10)]

        results = await map_tool.execute(tasks)

        # Results should be in same order as input tasks
        for i, result in enumerate(results):
            assert result.id == f"task-{i}"


class TestMapToolTimeoutHandling:
    """Tests for MapTool timeout handling."""

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test that tasks exceeding timeout are marked as failed."""
        # Worker with 1 second delay
        worker = MockWorker(delay=1.0)
        map_tool = MapTool(worker=worker, max_concurrency=2)
        tasks = [MapTask(id=str(i), input=f"Item {i}") for i in range(2)]

        # Execute with 0.1 second timeout
        results = await map_tool.execute(tasks, timeout_per_task=0.1)

        assert len(results) == 2
        # All should fail due to timeout
        assert all(not r.success for r in results)
        assert all("timeout" in (r.error or "").lower() for r in results)

    @pytest.mark.asyncio
    async def test_no_timeout_allows_completion(self, mock_worker: MockWorker):
        """Test that tasks complete when no timeout is set."""
        mock_worker.delay = 0.05
        map_tool = MapTool(worker=mock_worker, max_concurrency=5)
        tasks = [MapTask(id=str(i), input=f"Item {i}") for i in range(5)]

        results = await map_tool.execute(tasks, timeout_per_task=None)

        assert len(results) == 5
        assert all(r.success for r in results)


class TestMapToolRetry:
    """Tests for MapTool retry functionality."""

    @pytest.mark.asyncio
    async def test_execute_with_retry_success_after_retry(self):
        """Test that retries can recover from transient failures."""
        call_counts: dict[str, int] = {}

        class RetryableWorker:
            async def execute(self, task: MapTask) -> Any:
                call_counts[task.id] = call_counts.get(task.id, 0) + 1
                # Fail first attempt, succeed on retry
                if call_counts[task.id] < 2:
                    raise ValueError("Transient failure")
                return "success"

        worker = RetryableWorker()
        map_tool = MapTool(worker=worker, max_concurrency=2)
        tasks = [MapTask(id="task-1", input="data")]

        results = await map_tool.execute_with_retry(tasks, max_retries=2, retry_delay=0.01)

        assert len(results) == 1
        assert results[0].success is True
        assert call_counts["task-1"] == 2

    @pytest.mark.asyncio
    async def test_execute_with_retry_exhausts_retries(self):
        """Test that task fails after exhausting all retries."""

        class AlwaysFailWorker:
            async def execute(self, task: MapTask) -> Any:
                raise ValueError("Permanent failure")

        worker = AlwaysFailWorker()
        map_tool = MapTool(worker=worker, max_concurrency=2)
        tasks = [MapTask(id="task-1", input="data")]

        results = await map_tool.execute_with_retry(tasks, max_retries=3, retry_delay=0.01)

        assert len(results) == 1
        assert results[0].success is False
        assert "Permanent failure" in (results[0].error or "")

    @pytest.mark.asyncio
    async def test_execute_with_retry_respects_delay(self):
        """Test that retry delay is respected."""
        import time

        call_times: list[float] = []

        class TimingWorker:
            async def execute(self, task: MapTask) -> Any:
                call_times.append(time.time())
                if len(call_times) < 3:
                    raise ValueError("Retry me")
                return "success"

        worker = TimingWorker()
        map_tool = MapTool(worker=worker, max_concurrency=1)
        tasks = [MapTask(id="task-1", input="data")]

        await map_tool.execute_with_retry(tasks, max_retries=3, retry_delay=0.1)

        # Check that delays were respected (at least 0.08 seconds between attempts)
        for i in range(1, len(call_times)):
            delay = call_times[i] - call_times[i - 1]
            assert delay >= 0.08, f"Delay too short: {delay}"


class TestMapToolProgressCallback:
    """Tests for MapTool progress callback."""

    @pytest.mark.asyncio
    async def test_on_progress_callback(self, mock_worker: MockWorker):
        """Test that progress callback is called for each task."""
        progress_calls: list[dict[str, Any]] = []

        def on_progress(
            task_id: str,
            status: str,
            completed: int,
            total: int,
            result: MapResult | None = None,
        ) -> None:
            progress_calls.append(
                {
                    "task_id": task_id,
                    "status": status,
                    "completed": completed,
                    "total": total,
                    "result": result,
                }
            )

        map_tool = MapTool(
            worker=mock_worker,
            max_concurrency=2,
            on_progress=on_progress,
        )
        tasks = [MapTask(id=str(i), input=f"Item {i}") for i in range(3)]

        results = await map_tool.execute(tasks)

        assert len(results) == 3
        # Should have at least one callback per task (completed)
        assert len(progress_calls) >= 3

        # Check that we have completed callbacks
        completed_calls = [c for c in progress_calls if c["status"] == "completed"]
        assert len(completed_calls) == 3

    @pytest.mark.asyncio
    async def test_progress_callback_with_failures(self):
        """Test progress callback reports failures correctly."""
        progress_calls: list[dict[str, Any]] = []

        def on_progress(
            task_id: str,
            status: str,
            completed: int,
            total: int,
            result: MapResult | None = None,
        ) -> None:
            progress_calls.append(
                {
                    "task_id": task_id,
                    "status": status,
                    "result": result,
                }
            )

        worker = MockWorker(fail_on_ids=["1"])
        map_tool = MapTool(
            worker=worker,
            max_concurrency=3,
            on_progress=on_progress,
        )
        tasks = [MapTask(id=str(i), input=f"Item {i}") for i in range(3)]

        await map_tool.execute(tasks)

        # Find the failed task callback
        failed_calls = [c for c in progress_calls if c["result"] is not None and not c["result"].success]
        assert len(failed_calls) == 1
        assert failed_calls[0]["task_id"] == "1"


class TestMapToolEdgeCases:
    """Tests for MapTool edge cases."""

    @pytest.mark.asyncio
    async def test_empty_task_list(self, mock_worker: MockWorker):
        """Test execution with empty task list."""
        map_tool = MapTool(worker=mock_worker, max_concurrency=5)

        results = await map_tool.execute([])

        assert results == []
        assert mock_worker.call_count == 0

    @pytest.mark.asyncio
    async def test_single_task(self, mock_worker: MockWorker):
        """Test execution with a single task."""
        map_tool = MapTool(worker=mock_worker, max_concurrency=5)
        tasks = [MapTask(id="only-one", input="single item")]

        results = await map_tool.execute(tasks)

        assert len(results) == 1
        assert results[0].id == "only-one"
        assert results[0].success is True
        assert mock_worker.call_count == 1

    @pytest.mark.asyncio
    async def test_duration_tracking(self, mock_worker: MockWorker):
        """Test that duration_ms is tracked for each task."""
        mock_worker.delay = 0.05  # 50ms delay
        map_tool = MapTool(worker=mock_worker, max_concurrency=2)
        tasks = [MapTask(id=str(i), input=f"Item {i}") for i in range(3)]

        results = await map_tool.execute(tasks)

        for result in results:
            assert result.duration_ms > 0
            # Should be at least close to 50ms
            assert result.duration_ms >= 40  # Allow some margin

    @pytest.mark.asyncio
    async def test_large_batch_execution(self, mock_worker: MockWorker):
        """Test execution with a large batch of tasks."""
        mock_worker.delay = 0.001  # Very short delay
        map_tool = MapTool(worker=mock_worker, max_concurrency=20)
        tasks = [MapTask(id=str(i), input=f"Item {i}") for i in range(100)]

        results = await map_tool.execute(tasks)

        assert len(results) == 100
        assert all(r.success for r in results)
        assert mock_worker.call_count == 100

    @pytest.mark.asyncio
    async def test_concurrency_one_executes_sequentially(self, mock_worker: MockWorker):
        """Test that concurrency=1 executes tasks sequentially."""
        mock_worker.delay = 0.01
        map_tool = MapTool(worker=mock_worker, max_concurrency=1)
        tasks = [MapTask(id=str(i), input=f"Item {i}") for i in range(5)]

        results = await map_tool.execute(tasks)

        assert len(results) == 5
        # Tasks should be executed in order due to concurrency=1
        assert mock_worker.call_order == ["0", "1", "2", "3", "4"]

    @pytest.mark.asyncio
    async def test_worker_returning_none(self):
        """Test handling worker that returns None."""

        class NoneWorker:
            async def execute(self, task: MapTask) -> Any:
                return None

        worker = NoneWorker()
        map_tool = MapTool(worker=worker, max_concurrency=2)
        tasks = [MapTask(id="task-1", input="data")]

        results = await map_tool.execute(tasks)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].output is None

    @pytest.mark.asyncio
    async def test_worker_returning_complex_output(self):
        """Test handling worker that returns complex output."""

        class ComplexWorker:
            async def execute(self, task: MapTask) -> Any:
                return {
                    "id": task.id,
                    "processed": True,
                    "results": [1, 2, 3],
                    "nested": {"key": "value"},
                }

        worker = ComplexWorker()
        map_tool = MapTool(worker=worker, max_concurrency=2)
        tasks = [MapTask(id="task-1", input="data")]

        results = await map_tool.execute(tasks)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].output["id"] == "task-1"
        assert results[0].output["processed"] is True
        assert results[0].output["results"] == [1, 2, 3]


class TestWorkerProtocol:
    """Tests for WorkerProtocol compliance."""

    @pytest.mark.asyncio
    async def test_mock_worker_implements_protocol(self, mock_worker: MockWorker):
        """Test that MockWorker correctly implements WorkerProtocol."""
        # This should work without type errors - create MapTool to verify protocol works
        _ = MapTool(worker=mock_worker, max_concurrency=1)
        task = MapTask(id="test", input="data")

        result = await mock_worker.execute(task)

        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_mock_as_worker(self):
        """Test that AsyncMock can be used as a worker."""
        async_worker = AsyncMock()
        async_worker.execute.return_value = "mocked result"

        map_tool = MapTool(worker=async_worker, max_concurrency=1)
        tasks = [MapTask(id="test", input="data")]

        results = await map_tool.execute(tasks)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].output == "mocked result"
        async_worker.execute.assert_called_once()
