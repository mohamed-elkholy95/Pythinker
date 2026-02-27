"""Integration tests for ExaSearchEngine with APIKeyPool."""

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.infrastructure.external.search.exa_search import (
    ExaSearchEngine,
    _date_range_to_iso,
)


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    return redis


EXA_SUCCESS_RESPONSE = {
    "requestId": "abc123",
    "results": [
        {
            "title": "Understanding Neural Search Engines",
            "url": "https://example.com/neural-search",
            "text": "Neural search uses embeddings to find semantically relevant results...",
            "publishedDate": "2026-01-15T10:00:00.000Z",
            "author": "John Doe",
            "id": "https://example.com/neural-search",
        },
        {
            "title": "Exa AI Documentation",
            "url": "https://docs.exa.ai/overview",
            "text": "Exa is a search engine that finds content by meaning...",
            "publishedDate": "2026-02-01T12:00:00.000Z",
            "author": None,
            "id": "https://docs.exa.ai/overview",
        },
    ],
    "searchType": "auto",
    "costDollars": {"total": 0.005},
}


def _make_mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.text = json.dumps(data)
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()
    return mock


async def test_exa_uses_key_pool_rotation(mock_redis):
    """Exa should use APIKeyPool for multi-key rotation."""
    engine = ExaSearchEngine(
        api_key="key1",
        fallback_api_keys=["key2", "key3"],
        redis_client=mock_redis,
    )

    assert engine._key_pool is not None
    assert len(engine._key_pool.keys) == 3

    from app.infrastructure.external.key_pool import RotationStrategy

    assert engine._key_pool.strategy == RotationStrategy.FAILOVER


@pytest.mark.asyncio
async def test_exa_search_success(mock_redis, mocker):
    """Test successful Exa search returns parsed results."""
    engine = ExaSearchEngine(api_key="test-key", redis_client=mock_redis)

    mock_response = _make_mock_response(EXA_SUCCESS_RESPONSE)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search("neural search engines")

    assert result.success is True
    assert result.data.total_results == 2
    assert result.data.results[0].title == "Understanding Neural Search Engines"
    assert result.data.results[0].link == "https://example.com/neural-search"
    assert "Neural search" in result.data.results[0].snippet


@pytest.mark.asyncio
async def test_exa_respects_retry_limit(mock_redis, mocker):
    """Search should not recurse infinitely when all keys are exhausted."""
    engine = ExaSearchEngine(
        api_key="key1",
        fallback_api_keys=["key2", "key3"],
        redis_client=mock_redis,
    )

    mock_response = _make_mock_response({}, status_code=429)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search("test query")

    assert result.success is False
    assert "exhausted after" in result.message
    assert mock_client.post.call_count == 3


@pytest.mark.asyncio
async def test_exa_rotates_on_401(mock_redis, mocker):
    """Search should rotate key on 401 unauthorized and retry."""
    engine = ExaSearchEngine(
        api_key="bad-key",
        fallback_api_keys=["good-key"],
        redis_client=mock_redis,
    )

    # First call returns 401, second returns success
    fail_response = _make_mock_response({"error": "Invalid API key"}, status_code=401)
    ok_response = _make_mock_response(EXA_SUCCESS_RESPONSE)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=[fail_response, ok_response])
    mock_client.is_closed = False

    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search("test query")

    assert result.success is True
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_exa_empty_query_returns_error(mock_redis):
    """Empty query after sanitization should return error without API call."""
    engine = ExaSearchEngine(api_key="test-key", redis_client=mock_redis)

    result = await engine.search("   ")

    assert result.success is False
    assert "empty search query" in result.message


@pytest.mark.asyncio
async def test_exa_works_without_redis():
    """ExaSearchEngine should work in-memory mode without Redis."""
    engine = ExaSearchEngine(
        api_key="test-key-1",
        fallback_api_keys=["test-key-2"],
        redis_client=None,
    )

    key = await engine.api_key
    assert key == "test-key-1"
    assert engine._key_pool._redis is None


def test_date_range_to_iso_past_day():
    """past_day should produce an ISO date string approximately 1 day ago."""
    iso = _date_range_to_iso("past_day")
    assert iso is not None
    assert iso.endswith(".000Z")
    assert "T" in iso


def test_date_range_to_iso_none():
    """None and 'all' should return None."""
    assert _date_range_to_iso(None) is None
    assert _date_range_to_iso("all") is None


def test_date_range_to_iso_unknown():
    """Unknown date range should return None."""
    assert _date_range_to_iso("past_century") is None


def test_parse_response_handles_empty_results():
    """Empty results list should parse without error."""
    engine = ExaSearchEngine(api_key="test-key")
    mock_response = _make_mock_response({"results": [], "requestId": "x"})
    results, total = engine._parse_response(mock_response)
    assert results == []
    assert total == 0


def test_parse_response_skips_items_without_url():
    """Items missing url should be skipped."""
    engine = ExaSearchEngine(api_key="test-key")
    mock_response = _make_mock_response({
        "results": [
            {"title": "No URL", "text": "Some text"},
            {"title": "Has URL", "url": "https://example.com", "text": "Valid"},
        ],
    })
    results, total = engine._parse_response(mock_response)
    assert total == 1
    assert results[0].link == "https://example.com"


def test_build_request_params_includes_date():
    """Date range should be converted to startPublishedDate."""
    engine = ExaSearchEngine(api_key="test-key")
    params = engine._build_request_params("test query", "past_week")
    assert "startPublishedDate" in params
    assert params["query"] == "test query"
    assert params["type"] == "auto"
    assert params["text"] is True


def test_build_request_params_no_date():
    """No date range should omit startPublishedDate."""
    engine = ExaSearchEngine(api_key="test-key")
    params = engine._build_request_params("test query", None)
    assert "startPublishedDate" not in params
