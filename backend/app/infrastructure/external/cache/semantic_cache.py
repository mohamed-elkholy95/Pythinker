"""Semantic Cache for LLM Responses.

Caches LLM responses based on semantic similarity of prompts, not exact matches.
This enables cache hits for similar but not identical queries, significantly
reducing LLM API costs and latency.

Architecture:
- Uses Qdrant for similarity search on prompt embeddings
- Uses Redis for response storage with TTL
- Configurable similarity threshold (default 0.92)

Usage:
    cache = SemanticCache(
        embedding_client=embedding_client,
        redis_cache=redis_cache,
        qdrant_storage=qdrant_storage,
    )

    # Check cache before LLM call
    cached = await cache.get(prompt, context_hash)
    if cached:
        return cached

    # Call LLM
    response = await llm.ask(prompt)

    # Store in cache
    await cache.set(prompt, response, context_hash)
"""

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import models

from app.infrastructure.external.cache.circuit_breaker import (
    get_circuit_breaker,
)

logger = logging.getLogger(__name__)


@dataclass
class SemanticCacheConfig:
    """Configuration for semantic cache."""

    similarity_threshold: float = 0.92
    """Minimum cosine similarity for cache hit (0-1)."""

    ttl_seconds: int = 3600
    """Time-to-live for cached responses (1 hour default)."""

    collection_name: str = "semantic_cache"
    """Qdrant collection name for prompt embeddings."""

    max_prompt_length: int = 4000
    """Maximum prompt length to cache (chars)."""

    max_response_length: int = 16000
    """Maximum response length to cache (chars)."""

    enabled: bool = True
    """Whether caching is enabled."""


@dataclass
class CacheEntry:
    """A cached response entry."""

    cache_id: str
    prompt_hash: str
    context_hash: str
    response: str
    model: str
    created_at: float
    hit_count: int = 0
    token_savings: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cache_id": self.cache_id,
            "prompt_hash": self.prompt_hash,
            "context_hash": self.context_hash,
            "response": self.response,
            "model": self.model,
            "created_at": self.created_at,
            "hit_count": self.hit_count,
            "token_savings": self.token_savings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CacheEntry":
        return cls(
            cache_id=data["cache_id"],
            prompt_hash=data["prompt_hash"],
            context_hash=data["context_hash"],
            response=data["response"],
            model=data.get("model", "unknown"),
            created_at=data.get("created_at", time.time()),
            hit_count=data.get("hit_count", 0),
            token_savings=data.get("token_savings", 0),
        )


@dataclass
class SemanticCacheStats:
    """Statistics for semantic cache performance."""

    hits: int = 0
    misses: int = 0
    stores: int = 0
    evictions: int = 0
    errors: int = 0
    total_token_savings: int = 0
    avg_similarity_score: float = 0.0
    _similarity_scores: list[float] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def record_hit(self, similarity: float, token_savings: int = 0) -> None:
        self.hits += 1
        self.total_token_savings += token_savings
        self._similarity_scores.append(similarity)
        if len(self._similarity_scores) > 100:
            self._similarity_scores.pop(0)
        self.avg_similarity_score = sum(self._similarity_scores) / len(self._similarity_scores)

    def record_miss(self) -> None:
        self.misses += 1

    def record_store(self) -> None:
        self.stores += 1

    def record_error(self) -> None:
        self.errors += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "stores": self.stores,
            "evictions": self.evictions,
            "errors": self.errors,
            "hit_rate": round(self.hit_rate, 4),
            "total_token_savings": self.total_token_savings,
            "avg_similarity_score": round(self.avg_similarity_score, 4),
        }


