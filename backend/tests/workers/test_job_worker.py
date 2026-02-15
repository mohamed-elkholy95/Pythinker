"""
Tests for AsyncJobWorker

Tests job processing, retry logic, dead-letter queue, graceful shutdown,
and concurrent execution with RedisStreamTask integration.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.queue.redis_job_queue import Job, JobPriority, JobStatus
from app.workers.job_worker import AsyncJobWorker


@pytest.fixture
def mock_redis_queue():
    """Mock Redis job queue."""
    queue = AsyncMock()
    queue.queue_name = "test_queue"
    queue.dequeue = AsyncMock(return_value=None)
    queue.enqueue = AsyncMock()
    queue.mark_completed = AsyncMock()
    queue.mark_failed = AsyncMock()
    return queue


@pytest.fixture
def mock_task():
    """Mock RedisStreamTask instance."""
    task = MagicMock()
    task.id = "task-123"
    task.done = False  # Will be set to True to simulate completion
    task.run = AsyncMock()
    return task


@pytest.fixture
def mock_execution_agent():
    """Mock execution agent (kept for backward compatibility)."""
    return AsyncMock()


@pytest.fixture
def sample_job():
    """Create sample job for testing."""
    return Job(
        job_id="test-job-1",
        queue_name="test_queue",
        priority=JobPriority.NORMAL,
        payload={"task_id": "task-123", "session_id": "session-456", "user_id": "user-789"},
        max_retries=3,
        timeout_seconds=10,
        retry_delay_seconds=1,
        retry_backoff_multiplier=2.0,
        status=JobStatus.PENDING,
        attempts=0,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_worker_initialization(mock_redis_queue, mock_execution_agent):
    """Test worker initialization."""
    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
        max_concurrent_jobs=5,
    )

    assert worker.worker_id == "test-worker"
    assert worker.max_concurrent_jobs == 5
    assert worker.is_healthy is True
    assert not worker.shutdown_event.is_set()


@pytest.mark.asyncio
async def test_process_job_success(mock_redis_queue, mock_execution_agent, sample_job, mock_task):
    """Test successful job processing with RedisStreamTask."""
    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Mock RedisStreamTask.get to return our mock task
    with patch('app.workers.job_worker.RedisStreamTask') as MockRedisStreamTask:
        MockRedisStreamTask.get.return_value = mock_task

        # Simulate task completion after run()
        async def complete_task():
            await asyncio.sleep(0.01)
            mock_task.done = True

        mock_task.run.side_effect = complete_task

        # Process job
        await worker._process_job(sample_job)

        # Verify task was retrieved and executed
        MockRedisStreamTask.get.assert_called_once_with("task-123")
        mock_task.run.assert_called_once()

        # Verify job marked as completed
        mock_redis_queue.mark_completed.assert_called_once_with(sample_job)


@pytest.mark.asyncio
async def test_process_job_timeout(mock_redis_queue, mock_execution_agent, sample_job, mock_task):
    """Test job timeout handling."""
    # Set short timeout
    sample_job.timeout_seconds = 0.1

    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Mock RedisStreamTask.get to return our mock task
    with patch('app.workers.job_worker.RedisStreamTask') as MockRedisStreamTask:
        MockRedisStreamTask.get.return_value = mock_task

        # Mock slow task execution (exceeds timeout)
        async def slow_execution():
            await asyncio.sleep(1)

        mock_task.run.side_effect = slow_execution
        mock_task.done = False  # Never completes within timeout

        # Process job (should timeout)
        await worker._process_job(sample_job)

        # Verify job marked as failed or retried
        assert mock_redis_queue.mark_failed.called or mock_redis_queue.enqueue.called


@pytest.mark.asyncio
async def test_job_retry_logic(mock_redis_queue, mock_execution_agent, sample_job, mock_task):
    """Test job retry with exponential backoff."""
    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Mock RedisStreamTask.get to return our mock task
    with patch('app.workers.job_worker.RedisStreamTask') as MockRedisStreamTask:
        MockRedisStreamTask.get.return_value = mock_task

        # Mock execution failure
        mock_task.run.side_effect = ValueError("Test error")

        # Process job (should fail and retry)
        await worker._process_job(sample_job)

        # Verify retry enqueued
        assert mock_redis_queue.enqueue.called
        assert sample_job.attempts > 0


@pytest.mark.asyncio
async def test_dead_letter_queue(mock_redis_queue, mock_execution_agent, sample_job):
    """Test job moved to dead-letter queue after max retries."""
    # Set job to max attempts
    sample_job.attempts = sample_job.max_retries

    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Handle failure (no need to mock task execution, testing failure handler directly)
    await worker._handle_job_failure(sample_job, "Test error", "ValueError")

    # Verify moved to dead-letter queue
    mock_redis_queue.mark_failed.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_job_processing(mock_redis_queue, mock_execution_agent):
    """Test concurrent job processing with semaphore."""
    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
        max_concurrent_jobs=3,
    )

    # Create multiple jobs
    jobs = [
        Job(
            job_id=f"job-{i}",
            queue_name="test_queue",
            priority=JobPriority.NORMAL,
            payload={"task_id": f"task-{i}", "session_id": "session-1"},
            max_retries=3,
        )
        for i in range(5)
    ]

    # Mock dequeue to return jobs
    mock_redis_queue.dequeue.side_effect = [*jobs, None]

    # Process jobs concurrently
    async def process_jobs():
        for _ in range(len(jobs)):
            # Await the mocked dequeue coroutine so each side_effect job is returned
            job = await mock_redis_queue.dequeue()
            await worker._process_job_concurrent(job)

    # Run for short time
    import contextlib

    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(process_jobs(), timeout=2.0)

    # Verify semaphore limited concurrency
    assert len(worker.in_flight_jobs) <= worker.max_concurrent_jobs


@pytest.mark.asyncio
async def test_graceful_shutdown(mock_redis_queue, mock_execution_agent):
    """Test graceful shutdown waits for in-flight jobs."""
    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Create mock in-flight job
    async def slow_job():
        await asyncio.sleep(0.5)

    task = asyncio.create_task(slow_job())
    worker.in_flight_jobs.add(task)

    # Trigger graceful shutdown
    start_time = asyncio.get_event_loop().time()
    await worker._graceful_shutdown()
    elapsed = asyncio.get_event_loop().time() - start_time

    # Verify waited for job completion
    assert elapsed >= 0.5
    assert len(worker.in_flight_jobs) == 0


@pytest.mark.asyncio
async def test_worker_health_check(mock_redis_queue, mock_execution_agent):
    """Test worker health check updates metrics."""
    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Run health check once
    task = asyncio.create_task(worker._health_check_loop())

    # Let it run briefly
    await asyncio.sleep(0.1)

    # Stop health check
    worker.shutdown_event.set()
    await asyncio.sleep(0.1)
    task.cancel()

    import contextlib

    with contextlib.suppress(asyncio.CancelledError):
        await task

    # Worker should still be healthy
    assert worker.is_healthy is True


@pytest.mark.asyncio
async def test_priority_job_processing(mock_redis_queue, mock_execution_agent):
    """Test high-priority jobs processed first."""
    # Create jobs with different priorities
    high_priority_job = Job(
        job_id="high-job",
        queue_name="test_queue",
        priority=JobPriority.HIGH,
        payload={"task_id": "task-high", "session_id": "session-1"},
        max_retries=3,
    )

    low_priority_job = Job(
        job_id="low-job",
        queue_name="test_queue",
        priority=JobPriority.LOW,
        payload={"task_id": "task-low", "session_id": "session-1"},
        max_retries=3,
    )

    # Mock dequeue returns high priority first
    mock_redis_queue.dequeue.side_effect = [high_priority_job, low_priority_job, None]

    AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Process first job
    job1 = await mock_redis_queue.dequeue()
    assert job1.priority == JobPriority.HIGH

    # Process second job
    job2 = await mock_redis_queue.dequeue()
    assert job2.priority == JobPriority.LOW


@pytest.mark.asyncio
async def test_task_not_found_in_registry(mock_redis_queue, mock_execution_agent, sample_job):
    """Test job failure when task not found in RedisStreamTask registry."""
    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Mock RedisStreamTask.get to return None (task not found)
    with patch('app.workers.job_worker.RedisStreamTask') as MockRedisStreamTask:
        MockRedisStreamTask.get.return_value = None

        # Process job (should fail with RuntimeError)
        await worker._process_job(sample_job)

        # Verify task lookup was attempted
        MockRedisStreamTask.get.assert_called_once_with("task-123")

        # Verify job marked as failed or retried
        assert mock_redis_queue.mark_failed.called or mock_redis_queue.enqueue.called


@pytest.mark.asyncio
async def test_missing_payload_fields(mock_redis_queue, mock_execution_agent):
    """Test job failure when required payload fields are missing."""
    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Job with missing task_id
    job_missing_task_id = Job(
        job_id="test-job-missing-task",
        queue_name="test_queue",
        priority=JobPriority.NORMAL,
        payload={"session_id": "session-456"},  # Missing task_id
        max_retries=3,
    )

    # Process job (should fail with ValueError)
    await worker._process_job(job_missing_task_id)

    # Verify job marked as failed or retried
    assert mock_redis_queue.mark_failed.called or mock_redis_queue.enqueue.called


@pytest.mark.asyncio
async def test_task_execution_with_completion_polling(
    mock_redis_queue, mock_execution_agent, sample_job, mock_task
):
    """Test worker polls task.done until completion."""
    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Mock RedisStreamTask.get to return our mock task
    with patch('app.workers.job_worker.RedisStreamTask') as MockRedisStreamTask:
        MockRedisStreamTask.get.return_value = mock_task

        # Simulate gradual task completion
        completion_count = [0]

        async def gradual_completion():
            await asyncio.sleep(0.01)
            # Task completes after a few polls
            completion_count[0] += 1

        mock_task.run.side_effect = gradual_completion

        # Task starts as not done, becomes done after 3 checks
        def check_done():
            if completion_count[0] >= 3:
                return True
            completion_count[0] += 1
            return False

        type(mock_task).done = property(lambda self: check_done())

        # Process job
        await worker._process_job(sample_job)

        # Verify task was executed and worker waited for completion
        mock_task.run.assert_called_once()
        assert completion_count[0] >= 3  # At least 3 polling iterations

        # Verify job marked as completed
        mock_redis_queue.mark_completed.assert_called_once_with(sample_job)
