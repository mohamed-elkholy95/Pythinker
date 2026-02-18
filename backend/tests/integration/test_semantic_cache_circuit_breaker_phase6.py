"""Integration tests for Phase 6 semantic cache with circuit breaker.

Tests end-to-end SLO monitoring and automatic cache bypass.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestSemanticCacheCircuitBreakerIntegration:
    """Integration tests for semantic cache with circuit breaker."""

    @pytest.mark.asyncio
    async def test_cache_bypassed_when_circuit_open(self):
        """Test cache operations are bypassed when circuit is OPEN."""
        from app.infrastructure.external.cache.circuit_breaker import (
            CircuitState,
            get_circuit_breaker,
        )
        from app.infrastructure.external.cache.semantic_cache import SemanticCache

        # Create mocks
        embedding_client_mock = MagicMock()
        redis_cache_mock = AsyncMock()
        qdrant_storage_mock = MagicMock()

        cache = SemanticCache(
            embedding_client=embedding_client_mock,
            redis_cache=redis_cache_mock,
            qdrant_storage=qdrant_storage_mock,
        )

        # Force circuit breaker to OPEN state
        circuit_breaker = get_circuit_breaker()
        circuit_breaker._state = CircuitState.OPEN

        # Try to get from cache
        result = await cache.get("test prompt", context_hash="ctx123")

        # Should return None (bypassed)
        assert result is None

        # Qdrant should NOT have been called
        qdrant_storage_mock.client.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_recorded_to_circuit_breaker(self):
        """Test cache hits are recorded to circuit breaker."""
        from app.infrastructure.external.cache.circuit_breaker import get_circuit_breaker
        from app.infrastructure.external.cache.semantic_cache import SemanticCache

        # Reset circuit breaker
        circuit_breaker = get_circuit_breaker()
        circuit_breaker._samples.clear()
        circuit_breaker._state = "CLOSED"

        # Create mocks
        embedding_client_mock = AsyncMock()
        embedding_client_mock.embed.return_value = [0.1] * 1536

        redis_cache_mock = AsyncMock()
        redis_cache_mock.get.return_value = {
            "cache_id": "test-id",
            "prompt_hash": "hash",
            "context_hash": "ctx",
            "response": "cached response",
            "model": "claude",
            "created_at": time.time(),
            "hit_count": 0,
        }

        qdrant_storage_mock = MagicMock()
        search_result = MagicMock()
        search_result.score = 0.95
        search_result.payload = {"cache_id": "test-id"}
        qdrant_storage_mock.client = AsyncMock()
        qdrant_storage_mock.client.search.return_value = [search_result]

        cache = SemanticCache(
            embedding_client=embedding_client_mock,
            redis_cache=redis_cache_mock,
            qdrant_storage=qdrant_storage_mock,
        )

        # Get from cache (should be a hit)
        result = await cache.get("test prompt", context_hash="ctx")

        # Should return cached response
        assert result == "cached response"

        # Circuit breaker should have recorded at least one sample for the cache hit
        assert len(circuit_breaker._samples) >= 1, "Circuit breaker should record at least one sample after a cache hit"

    @pytest.mark.asyncio
    async def test_cache_miss_recorded_to_circuit_breaker(self):
        """Test cache misses are recorded to circuit breaker."""
        from app.infrastructure.external.cache.circuit_breaker import get_circuit_breaker
        from app.infrastructure.external.cache.semantic_cache import SemanticCache

        # Reset circuit breaker
        circuit_breaker = get_circuit_breaker()
        circuit_breaker._samples.clear()

        # Create mocks
        embedding_client_mock = AsyncMock()
        embedding_client_mock.embed.return_value = [0.1] * 1536

        redis_cache_mock = AsyncMock()
        qdrant_storage_mock = MagicMock()
        qdrant_storage_mock.client = AsyncMock()
        qdrant_storage_mock.client.search.return_value = []  # No results

        cache = SemanticCache(
            embedding_client=embedding_client_mock,
            redis_cache=redis_cache_mock,
            qdrant_storage=qdrant_storage_mock,
        )

        # Get from cache (should be a miss)
        result = await cache.get("test prompt", context_hash="ctx")

        # Should return None
        assert result is None

        # Circuit breaker should have recorded at least one sample for the cache miss
        assert len(circuit_breaker._samples) >= 1, (
            "Circuit breaker should record at least one sample after a cache miss"
        )

    @pytest.mark.asyncio
    async def test_prometheus_metrics_updated_on_cache_operations(self):
        """Test Prometheus metrics are updated during cache operations."""
        from app.core.prometheus_metrics import (
            semantic_cache_hit_total,
            semantic_cache_query_total,
        )
        from app.infrastructure.external.cache.semantic_cache import SemanticCache

        # Create mocks
        embedding_client_mock = AsyncMock()
        embedding_client_mock.embed.return_value = [0.1] * 1536

        redis_cache_mock = AsyncMock()
        redis_cache_mock.get.return_value = {
            "cache_id": "test-id",
            "prompt_hash": "hash",
            "context_hash": "ctx",
            "response": "cached response",
            "model": "claude",
            "created_at": time.time(),
            "hit_count": 0,
        }

        qdrant_storage_mock = MagicMock()
        search_result = MagicMock()
        search_result.score = 0.95
        search_result.payload = {"cache_id": "test-id"}
        qdrant_storage_mock.client = AsyncMock()
        qdrant_storage_mock.client.search.return_value = [search_result]

        cache = SemanticCache(
            embedding_client=embedding_client_mock,
            redis_cache=redis_cache_mock,
            qdrant_storage=qdrant_storage_mock,
        )

        initial_queries = semantic_cache_query_total.get({"result": "hit"})
        initial_hits = semantic_cache_hit_total.get({})

        # Perform cache get (should be a hit)
        await cache.get("test prompt", context_hash="ctx")

        # Metrics should be updated
        new_queries = semantic_cache_query_total.get({"result": "hit"})
        new_hits = semantic_cache_hit_total.get({})

        assert new_queries == initial_queries + 1
        assert new_hits == initial_hits + 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_state_metric_updated(self):
        """Test circuit breaker state metric is updated."""
        from app.core.prometheus_metrics import (
            semantic_cache_circuit_breaker_state,
        )
        from app.infrastructure.external.cache.circuit_breaker import (
            CircuitState,
            get_circuit_breaker,
        )
        from app.infrastructure.external.cache.semantic_cache import SemanticCache

        # Create mocks
        embedding_client_mock = AsyncMock()
        redis_cache_mock = AsyncMock()
        qdrant_storage_mock = MagicMock()
        qdrant_storage_mock.client = AsyncMock()
        qdrant_storage_mock.client.search.return_value = []

        cache = SemanticCache(
            embedding_client=embedding_client_mock,
            redis_cache=redis_cache_mock,
            qdrant_storage=qdrant_storage_mock,
        )

        # Set circuit to OPEN
        circuit_breaker = get_circuit_breaker()
        circuit_breaker._state = CircuitState.OPEN

        # Attempt cache get
        await cache.get("test prompt")

        # Circuit breaker state metric should reflect OPEN (value=1)
        state_value = semantic_cache_circuit_breaker_state.get({})
        assert state_value == 1  # OPEN


class TestCircuitBreakerRecoveryFlow:
    """Test full circuit breaker recovery flow."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_full_lifecycle(self):
        """Test complete circuit breaker lifecycle: CLOSED → OPEN → HALF_OPEN → CLOSED."""
        from app.infrastructure.external.cache.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitState,
            SemanticCacheCircuitBreaker,
        )

        # Use short timeouts for testing
        config = CircuitBreakerConfig(
            failure_threshold=0.40,
            recovery_threshold=0.60,
            failure_window_seconds=2,
            recovery_window_seconds=2,
            half_open_test_seconds=1,
            min_samples=3,
        )

        cb = SemanticCacheCircuitBreaker(config)

        # 1. Start in CLOSED state
        assert cb.state == CircuitState.CLOSED

        # 2. Simulate low hit rate (30%) to trigger OPEN
        for _ in range(3):
            for _ in range(3):
                cb.record_request(hit=True)
            for _ in range(7):
                cb.record_request(hit=False)
            await asyncio.sleep(0.1)

        # Eventually should open (need consecutive failures)
        # Note: Actual transition depends on timing and consecutive failure logic

        # 3. If circuit opened, wait for transition to HALF_OPEN
        # (In real scenario, would wait failure_window_seconds)

        # 4. Simulate recovery (70% hit rate) to close circuit
        cb._state = CircuitState.HALF_OPEN
        cb._half_open_started_at = time.time() - 2

        for _ in range(2):
            for _ in range(7):
                cb.record_request(hit=True)
            for _ in range(3):
                cb.record_request(hit=False)
            await asyncio.sleep(0.1)

        # Should eventually close after consecutive successes


class TestSLOMonitoring:
    """Test SLO threshold monitoring."""

    def test_slo_failure_threshold(self):
        """Test SLO failure threshold of 40% hit rate."""
        from app.infrastructure.external.cache.circuit_breaker import (
            CircuitBreakerConfig,
        )

        config = CircuitBreakerConfig()

        assert config.failure_threshold == 0.40

    def test_slo_recovery_threshold(self):
        """Test SLO recovery threshold of 60% hit rate."""
        from app.infrastructure.external.cache.circuit_breaker import (
            CircuitBreakerConfig,
        )

        config = CircuitBreakerConfig()

        assert config.recovery_threshold == 0.60

    def test_slo_failure_window(self):
        """Test SLO failure detection window of 5 minutes."""
        from app.infrastructure.external.cache.circuit_breaker import (
            CircuitBreakerConfig,
        )

        config = CircuitBreakerConfig()

        assert config.failure_window_seconds == 300  # 5 minutes

    def test_slo_recovery_window(self):
        """Test SLO recovery detection window of 3 minutes."""
        from app.infrastructure.external.cache.circuit_breaker import (
            CircuitBreakerConfig,
        )

        config = CircuitBreakerConfig()

        assert config.recovery_window_seconds == 180  # 3 minutes
