import asyncio
import logging
import uuid
from typing import ClassVar, Optional

from app.domain.external.task import Task, TaskRunner
from app.infrastructure.external.message_queue.redis_stream_queue import MessageQueue, RedisStreamQueue

logger = logging.getLogger(__name__)


class RedisStreamTask(Task):
    """Redis Stream-based task implementation following the Task protocol."""

    _task_registry: ClassVar[dict[str, "RedisStreamTask"]] = {}

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

        Returns:
            bool: True if the task is cancelled, False otherwise
        """
        request_cancellation = getattr(self._runner, "request_cancellation", None)
        if callable(request_cancellation):
            try:
                request_cancellation()
            except Exception as exc:
                logger.debug("Failed to signal cooperative cancellation for task %s: %s", self._id, exc)

        if not self.done:
            self._execution_task.cancel()
            logger.info(f"Task {self._id} cancelled")
            self._cleanup_registry()
            return True

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

    def _on_task_done(self) -> None:
        """Called when the task is done."""
        self._task_done = True
        if self._runner:
            task = asyncio.create_task(self._runner.on_done(self))
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
        """Cleanup Redis streams for this task to prevent memory leak."""
        try:
            await self._input_stream.delete_stream()
            await self._output_stream.delete_stream()
            logger.info(f"Cleaned up Redis streams for task {self._id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup Redis streams for task {self._id}: {e}")

    async def _execute_task(self):
        """Execute the task using the TaskRunner."""
        try:
            await self._runner.run(self)
        except asyncio.CancelledError:
            logger.info(f"Task {self._id} execution cancelled")
        except Exception as e:
            logger.error(f"Task {self._id} execution failed: {e!s}")
        finally:
            self._on_task_done()

    @classmethod
    def get(cls, task_id: str) -> Optional["RedisStreamTask"]:
        """Get a task by its ID.

        Returns:
            Optional[RedisStreamTask]: Task instance if found, None otherwise
        """
        return cls._task_registry.get(task_id)

    @classmethod
    def create(cls, runner: TaskRunner) -> "RedisStreamTask":
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
