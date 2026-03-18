"""Unit tests for JinaReranker."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.domain.models.search import SearchResultItem
from app.infrastructure.external.search.jina_reranker import JinaReranker


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    return redis


def _make_mock_response(data: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.text = str(data)
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()
    return mock


def _sample_results() -> list[SearchResultItem]:
    return [
        SearchResultItem(title="Result A", link="https://example.com/a", snippet="snippet a"),
        SearchResultItem(title="Result B", link="https://example.com/b", snippet="snippet b"),
        SearchResultItem(title="Result C", link="https://example.com/c", snippet="snippet c"),
    ]


async def test_jina_reranker_uses_key_pool_rotation(mock_redis):
    reranker = JinaReranker(
        api_key="key1",
        fallback_api_keys=["key2", "key3"],
        redis_client=mock_redis,
    )

    assert reranker._key_pool is not None
    assert len(reranker._key_pool.keys) == 3


@pytest.mark.asyncio
async def test_jina_reranker_reorders_top_window(mock_redis, mocker):
    reranker = JinaReranker(api_key="test-key", redis_client=mock_redis)
    mock_response = _make_mock_response(
        {
            "results": [
                {"index": 1, "relevance_score": 0.99},
                {"index": 0, "relevance_score": 0.45},
            ]
        }
    )

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False
    mocker.patch.object(reranker, "_get_client", return_value=mock_client)

    results = _sample_results()
    reranked = await reranker.rerank("query", results, top_n=2)

    assert [item.link for item in reranked] == [
        "https://example.com/b",
        "https://example.com/a",
        "https://example.com/c",
    ]
    headers = mock_client.post.await_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["Accept"] == "application/json"


@pytest.mark.asyncio
async def test_jina_reranker_respects_retry_limit(mock_redis, mocker):
    reranker = JinaReranker(
        api_key="key1",
        fallback_api_keys=["key2", "key3"],
        redis_client=mock_redis,
    )
    mock_response = _make_mock_response({"message": "Unauthorized"}, status_code=401)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False
    mocker.patch.object(reranker, "_get_client", return_value=mock_client)

    results = _sample_results()
    reranked = await reranker.rerank("query", results, top_n=3)

    assert [item.link for item in reranked] == [item.link for item in results]
    assert mock_client.post.call_count == 3


@pytest.mark.asyncio
async def test_jina_reranker_fails_open_on_exception(mock_redis, mocker):
    reranker = JinaReranker(api_key="test-key", redis_client=mock_redis)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=RuntimeError("network boom"))
    mock_client.is_closed = False
    mocker.patch.object(reranker, "_get_client", return_value=mock_client)

    results = _sample_results()
    reranked = await reranker.rerank("query", results, top_n=2)

    assert [item.link for item in reranked] == [item.link for item in results]
