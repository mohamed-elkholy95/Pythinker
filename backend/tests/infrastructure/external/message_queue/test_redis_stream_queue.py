"""Tests for RedisStreamQueue resilience behavior."""

import logging
from typing import Any

import pytest

from app.infrastructure.external.message_queue import redis_stream_queue
from app.infrastructure.external.message_queue.redis_stream_queue import RedisStreamQueue


class _FakeRedisWrapper:
    def __init__(self, xread_impl) -> None:
        self.client = _FakeRedisClient(xread_impl)

    async def initialize(self) -> None:
        return None


class _FakeRedisClient:
    def __init__(self, xread_impl) -> None:
        self._xread_impl = xread_impl

    async def xread(self, streams: dict[str, str], count: int, block: int | None) -> list[Any]:
        return await self._xread_impl(streams, count, block)


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