class SemanticCache:
    """Semantic cache for LLM responses using embedding similarity.

    Stores prompt embeddings in Qdrant for similarity search and
    cached responses in Redis with TTL-based expiration.
    """

    def __init__(
        self,
        embedding_client,
        redis_cache,
        qdrant_storage,
        config: SemanticCacheConfig | None = None,
    ):
        """Initialize semantic cache.

        Args:
            embedding_client: Client for generating embeddings (must have embed method)
            redis_cache: Redis cache instance for response storage
            qdrant_storage: Qdrant storage instance for similarity search
            config: Cache configuration
        """
        self._embedding_client = embedding_client
        self._redis_cache = redis_cache
        self._qdrant = qdrant_storage
        self._config = config or SemanticCacheConfig()
        self._stats = SemanticCacheStats()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the cache (create Qdrant collection if needed)."""
        if self._initialized:
            return

        try:
            # Ensure Qdrant collection exists
            collections = await self._qdrant.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self._config.collection_name not in collection_names:
                await self._qdrant.client.create_collection(
                    collection_name=self._config.collection_name,
                    vectors_config=models.VectorParams(
                        size=1536,  # OpenAI embedding dimension
                        distance=models.Distance.COSINE,
                    ),
                )
                logger.info(f"Created semantic cache collection: {self._config.collection_name}")

            self._initialized = True
            logger.info("Semantic cache initialized")
        except Exception as e:
            logger.error(f"Failed to initialize semantic cache: {e}")
            raise

    async def get(
        self,
        prompt: str,
        context_hash: str = "",
        model: str = "",
    ) -> str | None:
        """Get cached response for a semantically similar prompt.

        Args:
            prompt: The user prompt/query
            context_hash: Hash of the context (conversation history, system prompt)
            model: Model name (optional, for filtering)

        Returns:
            Cached response string or None if not found
        """
        if not self._config.enabled:
            return None

        # Phase 6: Check circuit breaker
        circuit_breaker = get_circuit_breaker()
        if not circuit_breaker.is_cache_allowed():
            logger.debug(f"Cache bypassed due to circuit breaker state: {circuit_breaker.state.value}")
            self._record_prometheus_query("bypassed")
            return None

        if len(prompt) > self._config.max_prompt_length:
            logger.debug("Prompt too long for cache")
            return None

        try:
            # Generate embedding for the prompt
            embedding = await self._generate_embedding(prompt)
            if embedding is None:
                self._stats.record_miss()
                get_circuit_breaker().record_request(hit=False)
                self._record_prometheus_query("miss")
                return None

            # Search Qdrant for similar prompts
            search_results = await self._qdrant.client.search(
                collection_name=self._config.collection_name,
                query_vector=embedding,
                limit=5,
                score_threshold=self._config.similarity_threshold,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="context_hash",
                            match=models.MatchValue(value=context_hash),
                        ),
                    ]
                )
                if context_hash
                else None,
            )

            if not search_results:
                self._stats.record_miss()
                get_circuit_breaker().record_request(hit=False)
                self._record_prometheus_query("miss")
                return None

            # Get the best match
            best_match = search_results[0]
            cache_id = best_match.payload.get("cache_id")
            similarity = best_match.score

            # Retrieve response from Redis
            cache_key = f"semantic_cache:{cache_id}"
            cached_data = await self._redis_cache.get(cache_key)

            if cached_data is None:
                # Entry in Qdrant but not in Redis (expired)
                self._stats.record_miss()
                get_circuit_breaker().record_request(hit=False)
                self._record_prometheus_query("miss")
                # Clean up orphaned Qdrant entry
                await self._qdrant.client.delete(
                    collection_name=self._config.collection_name,
                    points_selector=models.PointIdsList(points=[cache_id]),
                )
                return None

            entry = CacheEntry.from_dict(cached_data)

            # Update hit count
            entry.hit_count += 1
            await self._redis_cache.set(
                cache_key,
                entry.to_dict(),
                ttl=self._config.ttl_seconds,
            )

            # Estimate token savings (rough: 4 chars per token)
            token_savings = len(entry.response) // 4
            self._stats.record_hit(similarity, token_savings)
            get_circuit_breaker().record_request(hit=True)
            self._record_prometheus_query("hit")

            logger.debug(
                f"Semantic cache hit (similarity={similarity:.3f})",
                extra={"cache_id": cache_id, "similarity": similarity},
            )

            return entry.response

        except Exception as e:
            logger.warning(f"Semantic cache get error: {e}")
            self._stats.record_error()
            self._record_prometheus_query("error")
            return None

    async def set(
        self,
        prompt: str,
        response: str,
        context_hash: str = "",
        model: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store a response in the semantic cache.

        Args:
            prompt: The user prompt/query
            response: The LLM response to cache
            context_hash: Hash of the context
            model: Model name
            metadata: Additional metadata to store

        Returns:
            True if stored successfully
        """
        if not self._config.enabled:
            return False

        if len(prompt) > self._config.max_prompt_length:
            return False

        if len(response) > self._config.max_response_length:
            return False

        try:
            # Generate embedding for the prompt
            embedding = await self._generate_embedding(prompt)
            if embedding is None:
                return False

            # Generate unique cache ID
            cache_id = str(uuid.uuid4())
            prompt_hash = self._hash_text(prompt)

            # Create cache entry
            entry = CacheEntry(
                cache_id=cache_id,
                prompt_hash=prompt_hash,
                context_hash=context_hash,
                response=response,
                model=model,
                created_at=time.time(),
            )

            # Store in Redis
            cache_key = f"semantic_cache:{cache_id}"
            await self._redis_cache.set(
                cache_key,
                entry.to_dict(),
                ttl=self._config.ttl_seconds,
            )

            # Store embedding in Qdrant
            await self._qdrant.client.upsert(
                collection_name=self._config.collection_name,
                points=[
                    models.PointStruct(
                        id=cache_id,
                        vector=embedding,
                        payload={
                            "cache_id": cache_id,
                            "prompt_hash": prompt_hash,
                            "context_hash": context_hash,
                            "model": model,
                            "created_at": entry.created_at,
                            **(metadata or {}),
                        },
                    )
                ],
            )

            self._stats.record_store()
            logger.debug(f"Stored in semantic cache: {cache_id}")

            # Record Prometheus metrics for successful store
            try:
                from app.infrastructure.observability.prometheus_metrics import (
                    semantic_cache_store_total,
                )

                semantic_cache_store_total.inc({"success": "true"})
            except Exception:
                logger.debug("Failed to record semantic cache store metrics", exc_info=True)

            return True

        except Exception as e:
            logger.warning(f"Semantic cache set error: {e}")
            self._stats.record_error()

            # Record Prometheus metrics for failed store
            try:
                from app.infrastructure.observability.prometheus_metrics import (
                    semantic_cache_store_total,
                )

                semantic_cache_store_total.inc({"success": "false"})
            except Exception:
                logger.debug("Failed to record semantic cache store failure metrics", exc_info=True)

            return False

    async def invalidate(self, context_hash: str) -> int:
        """Invalidate all cache entries for a context.

        Args:
            context_hash: The context hash to invalidate

        Returns:
            Number of entries invalidated
        """
        try:
            # Find all entries with this context hash
            results = await self._qdrant.client.scroll(
                collection_name=self._config.collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="context_hash",
                            match=models.MatchValue(value=context_hash),
                        ),
                    ]
                ),
                limit=1000,
            )

            if not results or not results[0]:
                return 0

            points = results[0]
            cache_ids = [p.id for p in points]

            # Delete from Redis
            for cache_id in cache_ids:
                await self._redis_cache.delete(f"semantic_cache:{cache_id}")

            # Delete from Qdrant
            await self._qdrant.client.delete(
                collection_name=self._config.collection_name,
                points_selector=models.PointIdsList(points=cache_ids),
            )

            self._stats.evictions += len(cache_ids)
            logger.info(f"Invalidated {len(cache_ids)} semantic cache entries")
            return len(cache_ids)

        except Exception as e:
            logger.warning(f"Semantic cache invalidate error: {e}")
            return 0

    async def _generate_embedding(self, text: str) -> list[float] | None:
        """Generate embedding for text."""
        try:
            # Use the embedding client to generate embedding
            return await self._embedding_client.embed(text)
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")
            return None

    def _hash_text(self, text: str) -> str:
        """Generate a hash for text content."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    @property
    def stats(self) -> SemanticCacheStats:
        """Get cache statistics."""
        return self._stats

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics as dictionary."""
        return self._stats.to_dict()

    def _record_prometheus_query(self, result: str) -> None:
        """Record cache query to Prometheus metrics.

        Args:
            result: Query result ("hit", "miss", "error", "bypassed")
        """
        try:
            from app.infrastructure.observability.prometheus_metrics import (
                semantic_cache_circuit_breaker_state,
                semantic_cache_hit_rate,
                semantic_cache_hit_total,
                semantic_cache_miss_total,
                semantic_cache_query_total,
            )

            # Record query result
            semantic_cache_query_total.inc({"result": result})

            if result == "hit":
                semantic_cache_hit_total.inc({})
            elif result == "miss":
                semantic_cache_miss_total.inc({})

            # Update circuit breaker metrics
            circuit_breaker = get_circuit_breaker()
            semantic_cache_circuit_breaker_state.set({}, circuit_breaker.state_numeric)

            # Update hit rate gauge using circuit breaker as single source of truth
            cb_metrics = circuit_breaker.get_metrics()
            if cb_metrics["current_hit_rate"] is not None:
                semantic_cache_hit_rate.set({}, cb_metrics["current_hit_rate"])

        except Exception as e:
            # Don't fail cache operations due to metrics errors
            logger.debug(f"Failed to record Prometheus metrics: {e}")


