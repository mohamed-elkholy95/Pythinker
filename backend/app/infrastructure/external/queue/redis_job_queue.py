"""
Redis Job Queue - Self-hosted job queue with dead-letter queue support.

Features:
- Priority levels (high, normal, low)
- Automatic retries with exponential backoff
- Dead-letter queue for failed jobs
- Job timeout handling
- Dashboard metrics (via Prometheus)
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class JobPriority(IntEnum):
    """Job priority levels (higher number = higher priority)."""

    LOW = 0
    NORMAL = 5
    HIGH = 10


class JobStatus(str):
    """Job status values."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


@dataclass
class Job:
    """Job definition."""

    job_id: str
    queue_name: str
    priority: JobPriority
    payload: dict[str, Any]
    max_retries: int = 3
    timeout_seconds: int = 300  # 5 minutes default
    retry_delay_seconds: int = 60  # 1 minute base delay
    retry_backoff_multiplier: float = 2.0  # Exponential backoff

    # Internal state
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class RedisJobQueue:
    """
    Redis-based job queue with dead-letter queue support.

    Queue structure:
    - queue:{queue_name}:pending - Sorted set (by priority + timestamp)
    - queue:{queue_name}:processing - Hash (job_id -> started_at)
    - queue:{queue_name}:completed - Sorted set (by completed_at)
    - queue:{queue_name}:dead_letter - Sorted set (by failed_at)
    - job:{job_id} - Hash (job data)
    """

    def __init__(self, redis_client: redis.Redis, queue_name: str = "default"):
        self.redis = redis_client
        self.queue_name = queue_name

        # Queue keys
        self.pending_key = f"queue:{queue_name}:pending"
        self.processing_key = f"queue:{queue_name}:processing"
        self.completed_key = f"queue:{queue_name}:completed"
        self.dead_letter_key = f"queue:{queue_name}:dead_letter"

    async def enqueue(
        self,
        job_id: str,
        payload: dict[str, Any],
        priority: JobPriority = JobPriority.NORMAL,
        max_retries: int = 3,
        timeout_seconds: int = 300,
    ) -> Job:
        """
        Enqueue a job for processing.

        Args:
            job_id: Unique job ID
            payload: Job payload dict
            priority: Job priority
            max_retries: Maximum retry attempts
            timeout_seconds: Job timeout

        Returns:
            Job object
        """
        job = Job(
            job_id=job_id,
            queue_name=self.queue_name,
            priority=priority,
            payload=payload,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )

        # Store job data
        job_key = f"job:{job_id}"
        await self.redis.hset(
            job_key,
            mapping={
                "job_id": job.job_id,
                "queue_name": job.queue_name,
                "priority": job.priority.value,
                "payload": json.dumps(job.payload),
                "max_retries": job.max_retries,
                "timeout_seconds": job.timeout_seconds,
                "status": job.status,
                "attempts": job.attempts,
                "created_at": job.created_at.isoformat(),
            },
        )

        # Add to pending queue (sorted by priority + timestamp)
        # Score: priority * 1e10 + timestamp (higher priority processed first)
        score = priority.value * 1e10 + time.time()
        await self.redis.zadd(self.pending_key, {job_id: score})

        logger.info(f"Enqueued job {job_id} with priority {priority.name} in queue {self.queue_name}")
        return job

    async def dequeue(self, timeout_seconds: int = 30) -> Job | None:
        """
        Dequeue next job for processing (blocks until job available or timeout).

        Args:
            timeout_seconds: Max time to wait for job

        Returns:
            Job or None if timeout
        """
        # Pop highest priority job from pending queue
        result = await self.redis.bzpopmax(self.pending_key, timeout=timeout_seconds)

        if not result:
            return None

        _, job_id, _ = result

        # Load job data
        job_key = f"job:{job_id}"
        job_data = await self.redis.hgetall(job_key)

        if not job_data:
            logger.warning(f"Job {job_id} data not found, skipping")
            return None

        # Parse job
        job = Job(
            job_id=job_data[b"job_id"].decode(),
            queue_name=job_data[b"queue_name"].decode(),
            priority=JobPriority(int(job_data[b"priority"])),
            payload=json.loads(job_data[b"payload"]),
            max_retries=int(job_data[b"max_retries"]),
            timeout_seconds=int(job_data[b"timeout_seconds"]),
            status=JobStatus.PROCESSING,
            attempts=int(job_data[b"attempts"]) + 1,
            created_at=datetime.fromisoformat(job_data[b"created_at"].decode()),
            started_at=datetime.now(UTC),
        )

        # Update job status
        await self.redis.hset(
            job_key,
            mapping={
                "status": job.status,
                "attempts": job.attempts,
                "started_at": job.started_at.isoformat(),
            },
        )

        # Add to processing queue
        await self.redis.hset(self.processing_key, job_id, job.started_at.isoformat())

        logger.info(f"Dequeued job {job_id} (attempt {job.attempts}/{job.max_retries})")
        return job

    async def mark_completed(self, job: Job) -> None:
        """
        Mark job as completed.

        Args:
            job: Completed job
        """
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)

        job_key = f"job:{job.job_id}"
        await self.redis.hset(
            job_key,
            mapping={
                "status": job.status,
                "completed_at": job.completed_at.isoformat(),
            },
        )

        # Remove from processing
        await self.redis.hdel(self.processing_key, job.job_id)

        # Add to completed queue (TTL: 24 hours)
        score = job.completed_at.timestamp()
        await self.redis.zadd(self.completed_key, {job.job_id: score})
        await self.redis.expire(job_key, 86400)  # 24 hours

        logger.info(f"Job {job.job_id} marked as completed")

    async def mark_failed(self, job: Job, error: str) -> None:
        """
        Mark job as failed and retry or move to dead-letter queue.

        Args:
            job: Failed job
            error: Error message
        """
        job.error = error

        if job.attempts < job.max_retries:
            # Retry with exponential backoff
            delay = job.retry_delay_seconds * (job.retry_backoff_multiplier ** (job.attempts - 1))
            retry_at = datetime.now(UTC) + timedelta(seconds=delay)

            logger.info(f"Job {job.job_id} failed (attempt {job.attempts}/{job.max_retries}), retrying in {delay:.0f}s")

            # Update job
            job_key = f"job:{job.job_id}"
            await self.redis.hset(
                job_key,
                mapping={
                    "status": JobStatus.PENDING,
                    "error": error,
                },
            )

            # Remove from processing
            await self.redis.hdel(self.processing_key, job.job_id)

            # Re-enqueue with delay (using score as timestamp)
            score = job.priority.value * 1e10 + retry_at.timestamp()
            await self.redis.zadd(self.pending_key, {job.job_id: score})

        else:
            # Move to dead-letter queue
            job.status = JobStatus.DEAD_LETTER

            job_key = f"job:{job.job_id}"
            await self.redis.hset(
                job_key,
                mapping={
                    "status": job.status,
                    "error": error,
                    "failed_at": datetime.now(UTC).isoformat(),
                },
            )

            # Remove from processing
            await self.redis.hdel(self.processing_key, job.job_id)

            # Add to dead-letter queue (NO TTL - inspect manually)
            score = time.time()
            await self.redis.zadd(self.dead_letter_key, {job.job_id: score})

            logger.error(f"Job {job.job_id} moved to dead-letter queue after {job.attempts} attempts: {error}")

    async def get_queue_stats(self) -> dict[str, int]:
        """
        Get queue statistics.

        Returns:
            Dict with queue depths
        """
        return {
            "pending": await self.redis.zcard(self.pending_key),
            "processing": await self.redis.hlen(self.processing_key),
            "completed": await self.redis.zcard(self.completed_key),
            "dead_letter": await self.redis.zcard(self.dead_letter_key),
        }

    async def get_dead_letter_jobs(self, limit: int = 100) -> list[str]:
        """
        Get jobs in dead-letter queue.

        Args:
            limit: Maximum jobs to return

        Returns:
            List of job IDs
        """
        job_ids = await self.redis.zrange(self.dead_letter_key, 0, limit - 1, desc=True)
        return [job_id.decode() for job_id in job_ids]

    async def retry_dead_letter_job(self, job_id: str) -> bool:
        """
        Retry a job from dead-letter queue.

        Args:
            job_id: Job ID to retry

        Returns:
            True if job was moved back to pending queue
        """
        # Remove from dead-letter queue
        removed = await self.redis.zrem(self.dead_letter_key, job_id)

        if not removed:
            return False

        # Update job status
        job_key = f"job:{job_id}"
        await self.redis.hset(
            job_key,
            mapping={
                "status": JobStatus.PENDING,
                "attempts": 0,  # Reset attempts
                "error": None,
            },
        )

        # Re-enqueue with normal priority
        score = JobPriority.NORMAL.value * 1e10 + time.time()
        await self.redis.zadd(self.pending_key, {job_id: score})

        logger.info(f"Retried dead-letter job {job_id}")
        return True
