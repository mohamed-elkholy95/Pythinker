"""Tests for per-provider concurrency bulkhead via asyncio.Semaphore."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.domain.models.search import SearchResultItem
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType

# ---------------------------------------------------------------------------
# Minimal engine that uses the base search() method
# ---------------------------------------------------------------------------


class _SlowSearchEngine(SearchEngineBase):
    """Test engine that records peak concurrent calls."""

    provider_name = "slow_test"
    engine_type = SearchEngineType.API

    def __init__(self, delay: float = 0.1, max_concurrent: int = 2, **kwargs):
        super().__init__(max_concurrent=max_concurrent, **kwargs)
        self._delay = delay
        self._current_concurrent = 0
        self._peak_concurrent = 0

    def _get_date_range_mapping(self) -> dict[str, str]:
        return {}

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        return {"q": query}

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        self._current_concurrent += 1
        self._peak_concurrent = max(self._peak_concurrent, self._current_concurrent)
        await asyncio.sleep(self._delay)
        self._current_concurrent -= 1
        # Return a mock response
        mock_resp = AsyncMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.raise_for_status = lambda: None
        return mock_resp

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        return [], 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semaphore_is_created_with_correct_limit():
    """Semaphore is initialized with the configured max_concurrent value."""
    engine = _SlowSearchEngine(max_concurrent=4)
    sem = engine._semaphore
    assert isinstance(sem, asyncio.Semaphore)
    # The internal counter should be 4 (no tokens consumed yet)
    assert sem._value == 4


@pytest.mark.asyncio
async def test_different_limits_create_different_semaphores():
    """Two engines with different max_concurrent have separate semaphores."""
    eng2 = _SlowSearchEngine(max_concurrent=2)
    eng4 = _SlowSearchEngine(max_concurrent=4)
    assert eng2._semaphore is not eng4._semaphore


@pytest.mark.asyncio
async def test_same_limit_shares_semaphore_within_class():
    """Two instances of same class with same limit share the semaphore."""
    eng_a = _SlowSearchEngine(max_concurrent=3)
    eng_b = _SlowSearchEngine(max_concurrent=3)
    assert eng_a._semaphore is eng_b._semaphore


@pytest.mark.asyncio
async def test_bulkhead_caps_peak_concurrency():
    """Peak concurrent calls must not exceed max_concurrent."""
    engine = _SlowSearchEngine(delay=0.05, max_concurrent=2)
    tasks = [engine.search(f"query {i}") for i in range(6)]
    await asyncio.gather(*tasks, return_exceptions=True)
    assert engine._peak_concurrent <= 2
