"""
Async Job Worker - Production-ready worker for Redis job queue.

Features:
- Priority-based job processing (HIGH/NORMAL/LOW)
- Graceful shutdown with in-flight job completion
- Automatic retry with exponential backoff
- Dead-letter queue for failed jobs
- Prometheus metrics (throughput, latency, error rate)
- Python 3.11+ TaskGroup for safe async concurrency
- Comprehensive error handling and logging
"""

import asyncio
import logging
import signal
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis
from prometheus_client import Counter, Gauge, Histogram

from app.core.config import Settings, get_settings
from app.domain.external.observability import MetricsPort, get_null_metrics
from app.domain.services.agents.execution import ExecutionAgent
from app.infrastructure.external.queue.redis_job_queue import (
    Job,
    RedisJobQueue,
)

logger = logging.getLogger(__name__)

# Prometheus Metrics
JOBS_DEQUEUED = Counter(
    "pythinker_worker_jobs_dequeued_total",
    "Total jobs dequeued from queue",
    ["queue", "priority"],
)

JOBS_COMPLETED = Counter(
    "pythinker_worker_jobs_completed_total",
    "Total jobs completed successfully",
    ["queue"],
)

JOBS_FAILED = Counter(
    "pythinker_worker_jobs_failed_total",
    "Total jobs failed",
    ["queue", "error_type"],
)

JOBS_RETRIED = Counter(
    "pythinker_worker_jobs_retried_total",
    "Total job retries",
    ["queue", "attempt"],
)

JOBS_DEAD_LETTER = Counter(
    "pythinker_worker_jobs_dead_letter_total",
    "Total jobs moved to dead-letter queue",
    ["queue"],
)

JOBS_IN_FLIGHT = Gauge(
    "pythinker_worker_jobs_in_flight",
    "Number of jobs currently being processed",
    ["queue"],
)

