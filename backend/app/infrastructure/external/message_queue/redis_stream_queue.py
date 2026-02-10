import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from app.domain.external.message_queue import MessageQueue
from app.infrastructure.storage.redis import get_redis

logger = logging.getLogger(__name__)


class RedisStreamQueue(MessageQueue):
    """Redis Stream implementation of message queue"""

    def __init__(self, stream_name: str):
        self._stream_name = stream_name
        self._redis = get_redis()
        self._lock_expire_seconds = 10  # Lock expiration time
        self._invalid_stream_id_warning_emitted = False

    async def _ensure_initialized(self) -> None:
        """Ensure Redis client is initialized before use."""
        await self._redis.initialize()

    async def _acquire_lock(self, lock_key: str, timeout_seconds: int = 5) -> str | None:
        """Acquire distributed lock

        Args:
            lock_key: Lock key name
            timeout_seconds: Timeout in seconds for acquiring lock

        Returns:
            str: Lock value if acquired successfully, None otherwise
        """
        await self._ensure_initialized()
        lock_value = str(uuid.uuid4())
        end_time = timeout_seconds

        while end_time > 0:
            # Use SET with NX and EX for atomic lock acquisition
            result = await self._redis.client.set(
                lock_key,
                lock_value,
                nx=True,  # Only set if key doesn't exist
                ex=self._lock_expire_seconds,  # Set expiration time
            )

            if result:
                return lock_value

            # Wait a bit before retrying
            await asyncio.sleep(0.1)
            end_time -= 0.1

        return None

    async def _release_lock(self, lock_key: str, lock_value: str) -> bool:
        """Release distributed lock

        Args:
            lock_key: Lock key name
            lock_value: Lock value for verification

        Returns:
            bool: True if lock released successfully, False otherwise
        """
        await self._ensure_initialized()
        # Lua script for atomic lock release
        release_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """

        try:
            script = self._redis.client.register_script(release_script)
            result = await script(keys=[lock_key], args=[lock_value])
            return result == 1
        except Exception:
            return False

    async def put(self, message: Any) -> str:
        """Add a message to the stream

        Args:
            message: Message to be sent

        Returns:
            str: Message ID
        """
        await self._ensure_initialized()
        logger.debug(f"Putting message into stream ({self._stream_name}): {message}")
        return await self._redis.client.xadd(self._stream_name, {"data": message})

    # Maximum block time to stay below Redis socket timeout (30s default)
    MAX_BLOCK_MS = 25000  # 25 seconds - safe margin below socket timeout

    @staticmethod
    def _normalize_start_id(start_id: str | None) -> str:
        """Normalize stream cursor to Redis-compatible IDs.

        Redis stream IDs must include `-` (e.g. `0-0`) unless using special `$`.
        """
        if start_id is None:
            return "0-0"

        normalized = start_id.strip()
        if not normalized:
            return "0-0"
        if normalized == "$":
            return "$"
        if normalized == "0":
            return "0-0"
        if "-" in normalized:
            return normalized
        return "0-0"

    async def get(self, start_id: str = "0", block_ms: int | None = None) -> tuple[str, Any]:
        """Get a message from the stream with bounded blocking.

        Args:
            start_id: Message ID to start reading from, defaults to "0" meaning from the earliest message
            block_ms: Block time in milliseconds. Capped at MAX_BLOCK_MS (25s) to stay
                      below socket timeout. Use None for no blocking.

        Returns:
            Tuple[str, Any]: (Message ID, Message content), returns (None, None) if no message
        """
        await self._ensure_initialized()
        normalized_start_id = self._normalize_start_id(start_id)
        logger.debug(f"Getting message from stream ({self._stream_name}): {normalized_start_id}")

        # Cap block_ms to stay well below socket timeout (30s)
        # This prevents "Timeout reading from redis" errors
        effective_block_ms = block_ms
        if block_ms is not None and block_ms > self.MAX_BLOCK_MS:
            logger.debug(f"Capping xread block time from {block_ms}ms to {self.MAX_BLOCK_MS}ms")
            effective_block_ms = self.MAX_BLOCK_MS

        # Read new messages
        try:
            messages = await self._redis.client.xread(
                {self._stream_name: normalized_start_id},
                count=1,
                block=effective_block_ms,
            )
        except TimeoutError:
            logger.debug(f"xread timed out for stream {self._stream_name}")
            return None, None
        except Exception as e:
            error_text = str(e)
            if "Invalid stream ID specified as stream command argument" in error_text:
                if not self._invalid_stream_id_warning_emitted:
                    logger.warning(f"xread error for stream {self._stream_name}: {error_text}")
                    self._invalid_stream_id_warning_emitted = True
                else:
                    logger.debug(f"xread invalid stream id repeated for stream {self._stream_name}: {error_text}")
                return None, None

            logger.warning(f"xread error for stream {self._stream_name}: {error_text}")
            return None, None

        if not messages:
            return None, None

        # Get message ID and data
        stream_messages = messages[0][1]
        if not stream_messages:
            return None, None

        message_id, message_data = stream_messages[0]

        try:
            # Try both bytes and string keys for compatibility
            return message_id, message_data.get("data")
        except (KeyError, json.JSONDecodeError):
            return None, None

    async def get_range(
        self, start_id: str = "-", end_id: str = "+", count: int = 100
    ) -> AsyncGenerator[tuple[str, Any], None]:
        """Get messages within a specified range

        Args:
            start_id: Start ID, defaults to "-" meaning the earliest message
            end_id: End ID, defaults to "+" meaning the latest message
            count: Maximum number of messages to return

        Yields:
            Tuple[str, Any]: (Message ID, Message content)
        """
        await self._ensure_initialized()
        messages = await self._redis.client.xrange(self._stream_name, start_id, end_id, count=count)

        if not messages:
            return

        for message_id, message_data in messages:
            try:
                # Try both bytes and string keys for compatibility
                data = message_data.get("data")
                yield message_id, data
            except (KeyError, json.JSONDecodeError):
                continue

    async def get_latest_id(self) -> str:
        """Get the latest message ID

        Returns:
            str: Latest message ID, returns "0" if no messages
        """
        await self._ensure_initialized()
        messages = await self._redis.client.xrevrange(self._stream_name, "+", "-", count=1)
        if not messages:
            return "0"
        return messages[0][0]

    async def clear(self) -> None:
        """Clear all messages from the stream"""
        await self._ensure_initialized()
        await self._redis.client.xtrim(self._stream_name, 0)

    async def is_empty(self) -> bool:
        """Check if the stream is empty"""
        return await self.size() == 0

    async def size(self) -> int:
        """Get the number of messages in the stream"""
        await self._ensure_initialized()
        return await self._redis.client.xlen(self._stream_name)

    async def delete_message(self, message_id: str) -> bool:
        """Delete a specific message from the stream

        Args:
            message_id: ID of the message to delete

        Returns:
            bool: True if message was deleted successfully, False otherwise
        """
        await self._ensure_initialized()
        try:
            await self._redis.client.xdel(self._stream_name, message_id)
            return True
        except Exception:
            return False

    async def pop(self) -> tuple[str, Any]:
        """Get and remove the first message from the stream using distributed lock

        Returns:
            Tuple[str, Any]: (Message ID, Message content), returns (None, None) if stream is empty
        """
        await self._ensure_initialized()
        logger.debug(f"Popping message from stream ({self._stream_name})")
        lock_key = f"lock:{self._stream_name}:pop"

        # Acquire distributed lock
        lock_value = await self._acquire_lock(lock_key)
        if not lock_value:
            return None, None

        try:
            # Get the first message from stream
            messages = await self._redis.client.xrange(self._stream_name, "-", "+", count=1)

            if not messages:
                return None, None

            message_id, message_data = messages[0]

            # Delete the message from stream
            await self._redis.client.xdel(self._stream_name, message_id)

            try:
                # Try both bytes and string keys for compatibility
                return message_id, message_data.get("data")
            except (KeyError, json.JSONDecodeError):
                logger.exception(f"Error parsing message from stream ({self._stream_name}): {message_data}")
                return None, None

        finally:
            # Always release the lock
            await self._release_lock(lock_key, lock_value)
