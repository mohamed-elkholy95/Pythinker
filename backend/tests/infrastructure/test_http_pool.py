"""Unit tests for HTTPClientPool.

Tests connection pooling, reuse, lifecycle management, and metrics integration.
"""

import asyncio

import pytest

from app.infrastructure.external.http_pool import (
    HTTPClientConfig,
    HTTPClientPool,
    ManagedHTTPClient,
)


@pytest.fixture(autouse=True)
async def cleanup_pool():
    """Clean up HTTP pool after each test."""
    yield
    await HTTPClientPool.close_all()


@pytest.mark.asyncio
async def test_get_client_creates_new_client():
    """Test that get_client creates a new client on first call."""
    client = await HTTPClientPool.get_client(
        name="test-service",
        base_url="http://example.com",
        timeout=10.0,
    )

    assert client is not None
    assert isinstance(client, ManagedHTTPClient)
    assert client.name == "test-service"
    assert not client._closed


@pytest.mark.asyncio
async def test_get_client_reuses_existing_client():
    """Test that get_client returns the same client for same name."""
    client1 = await HTTPClientPool.get_client(
        name="test-service",
        base_url="http://example.com",
    )

    client2 = await HTTPClientPool.get_client(
        name="test-service",
        base_url="http://example.com",
    )

    assert client1 is client2


@pytest.mark.asyncio
async def test_get_client_different_names():
    """Test that different names create different clients."""
    client1 = await HTTPClientPool.get_client(
        name="service-1",
        base_url="http://example1.com",
    )

    client2 = await HTTPClientPool.get_client(
        name="service-2",
        base_url="http://example2.com",
    )

    assert client1 is not client2
    assert client1.name == "service-1"
    assert client2.name == "service-2"


@pytest.mark.asyncio
async def test_get_client_with_custom_config():
    """Test get_client with custom HTTPClientConfig."""
    config = HTTPClientConfig(
        base_url="http://example.com",
        timeout=5.0,
        connect_timeout=2.0,
        max_connections=50,
        max_keepalive_connections=10,
        http2=True,
    )

    client = await HTTPClientPool.get_client(
        name="test-service",
        config=config,
    )

    assert client.config.timeout == 5.0
    assert client.config.connect_timeout == 2.0
    assert client.config.max_connections == 50
    assert client.config.http2 is True


@pytest.mark.asyncio
async def test_close_client():
    """Test closing a specific client."""
    await HTTPClientPool.get_client(
        name="test-service",
        base_url="http://example.com",
    )

    closed = await HTTPClientPool.close_client("test-service")

    assert closed is True

    # Verify client was removed
    assert "test-service" not in HTTPClientPool.get_client_names()


@pytest.mark.asyncio
async def test_close_nonexistent_client():
    """Test closing a client that doesn't exist."""
    closed = await HTTPClientPool.close_client("nonexistent")

    assert closed is False


@pytest.mark.asyncio
async def test_close_all():
    """Test closing all clients."""
    await HTTPClientPool.get_client("service-1", "http://example1.com")
    await HTTPClientPool.get_client("service-2", "http://example2.com")
    await HTTPClientPool.get_client("service-3", "http://example3.com")

    count = await HTTPClientPool.close_all()

    assert count == 3
    assert len(HTTPClientPool.get_client_names()) == 0


@pytest.mark.asyncio
async def test_get_client_names():
    """Test getting list of all client names."""
    await HTTPClientPool.get_client("service-1", "http://example1.com")
    await HTTPClientPool.get_client("service-2", "http://example2.com")

    names = HTTPClientPool.get_client_names()

    assert len(names) == 2
    assert "service-1" in names
    assert "service-2" in names


@pytest.mark.asyncio
async def test_get_all_stats():
    """Test getting stats for all clients."""
    await HTTPClientPool.get_client("service-1", "http://example1.com")
    await HTTPClientPool.get_client("service-2", "http://example2.com")

    stats = HTTPClientPool.get_all_stats()

    assert len(stats) == 2
    assert "service-1" in stats
    assert "service-2" in stats
    assert stats["service-1"]["requests_total"] == 0


