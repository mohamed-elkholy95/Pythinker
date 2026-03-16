"""Tests for SerperSearchEngine.search_shopping() — Serper Shopping API integration."""

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.infrastructure.external.search.serper_search import SerperSearchEngine, ShoppingResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client for testing (in-memory fallback still works without it)."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def engine(mock_redis) -> SerperSearchEngine:
    """SerperSearchEngine with a single test key and mocked Redis."""
    return SerperSearchEngine(
        api_key="test-key-1",
        fallback_api_keys=["test-key-2"],
        redis_client=mock_redis,
    )


def _make_mock_response(body: dict, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response from a dict payload."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.text = json.dumps(body)
    mock_resp.json = MagicMock(return_value=body)
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _make_mock_client(response: MagicMock) -> AsyncMock:
    """Build a mock httpx.AsyncClient that always returns *response* from .post()."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=response)
    client.is_closed = False
    return client


# ---------------------------------------------------------------------------
# ShoppingResult dataclass
# ---------------------------------------------------------------------------


def test_shopping_result_defaults():
    """ShoppingResult has sensible defaults for optional fields."""
    result = ShoppingResult(
        title="Sony WH-1000XM5",
        source="Best Buy",
        price=278.00,
        link="https://www.bestbuy.com/product/123",
    )

    assert result.rating == 0.0
    assert result.rating_count == 0
    assert result.product_id == ""
    assert result.image_url == ""
    assert result.position == 0
    assert result.price_raw == ""


def test_shopping_result_full_fields():
    """ShoppingResult stores all fields correctly."""
    result = ShoppingResult(
        title="Sony WH-1000XM5 Headphones",
        source="Amazon",
        price=349.00,
        link="https://www.amazon.com/dp/B09XS7JWHH",
        rating=4.6,
        rating_count=1234,
        product_id="B09XS7JWHH",
        image_url="https://m.media-amazon.com/images/I/product.jpg",
        position=1,
        price_raw="$349.00",
    )

    assert result.title == "Sony WH-1000XM5 Headphones"
    assert result.source == "Amazon"
    assert result.price == 349.00
    assert result.rating == 4.6
    assert result.rating_count == 1234
    assert result.product_id == "B09XS7JWHH"
    assert result.position == 1
    assert result.price_raw == "$349.00"


# ---------------------------------------------------------------------------
# _extract_price_number static method
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "price_raw, expected",
    [
        ("$278.00", 278.0),
        ("$1,299.99", 1299.99),
        ("£499.00", 499.0),
        ("€1.299,99", 1299.99),  # European locale: dot=thousands, comma=decimal
        ("99", 99.0),
        ("Free", 0.0),
        ("", 0.0),
        ("$0.00", 0.0),
        ("1,000", 1000.0),
        ("$2,499.95", 2499.95),
    ],
)
def test_extract_price_number(price_raw: str, expected: float):
    """_extract_price_number correctly converts price strings to floats."""
    result = SerperSearchEngine._extract_price_number(price_raw)
    assert result == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# search_shopping() — structured result parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_shopping_parses_results(engine: SerperSearchEngine, mocker):
    """search_shopping() correctly parses title, source, price, rating from API response."""
    api_response = {
        "shopping": [
            {
                "title": "Sony WH-1000XM5 Wireless Headphones",
                "link": "https://www.bestbuy.com/product/1",
                "source": "Best Buy",
                "price": "$278.00",
                "rating": 4.7,
                "ratingCount": 892,
                "productId": "BB-6505727",
                "imageUrl": "https://pisces.bbystatic.com/image2/BestBuy_US/1.jpg",
                "position": 1,
            },
            {
                "title": "Sony WH-1000XM5 Noise Canceling Headphones",
                "link": "https://www.amazon.com/dp/B09XS7JWHH",
                "source": "Amazon",
                "price": "$349.00",
                "rating": 4.5,
                "ratingCount": 2341,
                "productId": "B09XS7JWHH",
                "imageUrl": "https://m.media-amazon.com/images/I/product.jpg",
                "position": 2,
            },
        ]
    }

    mock_resp = _make_mock_response(api_response)
    mock_client = _make_mock_client(mock_resp)
    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search_shopping("Sony WH-1000XM5")

    assert result.success is True
    assert result.data is not None
    assert len(result.data) == 2

    first = result.data[0]
    assert first.title == "Sony WH-1000XM5 Wireless Headphones"
    assert first.source == "Best Buy"
    assert first.price == pytest.approx(278.0)
    assert first.price_raw == "$278.00"
    assert first.rating == pytest.approx(4.7)
    assert first.rating_count == 892
    assert first.product_id == "BB-6505727"
    assert first.position == 1
    assert "bestbuy.com" in first.link

    second = result.data[1]
    assert second.source == "Amazon"
    assert second.price == pytest.approx(349.0)


@pytest.mark.asyncio
async def test_search_shopping_uses_shopping_endpoint(engine: SerperSearchEngine, mocker):
    """search_shopping() POSTs to /shopping, NOT /search."""
    api_response = {"shopping": []}
    mock_resp = _make_mock_response(api_response)
    mock_client = _make_mock_client(mock_resp)
    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    await engine.search_shopping("test product")

    # Verify the URL used is the shopping endpoint
    call_args = mock_client.post.call_args
    url = call_args[0][0]
    assert url == "https://google.serper.dev/shopping"
    assert "/search" not in url


@pytest.mark.asyncio
async def test_search_shopping_empty_results(engine: SerperSearchEngine, mocker):
    """search_shopping() returns success with empty list when API returns no results."""
    mock_resp = _make_mock_response({"shopping": []})
    mock_client = _make_mock_client(mock_resp)
    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search_shopping("extremely obscure product xyz123")

    assert result.success is True
    assert result.data == []


@pytest.mark.asyncio
async def test_search_shopping_missing_shopping_key(engine: SerperSearchEngine, mocker):
    """search_shopping() handles API response missing the 'shopping' key gracefully."""
    # Some error responses may return non-shopping JSON
    mock_resp = _make_mock_response({"organic": [], "knowledgeGraph": {}})
    mock_client = _make_mock_client(mock_resp)
    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search_shopping("any query")

    assert result.success is True
    assert result.data == []


@pytest.mark.asyncio
async def test_search_shopping_skips_items_without_title_or_link(engine: SerperSearchEngine, mocker):
    """Items missing title or link are silently skipped."""
    api_response = {
        "shopping": [
            # Valid item
            {"title": "Good Product", "link": "https://example.com/1", "source": "Store", "price": "$10.00"},
            # Missing title
            {"link": "https://example.com/2", "source": "Store", "price": "$20.00"},
            # Missing link
            {"title": "No Link Product", "source": "Store", "price": "$30.00"},
            # Both missing
            {"source": "Store", "price": "$40.00"},
        ]
    }
    mock_resp = _make_mock_response(api_response)
    mock_client = _make_mock_client(mock_resp)
    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search_shopping("test")

    assert result.success is True
    assert len(result.data) == 1
    assert result.data[0].title == "Good Product"


@pytest.mark.asyncio
async def test_search_shopping_request_params(engine: SerperSearchEngine, mocker):
    """search_shopping() sends correct JSON body with q, gl, hl, num parameters."""
    mock_resp = _make_mock_response({"shopping": []})
    mock_client = _make_mock_client(mock_resp)
    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    await engine.search_shopping("gaming laptop", num=20)

    call_kwargs = mock_client.post.call_args[1]
    body = call_kwargs["json"]

    assert body["q"] == "gaming laptop"
    assert body["gl"] == "us"
    assert body["hl"] == "en"
    assert body["num"] == 20


# ---------------------------------------------------------------------------
# Key rotation on 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_shopping_rotates_key_on_401(engine: SerperSearchEngine, mocker):
    """search_shopping() rotates to the next key when API returns HTTP 401."""
    # First call → 401, second call → success
    resp_401 = _make_mock_response({}, status_code=401)
    resp_ok = _make_mock_response({"shopping": []})

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=[resp_401, resp_ok])
    mock_client.is_closed = False
    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search_shopping("test product")

    assert result.success is True
    # Should have called post twice (first key failed, second succeeded)
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_search_shopping_exhausts_all_keys(engine: SerperSearchEngine, mocker):
    """search_shopping() returns error when all keys are exhausted (all return 401)."""
    resp_401 = MagicMock(spec=httpx.Response)
    resp_401.status_code = 401
    resp_401.text = "Unauthorized"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=resp_401)
    mock_client.is_closed = False
    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search_shopping("test product")

    assert result.success is False
    assert "exhausted" in result.message

    # engine has 2 keys → should attempt exactly 2 times
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_search_shopping_uses_api_key_header(engine: SerperSearchEngine, mocker):
    """search_shopping() injects X-API-Key header per request (not baked into client)."""
    mock_resp = _make_mock_response({"shopping": []})
    mock_client = _make_mock_client(mock_resp)
    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    await engine.search_shopping("test")

    call_kwargs = mock_client.post.call_args[1]
    assert "X-API-Key" in call_kwargs["headers"]
    assert call_kwargs["headers"]["X-API-Key"] == "test-key-1"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_shopping_timeout(engine: SerperSearchEngine, mocker):
    """search_shopping() returns error on network timeout."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    mock_client.is_closed = False
    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    result = await engine.search_shopping("test product")

    assert result.success is False
    assert "timed out" in result.message.lower()


@pytest.mark.asyncio
async def test_search_shopping_empty_query(engine: SerperSearchEngine):
    """search_shopping() returns error for empty query without hitting the API."""
    result = await engine.search_shopping("   ")

    assert result.success is False
    assert "empty" in result.message.lower()
