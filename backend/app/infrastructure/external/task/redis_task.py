from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, ClassVar

from app.domain.external.task import Task, TaskRunner
from app.infrastructure.external.message_queue.redis_stream_queue import MessageQueue, RedisStreamQueue

if TYPE_CHECKING:
    from app.domain.models.source_citation import SourceCitation

logger = logging.getLogger(__name__)

_LIVENESS_KEY_PREFIX = "task:liveness:"
_LIVENESS_TTL_SECONDS = 30
_LIVENESS_HEARTBEAT_INTERVAL = 10


class RedisStreamTask(Task):
    """Redis Stream-based task implementation following the Task protocol."""

    _task_registry: ClassVar[dict[str, RedisStreamTask]] = {}

    def __init__(self, runner: TaskRunner):
        """Initialize Redis Stream task with a task runner.

        Args:
            runner: The TaskRunner instance that will execute this task
        """
        self._runner = runner
        self._id = str(uuid.uuid4())
        self._execution_task: asyncio.Task | None = None
        self._background_tasks: set[asyncio.Task] = set()

        # Create input/output streams based on task ID
        input_stream_name = f"task:input:{self._id}"
        output_stream_name = f"task:output:{self._id}"
        self._input_stream = RedisStreamQueue(input_stream_name)
        self._output_stream = RedisStreamQueue(output_stream_name)
        self._paused = False

        # Register task instance
        RedisStreamTask._task_registry[self._id] = self

        # Liveness signal (Redis key heartbeated during execution)
        self._session_id: str | None = getattr(runner, "session_id", None)
        self._heartbeat_task: asyncio.Task | None = None

    @property
    def id(self) -> str:
        """Task ID."""
        return self._id

    @property
    def done(self) -> bool:
        """Check if the task is done.

        Returns:
            bool: True if the task is done, False otherwise
        """
        if self._execution_task is None:
            return True
        return self._execution_task.done()

    async def run(self) -> None:
        """Run the task using the provided TaskRunner."""
        if self.done:
            self._execution_task = asyncio.create_task(self._execute_task())
            logger.info(f"Task {self._id} execution started")

    def cancel(self) -> bool:
        """Cancel the task.

        Registry cleanup is deferred to ``_on_task_done()`` so that the task
        remains visible in the registry until the asyncio.Task actually stops.
        This prevents SSE reconnects from seeing an orphaned RUNNING session
        with no corresponding task object.

        Returns:
            bool: True if the task is cancelled, False otherwise
        """
        if not self.done:
            request_cancellation = getattr(self._runner, "request_cancellation", None)
            if callable(request_cancellation):
                try:
                    request_cancellation()
                except Exception as exc:
                    logger.debug("Failed to signal cooperative cancellation for task %s: %s", self._id, exc)

            self._execution_task.cancel()
            logger.info(f"Task {self._id} cancelled")
            # DO NOT call _cleanup_registry() here — task is still stopping.
            # Cleanup happens in _on_task_done() once the task is truly done.
            return True

        # Already done — safe to clean up now
        self._cleanup_registry()
        return False

    def pause(self) -> bool:
        """Pause the task.

        Returns:
            bool: True if the task is paused, False otherwise
        """
        if not self.done and not self._paused:
            self._paused = True
            logger.info(f"Task {self._id} paused")
            return True
        return False

    def resume(self) -> bool:
        """Resume a paused task.

        Returns:
            bool: True if the task is resumed, False otherwise
        """
        if self._paused:
            self._paused = False
            logger.info(f"Task {self._id} resumed")
            return True
        return False

    @property
    def paused(self) -> bool:
        """Check if the task is paused.

        Returns:
            bool: True if the task is paused, False otherwise
        """
        return self._paused

    @property
    def input_stream(self) -> MessageQueue:
        """Input stream."""
        return self._input_stream

    @property
    def output_stream(self) -> MessageQueue:
        """Output stream."""
        return self._output_stream

    @property
    def runner(self) -> TaskRunner:
        """Expose task runner for internal orchestration."""
        return self._runner

    def hydrate_reactivation_sources(self, sources: list[SourceCitation]) -> None:
        """Delegate source hydration to the runner if it supports it."""
        handler = getattr(self._runner, "hydrate_reactivation_sources", None)
        if callable(handler):
            handler(sources)

    def _on_task_done(self) -> None:
        """Called when the task is done."""
        self._task_done = True
        if self._runner:

            async def _finalize_runner() -> None:
                try:
                    await self._runner.on_done(self)
                except Exception as e:
                    logger.warning("Runner on_done failed for task %s: %s", self._id, e)
                try:
                    # Memory only: keep sandbox/MCP/factory for follow-up tasks in the same session
                    _release = getattr(self._runner, "release_task_resources", None)
                    if callable(_release):
                        await _release()
                    else:
                        await self._runner.destroy()
                except Exception as e:
                    logger.warning("Runner task resource release failed for task %s: %s", self._id, e)

            task = asyncio.create_task(_finalize_runner())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        self._cleanup_registry()

    def _cleanup_registry(self) -> None:
        """Remove this task from the registry and cleanup Redis streams."""
        if self._id in RedisStreamTask._task_registry:
            del RedisStreamTask._task_registry[self._id]
            logger.info(f"Task {self._id} removed from registry")

        # Schedule Redis stream cleanup in background
        task = asyncio.create_task(self._cleanup_redis_streams())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _cleanup_redis_streams(self) -> None:
        """Schedule stream expiry instead of immediate deletion.

        Allows SSE consumers to replay recent events after task completion.
        Streams auto-expire after a configurable TTL (default 5 minutes).
        The TTL is read from ``Settings.redis_stream_ttl_seconds`` so it can be
        tuned via the ``REDIS_STREAM_TTL_SECONDS`` environment variable without
        a code change.
        """
        try:
            from app.core.config import get_settings

            ttl_seconds = get_settings().redis_stream_ttl_seconds
        except Exception:
            ttl_seconds = 300  # safe fallback if settings unavailable at teardown
        try:
            await self._input_stream._ensure_initialized()
            redis_client = self._input_stream._redis.client
            await redis_client.expire(self._input_stream._stream_name, ttl_seconds)
            await redis_client.expire(self._output_stream._stream_name, ttl_seconds)
            logger.info("Set %ds TTL on Redis streams for task %s", ttl_seconds, self._id)
        except Exception as e:
            logger.warning("Failed to set stream TTL for task %s, falling back to delete: %s", self._id, e)
            try:
                await self._input_stream.delete_stream()
                await self._output_stream.delete_stream()
            except Exception:
                logger.debug("Fallback stream delete also failed for task %s", self._id)

    async def _execute_task(self) -> None:
        """Execute the task using the TaskRunner."""
        try:
            await self._set_liveness()
            self._heartbeat_task = asyncio.create_task(self._heartbeat_liveness())
            await self._runner.run(self)
        except asyncio.CancelledError:
            logger.info("Task %s was cancelled", self._id)
        except Exception as e:
            logger.exception("Task %s execution failed: %s", self._id, e)
        finally:
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
            await self._clear_liveness()
            self._on_task_done()

    @classmethod
    def get(cls, task_id: str) -> RedisStreamTask | None:
        """Get a task by its ID.

        Returns:
            Optional[RedisStreamTask]: Task instance if found, None otherwise
        """
        return cls._task_registry.get(task_id)

    @classmethod
    async def get_liveness(cls, session_id: str) -> str | None:
        """Check if a task is alive for the given session.

        Returns:
            The task_id string if a liveness key exists, None otherwise.
        """
        try:
            from app.infrastructure.storage.redis import get_redis

            raw_redis = get_redis().client
            value = await raw_redis.get(f"{_LIVENESS_KEY_PREFIX}{session_id}")
            # Redis client uses decode_responses=True, so value is already str
            return value or None
        except Exception as e:
            logger.warning("Failed to read liveness key for session %s: %s", session_id, e)
            return None

    async def _set_liveness(self) -> None:
        """SET liveness key in Redis with TTL. Value = task_id."""
        if not self._session_id:
            return
        try:
            from app.infrastructure.storage.redis import get_redis

            raw_redis = get_redis().client
            await raw_redis.set(
                f"{_LIVENESS_KEY_PREFIX}{self._session_id}",
                self._id,
                ex=_LIVENESS_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning("Failed to set liveness key for session %s: %s", self._session_id, e)

    async def _heartbeat_liveness(self) -> None:
        """Periodically refresh liveness key TTL."""
        while True:
            await asyncio.sleep(_LIVENESS_HEARTBEAT_INTERVAL)
            await self._set_liveness()

    async def _clear_liveness(self) -> None:
        """DELETE liveness key on task completion/failure."""
        if not self._session_id:
            return
        try:
            from app.infrastructure.storage.redis import get_redis

            raw_redis = get_redis().client
            await raw_redis.delete(f"{_LIVENESS_KEY_PREFIX}{self._session_id}")
        except Exception as e:
            logger.warning("Failed to clear liveness key for session %s: %s", self._session_id, e)

    @classmethod
    def create(cls, runner: TaskRunner) -> RedisStreamTask:
        """Create a new task instance with the specified TaskRunner.

        Args:
            runner: The TaskRunner that will execute this task

        Returns:
            RedisStreamTask: New task instance
        """
        return cls(runner)

    @classmethod
    async def destroy(cls) -> None:
        """Destroy all task instances and cleanup their Redis streams."""
        # Copy keys to list to avoid "dictionary changed size during iteration"
        task_ids = list(cls._task_registry.keys())
        cleanup_tasks = []
        for task_id in task_ids:
            task = cls._task_registry.get(task_id)
            if task:
                task.cancel()
                if task._runner:
                    await task._runner.destroy()
                # Schedule Redis cleanup (non-blocking)
                cleanup_tasks.append(task._cleanup_redis_streams())

        cls._task_registry.clear()

        # Await all cleanup tasks concurrently
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    def __repr__(self) -> str:
        """String representation of the task."""
        return f"RedisStreamTask(id={self._id}, done={self.done})"
