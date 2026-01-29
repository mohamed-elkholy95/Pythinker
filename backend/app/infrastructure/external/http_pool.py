"""HTTP Client Pool for Managed Connections.

Provides centralized HTTP client management with:
- Connection pooling per service
- Automatic retry configuration
- Proper lifecycle management
- Rate limiting support
- Health monitoring

Usage:
    # Get or create a client for a service
    client = await HTTPClientPool.get_client("openai-api")

    # Make requests
    response = await client.get("/v1/models")

    # Cleanup all clients
    await HTTPClientPool.close_all()
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class HTTPClientConfig:
    """Configuration for an HTTP client."""

    base_url: str | None = None
    timeout: float = 30.0
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    write_timeout: float = 30.0
    pool_timeout: float = 10.0

    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 5.0

    headers: dict[str, str] = field(default_factory=dict)

    # Retry settings
    max_retries: int = 3
    retry_statuses: tuple = (429, 500, 502, 503, 504)

    # SSL/TLS
    verify_ssl: bool = True

    # HTTP/2 support
    http2: bool = False


@dataclass
class ClientStats:
    """Statistics for an HTTP client."""

    requests_total: int = 0
    requests_successful: int = 0
    requests_failed: int = 0
    retries_total: int = 0
    total_response_time_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.requests_total == 0:
            return 1.0
        return self.requests_successful / self.requests_total

    @property
    def avg_response_time_ms(self) -> float:
        if self.requests_successful == 0:
            return 0.0
        return self.total_response_time_ms / self.requests_successful


class ManagedHTTPClient:
    """A managed HTTP client with stats and lifecycle."""

    def __init__(
        self,
        name: str,
        client: httpx.AsyncClient,
        config: HTTPClientConfig,
    ):
        self.name = name
        self.client = client
        self.config = config
        self.stats = ClientStats()
        self._closed = False

    async def request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """Make an HTTP request with stats tracking."""
        import time

        self.stats.requests_total += 1
        start_time = time.perf_counter()

        try:
            response = await self.client.request(method, url, **kwargs)

            # Track successful response
            response_time = (time.perf_counter() - start_time) * 1000
            self.stats.requests_successful += 1
            self.stats.total_response_time_ms += response_time

            return response

        except Exception as e:
            self.stats.requests_failed += 1
            logger.warning(
                f"HTTP request failed for {self.name}: {method} {url} - {e}"
            )
            raise

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """HTTP GET request."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """HTTP POST request."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        """HTTP PUT request."""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        """HTTP DELETE request."""
        return await self.request("DELETE", url, **kwargs)

    async def close(self) -> None:
        """Close the client."""
        if not self._closed:
            await self.client.aclose()
            self._closed = True
            logger.debug(f"Closed HTTP client: {self.name}")

    def get_stats(self) -> dict[str, Any]:
        """Get client statistics."""
        return {
            "name": self.name,
            "requests_total": self.stats.requests_total,
            "requests_successful": self.stats.requests_successful,
            "requests_failed": self.stats.requests_failed,
            "success_rate": round(self.stats.success_rate, 4),
            "avg_response_time_ms": round(self.stats.avg_response_time_ms, 2),
            "retries_total": self.stats.retries_total,
            "closed": self._closed,
        }


class HTTPClientPool:
    """Pool of managed HTTP clients for different services."""

    _clients: dict[str, ManagedHTTPClient] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def get_client(
        cls,
        name: str,
        base_url: str | None = None,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        config: HTTPClientConfig | None = None,
        **kwargs
    ) -> ManagedHTTPClient:
        """Get or create an HTTP client for a service.

        Args:
            name: Unique name for this client
            base_url: Base URL for requests
            timeout: Request timeout in seconds
            headers: Default headers
            config: Full configuration (overrides other params)
            **kwargs: Additional httpx.AsyncClient arguments

        Returns:
            ManagedHTTPClient instance
        """
        async with cls._lock:
            if name in cls._clients:
                client = cls._clients[name]
                if not client._closed:
                    return client
                # Client was closed, remove and recreate
                del cls._clients[name]

            # Build config
            if config is None:
                config = HTTPClientConfig(
                    base_url=base_url,
                    timeout=timeout,
                    headers=headers or {},
                )

            # Build timeout config
            timeout_config = httpx.Timeout(
                connect=config.connect_timeout,
                read=config.read_timeout,
                write=config.write_timeout,
                pool=config.pool_timeout,
            )

            # Build limits config
            limits = httpx.Limits(
                max_connections=config.max_connections,
                max_keepalive_connections=config.max_keepalive_connections,
                keepalive_expiry=config.keepalive_expiry,
            )

            # Create httpx client
            httpx_client = httpx.AsyncClient(
                base_url=config.base_url or "",
                timeout=timeout_config,
                limits=limits,
                headers=config.headers,
                verify=config.verify_ssl,
                http2=config.http2,
                **kwargs
            )

            # Wrap in managed client
            managed = ManagedHTTPClient(name, httpx_client, config)
            cls._clients[name] = managed

            logger.info(
                f"Created HTTP client: {name}",
                extra={"client": name, "base_url": config.base_url}
            )

            return managed

    @classmethod
    async def close_client(cls, name: str) -> bool:
        """Close a specific client.

        Args:
            name: Client name

        Returns:
            True if client was found and closed
        """
        async with cls._lock:
            if name in cls._clients:
                await cls._clients[name].close()
                del cls._clients[name]
                return True
            return False

    @classmethod
    async def close_all(cls) -> int:
        """Close all HTTP clients.

        Returns:
            Number of clients closed
        """
        async with cls._lock:
            count = len(cls._clients)

            close_tasks = [
                client.close()
                for client in cls._clients.values()
            ]

            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)

            cls._clients.clear()
            logger.info(f"Closed {count} HTTP clients")
            return count

    @classmethod
    def get_all_stats(cls) -> dict[str, dict[str, Any]]:
        """Get statistics for all clients."""
        return {
            name: client.get_stats()
            for name, client in cls._clients.items()
        }

    @classmethod
    def get_client_names(cls) -> list:
        """Get list of all client names."""
        return list(cls._clients.keys())


# Convenience function
async def get_http_client(
    name: str,
    base_url: str | None = None,
    **kwargs
) -> ManagedHTTPClient:
    """Get or create an HTTP client.

    Convenience wrapper for HTTPClientPool.get_client.
    """
    return await HTTPClientPool.get_client(name, base_url, **kwargs)
