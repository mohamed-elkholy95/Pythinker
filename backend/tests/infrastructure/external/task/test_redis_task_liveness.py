"""Tests for Redis task liveness signal.

The liveness key stores task_id at task:liveness:{session_id} in Redis
with a 30s TTL, heartbeated every 10s, cleared in finally.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.external.task.redis_task import (
    _LIVENESS_KEY_PREFIX,
    _LIVENESS_TTL_SECONDS,
    RedisStreamTask,
)


@pytest.fixture
def mock_redis_client():
    """Mock raw redis.asyncio.Redis client."""
    client = AsyncMock()
    client.set = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.delete = AsyncMock(return_value=1)
    return client


@pytest.fixture
def mock_runner():
    """Mock task runner. AgentTaskRunner._session_id is private;
    we expose it via the new session_id property added in this task."""
    runner = AsyncMock()
    runner.session_id = "test-session-123"

    async def run_briefly(task):
        await asyncio.sleep(0.05)

    runner.run = run_briefly
    runner.on_done = AsyncMock()
    return runner


class TestLivenessKeyLifecycle:
    """Verify SET on start, heartbeat refresh, DELETE on completion."""

    @pytest.mark.asyncio
    async def test_liveness_key_set_on_task_run(self, mock_runner, mock_redis_client):
        """Liveness key should be SET when _execute_task begins."""
        with patch("app.infrastructure.storage.redis.get_redis") as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            task = RedisStreamTask(mock_runner)
            await task.run()
            # Wait for completion + cleanup
            await asyncio.sleep(0.2)

            set_calls = [
                c
                for c in mock_redis_client.set.call_args_list
                if str(c).find(f"{_LIVENESS_KEY_PREFIX}test-session-123") >= 0
            ]
            assert len(set_calls) >= 1, "Liveness key must be SET on task start"

    @pytest.mark.asyncio
    async def test_liveness_key_value_is_task_id(self, mock_runner, mock_redis_client):
        """Liveness key value must be the task_id (not boolean)."""
        with patch("app.infrastructure.storage.redis.get_redis") as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            task = RedisStreamTask(mock_runner)
            task_id = task.id
            await task.run()
            await asyncio.sleep(0.2)

            set_calls = [
                c
                for c in mock_redis_client.set.call_args_list
                if str(c).find(f"{_LIVENESS_KEY_PREFIX}test-session-123") >= 0
            ]
            assert len(set_calls) >= 1
            # Positional arg [0][1] or kwarg 'value' should be the task_id
            first_call = set_calls[0]
            value = first_call[0][1] if len(first_call[0]) > 1 else first_call[1].get("value")
            assert value == task_id

    @pytest.mark.asyncio
    async def test_liveness_key_has_30s_ttl(self, mock_runner, mock_redis_client):
        """SET must include ex=30 for crash-safety TTL."""
        with patch("app.infrastructure.storage.redis.get_redis") as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            task = RedisStreamTask(mock_runner)
            await task.run()
            await asyncio.sleep(0.2)

            set_calls = [
                c
                for c in mock_redis_client.set.call_args_list
                if str(c).find(f"{_LIVENESS_KEY_PREFIX}test-session-123") >= 0
            ]
            assert len(set_calls) >= 1
            assert set_calls[0][1].get("ex") == _LIVENESS_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_liveness_key_deleted_on_task_done(self, mock_runner, mock_redis_client):
        """Liveness key must be DELETEd when the task completes (finally block)."""
        with patch("app.infrastructure.storage.redis.get_redis") as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            task = RedisStreamTask(mock_runner)
            await task.run()
            await asyncio.sleep(0.3)

            delete_calls = [
                c
                for c in mock_redis_client.delete.call_args_list
                if str(c).find(f"{_LIVENESS_KEY_PREFIX}test-session-123") >= 0
            ]
            assert len(delete_calls) >= 1, "Liveness key must be deleted on completion"

    @pytest.mark.asyncio
    async def test_liveness_key_deleted_on_exception(self, mock_runner, mock_redis_client):
        """Liveness key must be DELETEd even when runner.run() raises."""

        async def failing_run(task):
            raise RuntimeError("boom")

        mock_runner.run = failing_run

        with patch("app.infrastructure.storage.redis.get_redis") as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            task = RedisStreamTask(mock_runner)
            await task.run()
            await asyncio.sleep(0.2)

            delete_calls = [
                c
                for c in mock_redis_client.delete.call_args_list
                if str(c).find(f"{_LIVENESS_KEY_PREFIX}test-session-123") >= 0
            ]
            assert len(delete_calls) >= 1, "Liveness key must be deleted on exception"


class TestGetLiveness:
    """Verify the classmethod that reads the liveness key."""

    @pytest.mark.asyncio
    async def test_returns_task_id_when_key_exists(self, mock_redis_client):
        """get_liveness should return the task_id string when key exists."""
        mock_redis_client.get = AsyncMock(return_value=b"task-uuid-abc123")
        with patch("app.infrastructure.storage.redis.get_redis") as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            result = await RedisStreamTask.get_liveness("sess-xyz")
            assert result == "task-uuid-abc123"
            mock_redis_client.get.assert_called_once_with(f"{_LIVENESS_KEY_PREFIX}sess-xyz")

    @pytest.mark.asyncio
    async def test_returns_none_when_key_missing(self, mock_redis_client):
        """get_liveness should return None when no liveness key exists."""
        mock_redis_client.get = AsyncMock(return_value=None)
        with patch("app.infrastructure.storage.redis.get_redis") as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            result = await RedisStreamTask.get_liveness("sess-gone")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_error(self, mock_redis_client):
        """get_liveness must not raise on Redis failures."""
        mock_redis_client.get = AsyncMock(side_effect=ConnectionError("down"))
        with patch("app.infrastructure.storage.redis.get_redis") as mock_get_redis:
            mock_get_redis.return_value.client = mock_redis_client
            result = await RedisStreamTask.get_liveness("sess-err")
            assert result is None
