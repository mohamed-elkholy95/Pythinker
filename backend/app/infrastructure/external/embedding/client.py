"""Shared embedding client for vector generation.

Provides a singleton embedding client used by both MemoryService
and SemanticCache. Wraps OpenAI's embedding API with fallback support.
Includes Redis-based embedding cache to avoid redundant API calls.
"""

import hashlib
import json
import logging
import threading
import time
from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.external.http_pool import HTTPClientPool
from app.infrastructure.external.key_pool import (
    APIKeyConfig,
    APIKeyPool,
    RotationStrategy,
)

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Client for generating text embeddings via OpenAI-compatible API.

    Used by both MemoryService and SemanticCache to generate vector
    embeddings for text content. Supports multi-key rotation with
    ROUND_ROBIN strategy for load distribution.
    """

    def __init__(
        self,
        api_key: str,
        fallback_api_keys: list[str] | None = None,
        redis_client=None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "text-embedding-3-small",
        timeout: float = 30.0,
    ):
        """Initialize embedding client.

        Args:
            api_key: Primary OpenAI API key
            fallback_api_keys: Optional list of fallback API keys (up to 2 fallbacks = 3 total)
            redis_client: Redis client for distributed key coordination
            base_url: API base URL
            model: Embedding model name
            timeout: Request timeout
        """
        # Build key configs (primary + up to 2 fallbacks)
        all_keys = [api_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)

        key_configs = [APIKeyConfig(key=k, priority=i) for i, k in enumerate(all_keys) if k and k.strip()]

        # Initialize key pool with ROUND_ROBIN strategy (load distribution)
        self._key_pool = APIKeyPool(
            provider="openai_embedding",
            keys=key_configs,
            redis_client=redis_client,
            strategy=RotationStrategy.ROUND_ROBIN,  # ROUND_ROBIN, not FAILOVER!
        )

        # Set max retries to prevent unbounded recursion
        self._max_retries = len(key_configs)

        self._model = model
        self._dimension = 1536  # text-embedding-3-small dimension
        self.api_base = base_url
        self.timeout = timeout
        self._redis_client = redis_client
        self._cache_ttl = 86400  # 24 hours — embeddings are deterministic per model

        logger.info(f"Embedding client initialized with {len(key_configs)} API key(s) using ROUND_ROBIN strategy")

    async def get_api_key(self) -> str | None:
        """Get the currently active API key from pool (round-robin distribution).

        Uses wait-for-recovery (MCP Rotator pattern): if all keys are in cooldown,
        waits up to 120s for the soonest-recovering key instead of failing immediately.
        """
        return await self._key_pool.get_healthy_key_or_wait(max_wait_seconds=120.0)

    def _cache_key(self, text: str) -> str:
        """Build a Redis cache key from text content hash + model."""
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        return f"emb:{self._model}:{content_hash}"

    async def _get_cached(self, keys: list[str]) -> dict[str, list[float]]:
        """Fetch cached embeddings from Redis. Returns {cache_key: vector}."""
        if not self._redis_client:
            return {}
        try:
            raw_redis = self._redis_client.client if hasattr(self._redis_client, "client") else self._redis_client
            pipe = raw_redis.pipeline(transaction=False)
            for k in keys:
                pipe.get(k)
            results = await pipe.execute()
            cached = {}
            for k, val in zip(keys, results, strict=False):
                if val is not None:
                    cached[k] = json.loads(val)
            return cached
        except Exception as e:
            logger.warning("Embedding cache read failed (degraded to uncached): %s", e)
            return {}

    async def _set_cached(self, items: dict[str, list[float]]) -> None:
        """Store embeddings in Redis with TTL."""
        if not self._redis_client or not items:
            return
        try:
            raw_redis = self._redis_client.client if hasattr(self._redis_client, "client") else self._redis_client
            pipe = raw_redis.pipeline(transaction=False)
            for k, vec in items.items():
                pipe.set(k, json.dumps(vec), ex=self._cache_ttl)
            await pipe.execute()
        except Exception as e:
            logger.warning("Embedding cache write failed (non-critical): %s", e)

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Delegates to embed_batch() so every call benefits from
        HTTPClientPool connection reuse and APIKeyPool rotation.

        Args:
            text: Text to embed (truncated to 8000 chars)

        Returns:
            Embedding vector (1536 dimensions)

        Raises:
            Exception: If embedding API call fails
        """
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str], _attempt: int = 0) -> list[list[float]]:
        """Generate embeddings for multiple texts with automatic key rotation.

        Uses Redis cache to skip API calls for previously-embedded content.

        Args:
            texts: List of texts to embed
            _attempt: Internal retry counter

        Returns:
            List of embedding vectors

        Raises:
            RuntimeError: If all API keys are exhausted
        """
        if not texts:
            return []

        # --- Cache lookup: resolve already-embedded texts ---
        truncated = [t[:8000] for t in texts]
        cache_keys = [self._cache_key(t) for t in truncated]
        cached = await self._get_cached(cache_keys)

        # Build result array — None for cache misses
        results: list[list[float] | None] = [cached.get(ck) for ck in cache_keys]
        miss_indices = [i for i, r in enumerate(results) if r is None]

        if not miss_indices:
            return results  # type: ignore[return-value]  # all hits

        # --- API call for cache misses only ---
        miss_texts = [truncated[i] for i in miss_indices]

        # Check retry limit
        if _attempt >= self._max_retries:
            raise RuntimeError(
                f"All {len(self._key_pool.keys)} OpenAI embedding keys exhausted after {_attempt} attempts"
            )

        # Get healthy key from pool (round-robin)
        key = await self.get_api_key()
        if not key:
            raise RuntimeError(f"All {len(self._key_pool.keys)} OpenAI embedding keys exhausted")

        try:
            import httpx as _httpx  # Only for exception types

            # Reuse pooled connection — per-request Authorization (key rotates)
            client = await HTTPClientPool.get_client(
                "openai-embedding",
                base_url=self.api_base,
                timeout=self.timeout,
            )
            response = await client.post(
                "/embeddings",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": miss_texts,
                    "model": self._model,
                    "encoding_format": "float",
                },
            )

            # Check for rate limit/auth errors
            if response.status_code in (401, 429, 402, 403):
                body = response.text[:200] if hasattr(response, "text") else ""
                await self._key_pool.handle_error(key, status_code=response.status_code, body_text=body)
                return await self.embed_batch(texts, _attempt=_attempt + 1)

            response.raise_for_status()
            data = response.json()

            # Sort by index to maintain order
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            self._key_pool.record_success(key)
            api_embeddings = [d["embedding"] for d in sorted_data]

            # --- Merge API results + populate cache ---
            to_cache: dict[str, list[float]] = {}
            for idx_in_miss, orig_idx in enumerate(miss_indices):
                vec = api_embeddings[idx_in_miss]
                results[orig_idx] = vec
                to_cache[cache_keys[orig_idx]] = vec

            await self._set_cached(to_cache)

            return results  # type: ignore[return-value]

        except _httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 429, 402, 403):
                body = e.response.text[:200] if hasattr(e.response, "text") else ""
                await self._key_pool.handle_error(key, status_code=e.response.status_code, body_text=body)
                return await self.embed_batch(texts, _attempt=_attempt + 1)
            raise

        except (_httpx.TimeoutException, _httpx.ConnectError, _httpx.ReadError, _httpx.RemoteProtocolError):
            # Connection-level failures: rotate key and let caller retry.
            # Log at warning (not error) since these are transient network issues.
            logger.warning("Embedding network error (key %s), rotating", key[:8] if key else "?")
            await self._key_pool.handle_error(key, is_network_error=True)
            raise

        except Exception as e:
            logger.error("Embedding generation failed: %s", e)
            raise

    def _parse_rate_limit_ttl(self, headers: dict) -> int:
        """Parse X-RateLimit-Reset header to get TTL.

        Args:
            headers: Response headers

        Returns:
            TTL in seconds (default: 60 if header missing)
        """
        reset_time = headers.get("x-ratelimit-reset-requests") or headers.get("x-ratelimit-reset")
        if reset_time:
            try:
                # Parse Unix timestamp and calculate seconds until reset
                reset_timestamp = float(reset_time)
                now = time.time()
                return max(int(reset_timestamp - now), 60)  # At least 60 seconds
            except ValueError:
                logger.warning(f"Failed to parse X-RateLimit-Reset: {reset_time}")

        return 60  # Default: 1 minute TTL

    @property
    def model(self) -> str:
        """Get the embedding model name."""
        return self._model

    @property
    def dimension(self) -> int:
        """Get the embedding dimension."""
        return self._dimension


_get_embedding_client_init_lock = threading.Lock()


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    """Get the singleton embedding client.

    Uses settings for API key, base URL, and model configuration.
    Supports up to 3 API keys for round-robin load distribution.

    Returns:
        Configured EmbeddingClient instance

    Raises:
        RuntimeError: If no embedding API key is configured
    """
    with _get_embedding_client_init_lock:
        from app.infrastructure.storage.redis import get_redis

        settings = get_settings()
        api_key = settings.embedding_api_key or settings.api_key

        if not api_key:
            raise RuntimeError("No embedding API key configured. Set EMBEDDING_API_KEY or API_KEY.")

        # Collect fallback keys
        fallback_keys = []
        if settings.embedding_api_key_2:
            fallback_keys.append(settings.embedding_api_key_2)
        if settings.embedding_api_key_3:
            fallback_keys.append(settings.embedding_api_key_3)

        # Get Redis client for distributed coordination
        redis_client = get_redis()

        return EmbeddingClient(
            api_key=api_key,
            fallback_api_keys=fallback_keys or None,
            redis_client=redis_client,
            base_url=settings.embedding_api_base,
            model=settings.embedding_model,
        )
