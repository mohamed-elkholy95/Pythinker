"""Tests for RedisStreamQueue resilience behavior."""

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.infrastructure.external.message_queue import redis_stream_queue
from app.infrastructure.external.message_queue.redis_stream_queue import RedisStreamQueue


class _FakeRedisWrapper:
    def __init__(self, xread_impl=None, xadd_impl=None) -> None:
        self.client = _FakeRedisClient(xread_impl=xread_impl, xadd_impl=xadd_impl)

    async def initialize(self) -> None:
        return None


class _FakeRedisClient:
    def __init__(self, xread_impl=None, xadd_impl=None) -> None:
        self._xread_impl = xread_impl
        self._xadd_impl = xadd_impl

    async def xread(self, streams: dict[str, str], count: int, block: int | None) -> list[Any]:
        if self._xread_impl is None:
            raise RuntimeError("xread_impl not configured")
        return await self._xread_impl(streams, count, block)

    async def xadd(self, stream_name: str, fields: dict[str, Any], **kwargs: Any) -> str:
        if self._xadd_impl is None:
            raise RuntimeError("xadd_impl not configured")
        return await self._xadd_impl(stream_name, fields, **kwargs)


@pytest.mark.asyncio
async def test_get_normalizes_invalid_start_id_to_safe_cursor(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def _xread(streams: dict[str, str], count: int, block: int | None) -> list[Any]:
        captured["start_id"] = next(iter(streams.values()))
        captured["count"] = count
        captured["block"] = block
        return []

    monkeypatch.setattr(redis_stream_queue, "get_redis", lambda: _FakeRedisWrapper(_xread))
    queue = RedisStreamQueue("test-stream")

    result = await queue.get(start_id="1234567890", block_ms=1000)

    assert result == (None, None)
    assert captured["start_id"] == "0-0"
    assert captured["count"] == 1
    assert captured["block"] == 1000


@pytest.mark.asyncio
async def test_get_caps_block_ms_below_socket_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def _xread(streams: dict[str, str], count: int, block: int | None) -> list[Any]:
        captured["start_id"] = next(iter(streams.values()))
        captured["count"] = count
        captured["block"] = block
        return []

    monkeypatch.setattr(redis_stream_queue, "get_redis", lambda: _FakeRedisWrapper(_xread))
    queue = RedisStreamQueue("test-stream")

    result = await queue.get(start_id="0-0", block_ms=60000)

    assert result == (None, None)
    assert captured["start_id"] == "0-0"
    assert captured["count"] == 1
    assert captured["block"] == queue.MAX_BLOCK_MS


@pytest.mark.asyncio
async def test_get_handles_redis_timeout_without_exception(monkeypatch: pytest.MonkeyPatch):
    async def _xread(streams: dict[str, str], count: int, block: int | None) -> list[Any]:
        raise TimeoutError("Timeout reading from redis socket")

    monkeypatch.setattr(redis_stream_queue, "get_redis", lambda: _FakeRedisWrapper(_xread))
    queue = RedisStreamQueue("test-stream")

    message_id, message = await queue.get(start_id="0-0", block_ms=1000)

    assert message_id is None
    assert message is None


@pytest.mark.asyncio
async def test_get_handles_redis_library_timeout_without_exception(monkeypatch: pytest.MonkeyPatch):
    async def _xread(streams: dict[str, str], count: int, block: int | None) -> list[Any]:
        raise RedisTimeoutError("Timeout reading from redis:6379")

    monkeypatch.setattr(redis_stream_queue, "get_redis", lambda: _FakeRedisWrapper(_xread))
    queue = RedisStreamQueue("test-stream")

    message_id, message = await queue.get(start_id="0-0", block_ms=1000)

    assert message_id is None
    assert message is None


@pytest.mark.asyncio
async def test_get_warns_once_for_repeated_invalid_stream_id_errors(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    async def _xread(streams: dict[str, str], count: int, block: int | None) -> list[Any]:
        raise ValueError("Invalid stream ID specified as stream command argument")

    monkeypatch.setattr(redis_stream_queue, "get_redis", lambda: _FakeRedisWrapper(_xread))
    queue = RedisStreamQueue("test-stream")

    with caplog.at_level(logging.DEBUG):
        result1 = await queue.get(start_id="bad", block_ms=1000)
        result2 = await queue.get(start_id="bad", block_ms=1000)

    assert result1 == (None, None)
    assert result2 == (None, None)
    invalid_id_warnings = [
        record
        for record in caplog.records
        if record.levelno >= logging.WARNING and "Invalid stream ID specified as stream command argument" in record.msg
    ]
    assert len(invalid_id_warnings) == 1


@pytest.mark.asyncio
async def test_put_applies_stream_maxlen_when_configured(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    class _Settings:
        redis_stream_max_len = 123

    async def _xadd(stream_name: str, fields: dict[str, Any], **kwargs: Any) -> str:
        captured["stream_name"] = stream_name
        captured["fields"] = fields
        captured["kwargs"] = kwargs
        return "1-0"

    monkeypatch.setattr(redis_stream_queue, "get_settings", lambda: _Settings())
    monkeypatch.setattr(redis_stream_queue, "get_redis", lambda: _FakeRedisWrapper(xadd_impl=_xadd))

    queue = RedisStreamQueue("test-stream")
    result = await queue.put("hello")

    assert result == "1-0"
    assert captured["stream_name"] == "test-stream"
    assert captured["fields"] == {"data": "hello"}
    assert captured["kwargs"]["maxlen"] == 123
    assert captured["kwargs"]["approximate"] is True


@pytest.mark.asyncio
async def test_put_without_stream_maxlen_uses_plain_xadd(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    class _Settings:
        redis_stream_max_len = 0

    async def _xadd(stream_name: str, fields: dict[str, Any], **kwargs: Any) -> str:
        captured["stream_name"] = stream_name
        captured["fields"] = fields
        captured["kwargs"] = kwargs
        return "1-0"

    monkeypatch.setattr(redis_stream_queue, "get_settings", lambda: _Settings())
    monkeypatch.setattr(redis_stream_queue, "get_redis", lambda: _FakeRedisWrapper(xadd_impl=_xadd))

    queue = RedisStreamQueue("test-stream")
    result = await queue.put("hello")

    assert result == "1-0"
    assert captured["stream_name"] == "test-stream"
    assert captured["fields"] == {"data": "hello"}
    assert captured["kwargs"] == {}


@pytest.mark.asyncio
async def test_pop_renews_lock_during_long_operation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(redis_stream_queue, "get_redis", lambda: _FakeRedisWrapper())
    queue = RedisStreamQueue("test-stream")
    queue._lock_renewal_interval_seconds = 0.01

    monkeypatch.setattr(queue, "_ensure_initialized", AsyncMock(return_value=None))
    monkeypatch.setattr(queue, "_acquire_lock", AsyncMock(return_value="lock-1"))
    release_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(queue, "_release_lock", release_mock)

    renew_calls = 0

    async def _renew(_lock_key: str, _lock_value: str) -> bool:
        nonlocal renew_calls
        renew_calls += 1
        return True

    monkeypatch.setattr(queue, "_renew_lock", _renew)

    async def _xrange(*_args, **_kwargs):
        await asyncio.sleep(0.035)
        return [("1-0", {"data": "payload"})]

    queue._redis.client.xrange = AsyncMock(side_effect=_xrange)
    queue._redis.client.xdel = AsyncMock(return_value=1)

    message_id, payload = await queue.pop()

    assert message_id == "1-0"
    assert payload == "payload"
    assert renew_calls >= 1
    release_mock.assert_awaited_once_with("lock:test-stream:pop", "lock-1")


@pytest.mark.asyncio
async def test_pop_aborts_when_lock_renewal_fails(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(redis_stream_queue, "get_redis", lambda: _FakeRedisWrapper())
    queue = RedisStreamQueue("test-stream")
    queue._lock_renewal_interval_seconds = 0.01

    monkeypatch.setattr(queue, "_ensure_initialized", AsyncMock(return_value=None))
    monkeypatch.setattr(queue, "_acquire_lock", AsyncMock(return_value="lock-2"))
    release_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(queue, "_release_lock", release_mock)

    renew_calls = 0

    async def _renew(_lock_key: str, _lock_value: str) -> bool:
        nonlocal renew_calls
        renew_calls += 1
        return False

    monkeypatch.setattr(queue, "_renew_lock", _renew)

    async def _xrange(*_args, **_kwargs):
        await asyncio.sleep(0.025)
        return [("2-0", {"data": "payload-2"})]

    queue._redis.client.xrange = AsyncMock(side_effect=_xrange)
    queue._redis.client.xdel = AsyncMock(return_value=1)

    message_id, payload = await queue.pop()

    assert message_id is None
    assert payload is None
    assert renew_calls >= 1
    queue._redis.client.xdel.assert_not_awaited()
    release_mock.assert_awaited_once_with("lock:test-stream:pop", "lock-2")
