"""Redis-backed implementation of the TaskOutputRelay protocol.

Delegates liveness checks to ``RedisStreamTask.get_liveness`` and output
streaming to a per-task ``RedisStreamQueue``.
"""

from __future__ import annotations

from typing import Any

from app.infrastructure.external.message_queue.redis_stream_queue import RedisStreamQueue
from app.infrastructure.external.task.redis_task import RedisStreamTask


class RedisTaskOutputRelay:
    """Concrete :class:`~app.domain.external.task_output_relay.TaskOutputRelay`
    backed by Redis streams and liveness keys."""

    async def get_live_task_id(self, session_id: str) -> str | None:
        """Check whether a background task is alive for *session_id*."""
        return await RedisStreamTask.get_liveness(session_id)

    async def get_task_output(
        self,
        task_id: str,
        start_id: str | None = None,
        block_ms: int | None = None,
    ) -> tuple[str | None, Any]:
        """Read the next output message from the Redis output stream."""
        stream = RedisStreamQueue(f"task:output:{task_id}")
        return await stream.get(start_id=start_id or "0", block_ms=block_ms)