@pytest.mark.asyncio
async def test_client_stats_tracking():
    """Test that client stats are tracked correctly."""
    client = await HTTPClientPool.get_client(
        name="test-service",
        base_url="http://example.com",
    )

    # Initial stats
    assert client.stats.requests_total == 0
    assert client.stats.requests_successful == 0
    assert client.stats.requests_failed == 0

    # Note: Actual HTTP requests require a mock server or mocking
    # This is a basic structure test


@pytest.mark.asyncio
async def test_client_recreated_after_close():
    """Test that client can be recreated after being closed."""
    client1 = await HTTPClientPool.get_client(
        name="test-service",
        base_url="http://example.com",
    )

    await HTTPClientPool.close_client("test-service")

    client2 = await HTTPClientPool.get_client(
        name="test-service",
        base_url="http://example.com",
    )

    assert client2 is not None
    assert client2 is not client1  # Different instance


@pytest.mark.asyncio
async def test_concurrent_client_access():
    """Test thread-safe concurrent access to pool."""

    async def get_client():
        return await HTTPClientPool.get_client(
            name="shared-service",
            base_url="http://example.com",
        )

    # Create 10 concurrent tasks
    tasks = [get_client() for _ in range(10)]
    clients = await asyncio.gather(*tasks)

    # All should be the same instance
    assert all(c is clients[0] for c in clients)
    assert len(HTTPClientPool.get_client_names()) == 1


@pytest.mark.asyncio
async def test_http_client_config_defaults():
    """Test HTTPClientConfig default values."""
    config = HTTPClientConfig()

    assert config.timeout == 30.0
    assert config.connect_timeout == 10.0
    assert config.max_connections == 100
    assert config.max_keepalive_connections == 20
    assert config.verify_ssl is True
    assert config.http2 is False
    assert config.max_retries == 3


@pytest.mark.asyncio
async def test_managed_client_http_methods():
    """Test that ManagedHTTPClient exposes HTTP methods."""
    client = await HTTPClientPool.get_client(
        name="test-service",
        base_url="http://example.com",
    )

    # Check methods exist
    assert hasattr(client, "get")
    assert hasattr(client, "post")
    assert hasattr(client, "put")
    assert hasattr(client, "delete")
    assert hasattr(client, "request")


@pytest.mark.asyncio
async def test_client_lifecycle_in_lifespan():
    """Test that clients can be properly managed in FastAPI lifespan."""
    # Simulate lifespan startup
    await HTTPClientPool.get_client("service-1", "http://example1.com")
    await HTTPClientPool.get_client("service-2", "http://example2.com")

    assert len(HTTPClientPool.get_client_names()) == 2

    # Simulate lifespan shutdown
    count = await HTTPClientPool.close_all()

    assert count == 2
    assert len(HTTPClientPool.get_client_names()) == 0


@pytest.mark.asyncio
async def test_is_closed_property():
    """Test that is_closed property works correctly."""
    client = await HTTPClientPool.get_client("test-service", "http://example.com")

    assert client.is_closed is False

    await client.close()

    assert client.is_closed is True


@pytest.mark.asyncio
async def test_pool_max_size_lru_eviction():
    """Test that pool enforces maximum size with LRU eviction."""
    # Create clients up to the limit
    max_size = HTTPClientPool._max_pool_size

    # Create max_size clients
    for i in range(max_size):
        await HTTPClientPool.get_client(f"service-{i}", f"http://example{i}.com")

    assert len(HTTPClientPool.get_client_names()) == max_size

    # Create one more - should evict the first one (service-0)
    await HTTPClientPool.get_client("service-overflow", "http://overflow.com")

    # Pool size should still be at max
    assert len(HTTPClientPool.get_client_names()) == max_size

    # First client should have been evicted
    assert "service-0" not in HTTPClientPool.get_client_names()

    # New client should exist
    assert "service-overflow" in HTTPClientPool.get_client_names()


@pytest.mark.asyncio
async def test_thread_safe_stats_updates():
    """Test that concurrent stats updates don't lose counts."""
    import asyncio

    client = await HTTPClientPool.get_client("test-service", "http://example.com")

    # Simulate concurrent access to stats (would cause race conditions without locking)
    async def increment_stats():
        async with client._stats_lock:
            client.stats.requests_total += 1

    # Run 100 concurrent increments
    tasks = [increment_stats() for _ in range(100)]
    await asyncio.gather(*tasks)

    # All increments should be accounted for
    assert client.stats.requests_total == 100
