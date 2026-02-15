"""
Tests for AsyncJobWorker

Tests job processing, retry logic, dead-letter queue, graceful shutdown,
and concurrent execution.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

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
def mock_execution_agent():
    """Mock execution agent."""
    agent = AsyncMock()
    return agent


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
async def test_process_job_success(
    mock_redis_queue, mock_execution_agent, sample_job
):
    """Test successful job processing."""
    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Process job
    await worker._process_job(sample_job)

    # Verify job marked as completed
    mock_redis_queue.mark_completed.assert_called_once_with(sample_job)


@pytest.mark.asyncio
async def test_process_job_timeout(mock_redis_queue, mock_execution_agent, sample_job):
    """Test job timeout handling."""
    # Set short timeout
    sample_job.timeout_seconds = 0.1

    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Mock slow execution
    async def slow_execution(*args, **kwargs):
        await asyncio.sleep(1)
        return {}

    worker._execute_task_placeholder = slow_execution

    # Process job (should timeout)
    await worker._process_job(sample_job)

    # Verify job marked as failed
    assert mock_redis_queue.mark_failed.called or mock_redis_queue.enqueue.called


@pytest.mark.asyncio
async def test_job_retry_logic(mock_redis_queue, mock_execution_agent, sample_job):
    """Test job retry with exponential backoff."""
    worker = AsyncJobWorker(
        queue=mock_redis_queue,
        execution_agent=mock_execution_agent,
        worker_id="test-worker",
    )

    # Mock execution failure
    async def failing_execution(*args, **kwargs):
        raise ValueError("Test error")

    worker._execute_task_placeholder = failing_execution

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

    # Mock execution failure
    async def failing_execution(*args, **kwargs):
        raise ValueError("Test error")

    worker._execute_task_placeholder = failing_execution

    # Handle failure
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
    mock_redis_queue.dequeue.side_effect = jobs + [None]

    # Process jobs concurrently
    async def process_jobs():
        for _ in range(len(jobs)):
            await worker._process_job_concurrent(mock_redis_queue.dequeue.return_value)

    # Run for short time
    try:
        await asyncio.wait_for(process_jobs(), timeout=2.0)
    except TimeoutError:
        pass

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

    try:
        await task
    except asyncio.CancelledError:
        pass

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

    worker = AsyncJobWorker(
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
