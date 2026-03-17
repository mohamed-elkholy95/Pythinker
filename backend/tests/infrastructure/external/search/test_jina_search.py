"""Integration tests for JinaSearchEngine with APIKeyPool."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.infrastructure.external.search.jina_search import JinaSearchEngine


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    return redis


JINA_SUCCESS_RESPONSE = {
    "code": 200,
    "status": 20000,
    "data": [
        {
            "title": "Jina AI - Search Foundation",
            "url": "https://jina.ai/",
            "content": "Jina AI provides search foundation APIs for enterprise and agent workloads.",
        },
        {
            "title": "Reader by Jina AI",
            "url": "https://github.com/jina-ai/reader",
            "description": "Convert URL and search results into LLM-friendly content.",
        },
    ],
}


def _make_mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.text = str(data)
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()
    return mock


async def test_jina_uses_key_pool_rotation(mock_redis):
    """Jina should use APIKeyPool for multi-key rotation."""
    engine = JinaSearchEngine(
        api_key="key1",
        fallback_api_keys=["key2", "key3"],
        redis_client=mock_redis,
    )

    assert engine._key_pool is not None
    assert len(engine._key_pool.keys) == 3

    from app.infrastructure.external.key_pool import RotationStrategy

    assert engine._key_pool.strategy == RotationStrategy.FAILOVER


@pytest.mark.asyncio
async def test_jina_search_success(mock_redis, mocker):
    """Successful Jina search should return parsed results."""
    engine = JinaSearchEngine(api_key="test-key", redis_client=mock_redis)

    mock_response = _make_mock_response(JINA_SUCCESS_RESPONSE)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search("jina search foundation")

    assert result.success is True
    assert result.data is not None
    assert result.data.total_results == 2
    assert result.data.results[0].title == "Jina AI - Search Foundation"
    assert result.data.results[0].link == "https://jina.ai/"

    headers = mock_client.post.await_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["Accept"] == "application/json"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_jina_respects_retry_limit(mock_redis, mocker):
    """Search should not recurse infinitely when all keys are exhausted."""
    engine = JinaSearchEngine(
        api_key="key1",
        fallback_api_keys=["key2", "key3"],
        redis_client=mock_redis,
    )

    mock_response = _make_mock_response({"message": "Unauthorized"}, status_code=401)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search("test query")

    assert result.success is False
    assert "exhausted after" in (result.message or "")
    assert mock_client.post.call_count == 3


@pytest.mark.asyncio
async def test_jina_rotates_on_401(mock_redis, mocker):
    """Search should rotate keys when first key is unauthorized."""
    engine = JinaSearchEngine(
        api_key="bad-key",
        fallback_api_keys=["good-key"],
        redis_client=mock_redis,
    )

    fail_response = _make_mock_response({"message": "Unauthorized"}, status_code=401)
    ok_response = _make_mock_response(JINA_SUCCESS_RESPONSE)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=[fail_response, ok_response])
    mock_client.is_closed = False

    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search("test query")

    assert result.success is True
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_jina_empty_query_returns_error(mock_redis):
    """Empty query after sanitization should return error."""
    engine = JinaSearchEngine(api_key="test-key", redis_client=mock_redis)

    result = await engine.search("   ")

    assert result.success is False
    assert "empty search query" in (result.message or "")


@pytest.mark.asyncio
async def test_jina_works_without_redis():
    """JinaSearchEngine should work in-memory mode without Redis."""
    engine = JinaSearchEngine(
        api_key="test-key-1",
        fallback_api_keys=["test-key-2"],
        redis_client=None,
    )

    key = await engine._key_pool.get_healthy_key()
    assert key == "test-key-1"
    # Pool works in-memory without Redis; lazy _ensure_redis() may connect later
    assert engine._key_pool is not None
