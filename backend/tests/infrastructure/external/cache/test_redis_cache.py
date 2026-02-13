"""Tests for RedisCache pattern operations."""

from collections.abc import Iterable
from typing import Any

import pytest

from app.infrastructure.external.cache import redis_cache as redis_cache_module
from app.infrastructure.external.cache.redis_cache import RedisCache


class _FakeRedisClient:
    def __init__(self, scan_responses: list[tuple[int | str, list[str]]], unlink_raises: bool = False):
        self._scan_responses = scan_responses
        self._scan_index = 0
        self.unlink_raises = unlink_raises
        self.scan_calls: list[dict[str, Any]] = []
        self.unlink_calls: list[list[str]] = []
        self.delete_calls: list[list[str]] = []

    async def scan(self, cursor: int | str, match: str, count: int) -> tuple[int | str, list[str]]:
        self.scan_calls.append({"cursor": cursor, "match": match, "count": count})
        response = self._scan_responses[self._scan_index]
        self._scan_index += 1
        return response

    async def unlink(self, *keys: str) -> int:
        self.unlink_calls.append(list(keys))
        if self.unlink_raises:
            raise RuntimeError("UNLINK unavailable")
        return len(keys)

    async def delete(self, *keys: str) -> int:
        self.delete_calls.append(list(keys))
        return len(keys)


class _FakeRedisWrapper:
    def __init__(self, client: _FakeRedisClient):
        self.client = client

    async def initialize(self) -> None:
        return None

    async def call(self, method_name: str, *args: Any, **kwargs: Any):
        method = getattr(self.client, method_name)
        return await method(*args, **kwargs)


class _Settings:
    redis_scan_count = 2


def _as_flat(items: Iterable[list[str]]) -> list[str]:
    result: list[str] = []
    for sub in items:
        result.extend(sub)
    return result


@pytest.mark.asyncio
async def test_keys_uses_scan_and_collects_all_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient(
        scan_responses=[
            (1, ["cache:a", "cache:b"]),
            (0, ["cache:c"]),
        ]
    )

    monkeypatch.setattr(redis_cache_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(redis_cache_module, "get_cache_redis", lambda: _FakeRedisWrapper(client))

    cache = RedisCache()
    keys = await cache.keys("cache:*")

    assert keys == ["cache:a", "cache:b", "cache:c"]
    assert len(client.scan_calls) == 2
    assert all(call["match"] == "cache:*" for call in client.scan_calls)
    assert all(call["count"] == 2 for call in client.scan_calls)


@pytest.mark.asyncio
async def test_clear_pattern_falls_back_to_delete_when_unlink_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient(
        scan_responses=[
            (1, ["cache:a", "cache:b"]),
            (0, ["cache:c"]),
        ],
        unlink_raises=True,
    )

    monkeypatch.setattr(redis_cache_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(redis_cache_module, "get_cache_redis", lambda: _FakeRedisWrapper(client))

    cache = RedisCache()
    deleted = await cache.clear_pattern("cache:*")

    assert deleted == 3
    assert _as_flat(client.unlink_calls) == ["cache:a", "cache:b", "cache:c"]
    assert _as_flat(client.delete_calls) == ["cache:a", "cache:b", "cache:c"]