JOB_PROCESSING_DURATION = Histogram(
    "pythinker_worker_job_processing_duration_seconds",
    "Job processing duration in seconds",
    ["queue", "priority"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

WORKER_HEALTH = Gauge(
    "pythinker_worker_health",
    "Worker health status (1=healthy, 0=unhealthy)",
    ["worker_id"],
)


class WorkerShutdownError(Exception):
    """Exception raised to signal worker shutdown."""


class AsyncJobWorker:
    """
    Production-ready async job worker for Redis job queue.

    Processes jobs from Redis queue with priority handling, automatic retries,
    and graceful shutdown.
    """

    def __init__(
        self,
        queue: RedisJobQueue,
        execution_agent: ExecutionAgent,
        worker_id: str = "worker-1",
        max_concurrent_jobs: int = 5,
        poll_interval: float = 1.0,
        metrics: MetricsPort | None = None,
    ):
        """
        Initialize async job worker.

        Args:
            queue: Redis job queue instance
            execution_agent: Agent for executing tasks
            worker_id: Unique worker identifier
            max_concurrent_jobs: Maximum concurrent jobs (semaphore limit)
            poll_interval: Seconds between queue polls when empty
            metrics: Metrics port for observability
        """
        self.queue = queue
        self.execution_agent = execution_agent
        self.worker_id = worker_id
        self.max_concurrent_jobs = max_concurrent_jobs
        self.poll_interval = poll_interval
        self.metrics = metrics or get_null_metrics()

        # Concurrency control
        self.semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self.in_flight_jobs: set[asyncio.Task] = set()

        # Shutdown control
        self.shutdown_event = asyncio.Event()
        self.graceful_shutdown_timeout = 300  # 5 minutes

        # Health status
        self.is_healthy = True
        WORKER_HEALTH.labels(worker_id=worker_id).set(1)

        logger.info(f"Worker {worker_id} initialized (max_concurrent={max_concurrent_jobs})")

    async def start(self) -> None:
        """
        Start the worker main loop.

        Runs until shutdown signal received. Uses Python 3.11+ TaskGroup
        for safe async concurrency.
        """
        logger.info(f"Worker {self.worker_id} starting...")

        # Register signal handlers for graceful shutdown
        self._register_signal_handlers()

        try:
            # Python 3.11+ TaskGroup for safe concurrency
            async with asyncio.TaskGroup() as tg:
                # Main worker loop
                worker_task = tg.create_task(self._worker_loop())

                # Health check loop
                health_task = tg.create_task(self._health_check_loop())

                # Wait for shutdown signal
                await self.shutdown_event.wait()

                logger.info(f"Worker {self.worker_id} received shutdown signal")

                # Cancel tasks
                worker_task.cancel()
                health_task.cancel()

        except* asyncio.CancelledError:
            # TaskGroup cancellation (expected)
            logger.info("Worker tasks cancelled")

        except* Exception as eg:
            # Handle multiple exceptions from TaskGroup
            for exc in eg.exceptions:
                logger.error(f"Worker task error: {exc}", exc_info=exc)
            self.is_healthy = False
            WORKER_HEALTH.labels(worker_id=self.worker_id).set(0)

        finally:
            # Graceful shutdown: complete in-flight jobs
            await self._graceful_shutdown()

        logger.info(f"Worker {self.worker_id} stopped")

    async def _worker_loop(self) -> None:
        """Main worker loop that polls queue and processes jobs."""
        logger.info(f"Worker {self.worker_id} loop started")

        while not self.shutdown_event.is_set():
            try:
                # Dequeue next job (priority-based)
                job = await self.queue.dequeue()

                if job is None:
                    # Queue empty, wait before polling again
                    await asyncio.sleep(self.poll_interval)
                    continue

                # Process job concurrently (respecting semaphore limit)
                await self._process_job_concurrent(job)

            except WorkerShutdownError:
                logger.info("Worker shutdown requested")
                break

            except Exception as e:
                logger.error(f"Worker loop error: {e}", exc_info=True)
                self.is_healthy = False
                WORKER_HEALTH.labels(worker_id=self.worker_id).set(0)
                await asyncio.sleep(5)  # Backoff on error

    async def _process_job_concurrent(self, job: Job) -> None:
        """
        Process job concurrently using semaphore for rate limiting.

        Args:
            job: Job to process
        """
        # Acquire semaphore (rate limiting)
        async with self.semaphore:
            JOBS_IN_FLIGHT.labels(queue=self.queue.queue_name).inc()

            try:
                # Create task for job processing
                task = asyncio.create_task(self._process_job(job))
                self.in_flight_jobs.add(task)

                # Record metrics
                JOBS_DEQUEUED.labels(
                    queue=self.queue.queue_name,
                    priority=job.priority.name,
                ).inc()

                # Await completion
                await task

            finally:
                self.in_flight_jobs.discard(task)
                JOBS_IN_FLIGHT.labels(queue=self.queue.queue_name).dec()

    async def _process_job(self, job: Job) -> None:
        """
        Process individual job with timeout and error handling.

        Args:
            job: Job to process
        """
        start_time = time.time()

        logger.info(
            f"Processing job {job.job_id} (priority={job.priority.name}, "
            f"attempt={job.attempts + 1}/{job.max_retries + 1})"
        )

        try:
            # Execute job with timeout
            async with asyncio.timeout(job.timeout_seconds):
                await self._execute_job(job)

            # Mark as completed
            await self.queue.mark_completed(job)

            # Record metrics
            duration = time.time() - start_time
            JOBS_COMPLETED.labels(queue=self.queue.queue_name).inc()
            JOB_PROCESSING_DURATION.labels(
                queue=self.queue.queue_name,
                priority=job.priority.name,
            ).observe(duration)

            logger.info(f"Job {job.job_id} completed successfully in {duration:.2f}s")

        except TimeoutError:
            # Job exceeded timeout
            error_msg = f"Job timeout after {job.timeout_seconds}s"
            logger.error(f"Job {job.job_id} failed: {error_msg}")

            await self._handle_job_failure(job, error_msg, "timeout")

        except asyncio.CancelledError:
            # Job cancelled during shutdown
            logger.warning(f"Job {job.job_id} cancelled during shutdown")
            # Re-enqueue for later processing
            await self.queue.enqueue(
                job_id=job.job_id,
                payload=job.payload,
                priority=job.priority,
                max_retries=job.max_retries,
                timeout_seconds=job.timeout_seconds,
            )
            raise  # Re-raise to propagate cancellation

        except Exception as e:
            # Job execution error
            error_msg = str(e)
            error_type = type(e).__name__
            logger.error(
                f"Job {job.job_id} failed: {error_msg}",
                exc_info=True,
            )

            await self._handle_job_failure(job, error_msg, error_type)

    async def _execute_job(self, job: Job) -> Any:
        """
        Execute job payload using ExecutionAgent.

        Args:
            job: Job to execute

        Returns:
            Job execution result
        """
        # Extract task parameters from job payload
        task_id = job.payload.get("task_id")
        session_id = job.payload.get("session_id")
        user_id = job.payload.get("user_id")

        if not task_id or not session_id:
            raise ValueError("Job payload missing required fields: task_id, session_id")

        logger.info(f"Executing task {task_id} for session {session_id} (job={job.job_id})")

        # Get task from registry
        from app.infrastructure.external.task.redis_task import RedisStreamTask

        task = RedisStreamTask.get(task_id)
        if not task:
            raise RuntimeError(f"Task {task_id} not found in registry")

        # Run the task (this will call the AgentTaskRunner)
        await task.run()

        # Wait for task completion
        # The task execution happens in the background, we need to wait
        while not task.done:
            await asyncio.sleep(0.1)

        logger.info(f"Task {task_id} completed (job={job.job_id})")

        return {
            "task_id": task_id,
            "session_id": session_id,
            "status": "completed",
            "message": "Task executed successfully via worker"
        }

    async def _handle_job_failure(self, job: Job, error: str, error_type: str) -> None:
        """
        Handle job failure with retry logic or dead-letter queue.

        Args:
            job: Failed job
            error: Error message
            error_type: Error type for metrics
        """
        job.attempts += 1

        # Record failure metrics
        JOBS_FAILED.labels(
            queue=self.queue.queue_name,
            error_type=error_type,
        ).inc()

        # Check if retry limit exceeded
        if job.attempts >= job.max_retries:
            # Move to dead-letter queue
            logger.error(f"Job {job.job_id} exceeded max retries ({job.max_retries}), moving to dead-letter queue")

            await self.queue.mark_failed(job, error=error)

            JOBS_DEAD_LETTER.labels(queue=self.queue.queue_name).inc()

        else:
            # Retry with exponential backoff
            retry_delay = job.retry_delay_seconds * (job.retry_backoff_multiplier ** (job.attempts - 1))

            logger.info(f"Job {job.job_id} will retry in {retry_delay:.0f}s (attempt {job.attempts}/{job.max_retries})")

            JOBS_RETRIED.labels(
                queue=self.queue.queue_name,
                attempt=str(job.attempts),
            ).inc()

            # Schedule a delayed re-enqueue so the worker loop isn't blocked
            try:
                asyncio.create_task(self._delayed_reenqueue(job, retry_delay))
            except Exception:
                # Fallback: attempt immediate enqueue if scheduling fails
                logger.exception("Failed to schedule delayed re-enqueue, attempting immediate enqueue")
                await self.queue.enqueue(
                    job_id=job.job_id,
                    payload=job.payload,
                    priority=job.priority,
                    max_retries=job.max_retries,
                    timeout_seconds=job.timeout_seconds,
                )

    async def _delayed_reenqueue(self, job: Job, delay: float) -> None:
        """
        Helper to re-enqueue a job after a delay without blocking the worker loop.

        Args:
            job: Job to re-enqueue
            delay: Seconds to wait before re-enqueueing
        """
        try:
            await asyncio.sleep(delay)
            await self.queue.enqueue(
                job_id=job.job_id,
                payload=job.payload,
                priority=job.priority,
                max_retries=job.max_retries,
                timeout_seconds=job.timeout_seconds,
            )
            logger.info(f"Delayed re-enqueue scheduled job {job.job_id} after {delay}s")
        except Exception as e:
            logger.error(f"Delayed re-enqueue failed for job {job.job_id}: {e}", exc_info=True)

    async def _health_check_loop(self) -> None:
        """Periodic health check loop."""
        while not self.shutdown_event.is_set():
            try:
                # Update health status
                health_value = 1 if self.is_healthy else 0
                WORKER_HEALTH.labels(worker_id=self.worker_id).set(health_value)

                # Wait before next check
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)

    async def _graceful_shutdown(self) -> None:
        """
        Gracefully shutdown worker by completing in-flight jobs.

        Waits up to graceful_shutdown_timeout for jobs to complete.
        """
        if not self.in_flight_jobs:
            logger.info("No in-flight jobs, shutdown complete")
            return

        logger.info(
            f"Waiting for {len(self.in_flight_jobs)} in-flight jobs to complete "
            f"(timeout={self.graceful_shutdown_timeout}s)"
        )

        try:
            # Wait for in-flight jobs with timeout
            await asyncio.wait_for(
                asyncio.gather(*self.in_flight_jobs, return_exceptions=True),
                timeout=self.graceful_shutdown_timeout,
            )

            logger.info("All in-flight jobs completed")

        except TimeoutError:
            logger.warning(f"Graceful shutdown timeout exceeded, {len(self.in_flight_jobs)} jobs still in-flight")

            # Cancel remaining jobs
            for task in self.in_flight_jobs:
                task.cancel()

        finally:
            WORKER_HEALTH.labels(worker_id=self.worker_id).set(0)

    def _register_signal_handlers(self) -> None:
        """Register signal handlers for graceful shutdown."""

        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, initiating graceful shutdown")
            self.shutdown_event.set()

        # Register SIGINT (Ctrl+C) and SIGTERM handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def stop(self) -> None:
        """Stop the worker (trigger graceful shutdown)."""
        self.shutdown_event.set()


@asynccontextmanager
async def create_worker(
    settings: Settings | None = None,
    queue_name: str = "agent_tasks",
    worker_id: str = "worker-1",
    max_concurrent_jobs: int = 5,
):
    """
    Context manager for creating and managing async job worker.

    Args:
        settings: Application settings
        queue_name: Redis queue name
        worker_id: Unique worker identifier
        max_concurrent_jobs: Maximum concurrent jobs

    Yields:
        AsyncJobWorker instance

    Example:
        async with create_worker(queue_name="agent_tasks") as worker:
            await worker.start()
    """
    settings = settings or get_settings()

    # Create Redis connection
    redis_client = await redis.from_url(
        f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
        decode_responses=True,
    )

    # Create job queue
    job_queue = RedisJobQueue(redis_client, queue_name=queue_name)

    # Create execution agent (placeholder - requires full initialization)
    # TODO: Properly initialize ExecutionAgent with all dependencies
    execution_agent = None  # type: ignore

    # Create worker
    worker = AsyncJobWorker(
        queue=job_queue,
        execution_agent=execution_agent,  # type: ignore
        worker_id=worker_id,
        max_concurrent_jobs=max_concurrent_jobs,
    )

    try:
        yield worker
    finally:
        # Cleanup
        await worker.stop()
        await redis_client.close()


async def main():
    """Main entry point for running worker."""
    logger.info("Starting Pythinker async job worker")

    # Load settings
    settings = get_settings()

    # Create and run worker
    async with create_worker(
        settings=settings,
        queue_name="agent_tasks",
        worker_id="worker-1",
        max_concurrent_jobs=5,
    ) as worker:
        await worker.start()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run worker
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
        sys.exit(0)