# Global semantic cache instance
_semantic_cache: SemanticCache | None = None


async def get_semantic_cache() -> SemanticCache | None:
    """Get the global semantic cache instance.

    Returns None if not configured or dependencies unavailable.
    """
    global _semantic_cache

    if _semantic_cache is not None:
        return _semantic_cache

    try:
        from app.core.config import get_settings

        settings = get_settings()

        if not settings.semantic_cache_enabled:
            return None

        # Get dependencies
        from app.infrastructure.external.cache.redis_cache import RedisCache
        from app.infrastructure.external.embedding.client import get_embedding_client
        from app.infrastructure.storage.qdrant import get_qdrant

        redis_cache = RedisCache()
        qdrant_storage = get_qdrant()
        embedding_client = get_embedding_client()

        config = SemanticCacheConfig(
            similarity_threshold=settings.semantic_cache_threshold,
            ttl_seconds=settings.semantic_cache_ttl_seconds,
        )

        _semantic_cache = SemanticCache(
            embedding_client=embedding_client,
            redis_cache=redis_cache,
            qdrant_storage=qdrant_storage,
            config=config,
        )

        await _semantic_cache.initialize()
        return _semantic_cache

    except Exception as e:
        logger.warning(f"Failed to initialize semantic cache: {e}")
        return None
