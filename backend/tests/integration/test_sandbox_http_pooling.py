"""Integration tests for DockerSandbox HTTP connection pooling.

Tests that DockerSandbox properly uses HTTPClientPool for connection reuse.
"""

import pytest

from app.infrastructure.external.http_pool import HTTPClientPool
from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox


@pytest.fixture(autouse=True)
async def cleanup_pool():
    """Clean up HTTP pool after each test."""
    yield
    await HTTPClientPool.close_all()


@pytest.mark.asyncio
async def test_docker_sandbox_creates_pooled_client():
    """Test that DockerSandbox creates a client in the pool."""
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="test-sandbox")

    # Get client - should create pool entry
    client = await sandbox.get_client()

    assert client is not None
    assert sandbox._pool_client_name in HTTPClientPool.get_client_names()


@pytest.mark.asyncio
async def test_docker_sandbox_reuses_client():
    """Test that multiple get_client() calls return the same client."""
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="test-sandbox")

    client1 = await sandbox.get_client()
    client2 = await sandbox.get_client()

    # Should be the same client instance
    assert client1 is client2


@pytest.mark.asyncio
async def test_multiple_sandboxes_different_clients():
    """Test that different sandboxes get different pooled clients."""
    sandbox1 = DockerSandbox(ip="127.0.0.1", container_name="sandbox-1")
    sandbox2 = DockerSandbox(ip="127.0.0.2", container_name="sandbox-2")

    client1 = await sandbox1.get_client()
    client2 = await sandbox2.get_client()

    # Should be different clients (different IPs, different base URLs)
    assert client1 is not client2
    assert len(HTTPClientPool.get_client_names()) == 2


@pytest.mark.asyncio
async def test_sandbox_destroy_closes_pool_client():
    """Test that sandbox.destroy() closes the pool client."""
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="test-sandbox")

    # Create client
    await sandbox.get_client()

    assert sandbox._pool_client_name in HTTPClientPool.get_client_names()

    # Destroy sandbox
    await sandbox.destroy()

    # Client should be removed from pool
    assert sandbox._pool_client_name not in HTTPClientPool.get_client_names()


@pytest.mark.asyncio
async def test_sandbox_client_config():
    """Test that sandbox client has correct configuration."""
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="test-sandbox")

    client = await sandbox.get_client()

    # Verify config
    assert client.config.timeout == 600.0
    assert client.config.connect_timeout == 10.0
    assert client.config.read_timeout == 600.0
    assert client.config.max_connections == 10
    assert client.config.max_keepalive_connections == 5
    assert client.config.keepalive_expiry == 30.0


@pytest.mark.asyncio
async def test_sandbox_http2_feature_flag(monkeypatch):
    """Test that HTTP/2 is controlled by feature flag."""
    from app.core.config import get_settings

    # Test with HTTP/2 disabled (default)
    settings = get_settings()
    assert settings.sandbox_http2_enabled is False

    sandbox1 = DockerSandbox(ip="127.0.0.1", container_name="sandbox-1")
    client1 = await sandbox1.get_client()
    assert client1.config.http2 is False

    await HTTPClientPool.close_all()

    # Test with HTTP/2 enabled - monkeypatch the settings instance
    settings_instance = get_settings()
    monkeypatch.setattr(settings_instance, "sandbox_http2_enabled", True)

    sandbox2 = DockerSandbox(ip="127.0.0.2", container_name="sandbox-2")
    client2 = await sandbox2.get_client()
    assert client2.config.http2 is True


@pytest.mark.asyncio
async def test_pool_stats_after_sandbox_operations():
    """Test that pool stats are updated after sandbox operations."""
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="test-sandbox")

    await sandbox.get_client()

    stats = HTTPClientPool.get_all_stats()

    assert sandbox._pool_client_name in stats
    assert stats[sandbox._pool_client_name]["closed"] is False


@pytest.mark.asyncio
async def test_concurrent_sandbox_client_access():
    """Test concurrent access to same sandbox's client."""
    import asyncio

    sandbox = DockerSandbox(ip="127.0.0.1", container_name="test-sandbox")

    async def get_client():
        return await sandbox.get_client()

    # Multiple concurrent accesses
    tasks = [get_client() for _ in range(10)]
    clients = await asyncio.gather(*tasks)

    # All should be the same client
    assert all(c is clients[0] for c in clients)
    # Only one pool entry
    assert len([n for n in HTTPClientPool.get_client_names() if "sandbox" in n]) == 1


@pytest.mark.asyncio
async def test_sandbox_pool_client_name_format():
    """Test that sandbox pool client name follows expected format."""
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="my-sandbox-123")

    expected_name = f"sandbox-{sandbox.id}"
    assert sandbox._pool_client_name == expected_name


@pytest.mark.asyncio
async def test_connection_reuse_reduces_overhead():
    """Test that connection pooling reduces TCP handshake overhead.

    This is a conceptual test - actual performance measurement would require
    a real sandbox API endpoint and timing measurements.
    """
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="test-sandbox")

    # First call - creates connection
    client1 = await sandbox.get_client()

    # Second call - reuses connection
    client2 = await sandbox.get_client()

    # Both should use the same underlying connection pool
    assert client1 is client2
    assert client1.stats.requests_total == 0  # No requests yet
