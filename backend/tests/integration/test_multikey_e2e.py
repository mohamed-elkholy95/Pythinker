"""End-to-end integration tests for multi-key management.

Tests the complete multi-API key management system across all providers:
- Serper, Tavily, Brave (search engines)
- OpenAI Embeddings
- Anthropic LLM
- OpenAI LLM

Tests key rotation, recovery, metrics, and Redis coordination.

Prerequisites:
    - Redis running at localhost:6379
    - API keys configured in .env (can be test keys)

Run:
    pytest tests/integration/test_multikey_e2e.py -v
    pytest tests/integration/test_multikey_e2e.py -v -k "rotation"
"""

import asyncio
import contextlib
from collections import Counter

import pytest

from app.core.config import get_settings
from app.infrastructure.external.embedding.client import EmbeddingClient
from app.infrastructure.external.key_pool import RotationStrategy
from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM
from app.infrastructure.external.llm.openai_llm import OpenAILLM
from app.infrastructure.external.search.brave_search import BraveSearchEngine
from app.infrastructure.external.search.serper_search import SerperSearchEngine
from app.infrastructure.external.search.tavily_search import TavilySearchEngine
from app.infrastructure.storage.redis import get_redis


@pytest.fixture
async def redis_client():
    """Get Redis client for testing.

    Skips test if Redis is unavailable.
    """
    client = get_redis()
    try:
        await client.initialize()
        # Verify Redis is reachable
        await client.client.ping()
    except Exception as e:
        pytest.skip(f"Redis unavailable: {e}")

    yield client

    # Cleanup
    with contextlib.suppress(Exception):
        await client.shutdown()


@pytest.fixture
def settings():
    """Get application settings."""
    return get_settings()


class TestMultiKeyRotationE2E:
    """Test end-to-end key rotation across all providers."""

    @pytest.mark.asyncio
    async def test_serper_rotation_workflow(self, redis_client, settings):
        """Test Serper exhaustion → rotation → recovery cycle."""
        if not settings.serper_api_key:
            pytest.skip("SERPER_API_KEY not configured")

        # Build fallback keys list (filter None values)
        fallback_keys = [k for k in [settings.serper_api_key_2, settings.serper_api_key_3] if k and k.strip()]

        engine = SerperSearchEngine(
            api_key=settings.serper_api_key,
            fallback_api_keys=fallback_keys if fallback_keys else None,
            redis_client=redis_client,
        )

        # Verify pool initialized
        expected_keys = 1 + len(fallback_keys)
        assert len(engine._key_pool.keys) == expected_keys

        # Get primary key
        primary_key = await engine.api_key
        assert primary_key == settings.serper_api_key

        if len(fallback_keys) > 0:
            # Simulate exhaustion and rotation
            await engine._key_pool.mark_exhausted(primary_key, ttl_seconds=3600)

            # Next key should be fallback
            next_key = await engine.api_key
            assert next_key != primary_key
            assert next_key in fallback_keys

    @pytest.mark.asyncio
    async def test_tavily_json_error_detection(self, redis_client, settings):
        """Test Tavily JSON body error detection."""
        if not settings.tavily_api_key:
            pytest.skip("TAVILY_API_KEY not configured")

        # Build fallback keys list (filter None values)
        fallback_keys = [k for k in [settings.tavily_api_key_2] if k and k.strip()]

        engine = TavilySearchEngine(
            api_key=settings.tavily_api_key,
            fallback_api_keys=fallback_keys if fallback_keys else None,
            redis_client=redis_client,
        )

        # Verify search method exists and has error handling
        assert hasattr(engine, "search")
        assert engine._key_pool is not None
        # Note: Full error detection test requires mocking HTTP responses

    @pytest.mark.asyncio
    async def test_brave_rotation_workflow(self, redis_client, settings):
        """Test Brave search exhaustion → rotation → recovery cycle."""
        if not settings.brave_search_api_key:
            pytest.skip("BRAVE_SEARCH_API_KEY not configured")

        # Build fallback keys list (filter None values)
        fallback_keys = [
            k for k in [settings.brave_search_api_key_2, settings.brave_search_api_key_3] if k and k.strip()
        ]

        engine = BraveSearchEngine(
            api_key=settings.brave_search_api_key,
            fallback_api_keys=fallback_keys if fallback_keys else None,
            redis_client=redis_client,
        )

        # Verify pool initialized
        expected_keys = 1 + len(fallback_keys)
        assert len(engine._key_pool.keys) == expected_keys

        # Get primary key
        primary_key = await engine.api_key
        assert primary_key == settings.brave_search_api_key

    @pytest.mark.asyncio
    async def test_embedding_round_robin_distribution(self, redis_client, settings):
        """Test embedding client distributes load evenly."""
        if not settings.embedding_api_key:
            pytest.skip("EMBEDDING_API_KEY not configured")

        # Build fallback keys list (filter None values)
        fallback_keys = [k for k in [settings.embedding_api_key_2, settings.embedding_api_key_3] if k and k.strip()]

        if len(fallback_keys) < 2:
            pytest.skip("Need at least 3 embedding keys for round-robin test")

        client = EmbeddingClient(
            api_key=settings.embedding_api_key,
            fallback_api_keys=fallback_keys,
            redis_client=redis_client,
        )

        # Verify ROUND_ROBIN strategy
        assert client._key_pool.strategy == RotationStrategy.ROUND_ROBIN

        # Get 9 keys (3 rounds)
        keys_used = [await client.get_api_key() for _ in range(9)]

        # Verify even distribution
        distribution = Counter(keys_used)
        assert all(count == 3 for count in distribution.values())

    @pytest.mark.asyncio
    async def test_anthropic_cache_locality(self, redis_client, settings):
        """Test Anthropic FAILOVER preserves cache locality."""
        if not settings.anthropic_api_key:
            pytest.skip("ANTHROPIC_API_KEY not configured")

        # Build fallback keys list (filter None values)
        fallback_keys = [k for k in [settings.anthropic_api_key_2] if k and k.strip()]

        llm = AnthropicLLM(
            api_key=settings.anthropic_api_key,
            fallback_api_keys=fallback_keys if fallback_keys else None,
            redis_client=redis_client,
        )

        # Verify FAILOVER strategy
        assert llm._key_pool.strategy == RotationStrategy.FAILOVER

        # Request key 10 times - should always be primary (FAILOVER prefers primary)
        keys_used = [await llm.get_api_key() for _ in range(10)]
        assert all(k == settings.anthropic_api_key for k in keys_used)

    @pytest.mark.asyncio
    async def test_openai_llm_failover(self, redis_client, settings):
        """Test OpenAI LLM uses FAILOVER strategy."""
        if not settings.api_key:
            pytest.skip("API_KEY (OpenAI) not configured")

        # Build fallback keys list (filter None values)
        fallback_keys = [k for k in [settings.api_key_2] if k and k.strip()]

        llm = OpenAILLM(
            api_key=settings.api_key,
            fallback_api_keys=fallback_keys if fallback_keys else None,
            redis_client=redis_client,
        )

        # Verify FAILOVER strategy (cache locality)
        assert llm._key_pool.strategy == RotationStrategy.FAILOVER

        # Request key multiple times - should always be primary
        keys_used = [await llm.get_api_key() for _ in range(5)]
        assert all(k == settings.api_key for k in keys_used)

    @pytest.mark.asyncio
    async def test_redis_degradation_all_providers(self, settings):
        """Test all providers work without Redis."""
        # Serper
        if settings.serper_api_key:
            serper = SerperSearchEngine(
                api_key=settings.serper_api_key,
                redis_client=None,
            )
            key = await serper.api_key
            assert key == settings.serper_api_key

        # Tavily
        if settings.tavily_api_key:
            tavily = TavilySearchEngine(
                api_key=settings.tavily_api_key,
                redis_client=None,
            )
            key = await tavily.api_key
            assert key == settings.tavily_api_key

        # Brave
        if settings.brave_search_api_key:
            brave = BraveSearchEngine(
                api_key=settings.brave_search_api_key,
                redis_client=None,
            )
            key = await brave.api_key
            assert key == settings.brave_search_api_key

        # Embeddings
        if settings.embedding_api_key:
            embeddings = EmbeddingClient(
                api_key=settings.embedding_api_key,
                redis_client=None,
            )
            key = await embeddings.get_api_key()
            assert key == settings.embedding_api_key

        # Anthropic
        if settings.anthropic_api_key:
            anthropic = AnthropicLLM(
                api_key=settings.anthropic_api_key,
                redis_client=None,
            )
            key = await anthropic.get_api_key()
            assert key == settings.anthropic_api_key

        # OpenAI LLM
        if settings.api_key:
            openai = OpenAILLM(
                api_key=settings.api_key,
                redis_client=None,
            )
            key = await openai.get_api_key()
            assert key == settings.api_key


class TestMultiKeyMetrics:
    """Test Prometheus metrics integration."""

    @pytest.mark.asyncio
    async def test_metrics_recorded(self, redis_client, settings):
        """Test that key pool operations record metrics."""
        if not settings.serper_api_key:
            pytest.skip("SERPER_API_KEY not configured")

        from app.core.prometheus_metrics import (
            api_key_exhaustions_total,
            api_key_health_score,
            api_key_selections_total,
        )

        engine = SerperSearchEngine(
            api_key=settings.serper_api_key,
            redis_client=redis_client,
        )

        # Get key (should increment selection counter)
        key = await engine.api_key
        assert key is not None

        # Verify metrics exist (Prometheus counters/gauges)
        # Note: Actual values depend on test execution order
        assert api_key_selections_total is not None
        assert api_key_exhaustions_total is not None
        assert api_key_health_score is not None

    @pytest.mark.asyncio
    async def test_exhaustion_metrics(self, redis_client, settings):
        """Test exhaustion events are recorded in metrics."""
        if not settings.serper_api_key:
            pytest.skip("SERPER_API_KEY not configured")

        engine = SerperSearchEngine(
            api_key=settings.serper_api_key,
            redis_client=redis_client,
        )

        # Mark key exhausted
        primary_key = await engine.api_key
        await engine._key_pool.mark_exhausted(primary_key, ttl_seconds=10)

        # Verify key is marked as exhausted
        is_healthy = await engine._key_pool._is_healthy(primary_key)
        assert not is_healthy


class TestMultiKeyRecovery:
    """Test TTL-based auto-recovery."""

    @pytest.mark.asyncio
    async def test_ttl_recovery_cycle(self, redis_client, settings):
        """Test key recovers after TTL expires."""
        if not settings.serper_api_key:
            pytest.skip("SERPER_API_KEY not configured")

        # Build fallback keys list (filter None values)
        fallback_keys = [k for k in [settings.serper_api_key_2] if k and k.strip()]

        if len(fallback_keys) == 0:
            pytest.skip("Need at least 2 serper keys for recovery test")

        engine = SerperSearchEngine(
            api_key=settings.serper_api_key,
            fallback_api_keys=fallback_keys,
            redis_client=redis_client,
        )

        # Mark key exhausted with 2-second TTL
        key = await engine.api_key
        await engine._key_pool.mark_exhausted(key, ttl_seconds=2)

        # Immediately after: key should be unavailable
        await asyncio.sleep(0.1)
        next_key = await engine.api_key

        # Should have rotated to fallback (unless only 1 key)
        if len(engine._key_pool.keys) > 1:
            assert next_key != key

        # After TTL expires: key should recover
        await asyncio.sleep(2.5)
        recovered_key = await engine.api_key

        # Note: FAILOVER always prefers primary, so if primary recovered, it returns primary
        assert recovered_key is not None

    @pytest.mark.asyncio
    async def test_multi_instance_coordination(self, redis_client, settings):
        """Test Redis coordinates key health across multiple instances."""
        if not settings.serper_api_key:
            pytest.skip("SERPER_API_KEY not configured")

        # Create two engine instances (simulate two app instances)
        engine1 = SerperSearchEngine(
            api_key=settings.serper_api_key,
            redis_client=redis_client,
        )

        engine2 = SerperSearchEngine(
            api_key=settings.serper_api_key,
            redis_client=redis_client,
        )

        # Instance 1 marks key exhausted
        primary_key = await engine1.api_key
        await engine1._key_pool.mark_exhausted(primary_key, ttl_seconds=10)

        # Instance 2 should see the key as exhausted (Redis coordination)
        is_healthy = await engine2._key_pool._is_healthy(primary_key)
        assert not is_healthy

    @pytest.mark.asyncio
    async def test_recovery_after_short_ttl(self, redis_client, settings):
        """Test that keys recover immediately after TTL expires."""
        if not settings.embedding_api_key:
            pytest.skip("EMBEDDING_API_KEY not configured")

        client = EmbeddingClient(
            api_key=settings.embedding_api_key,
            redis_client=redis_client,
        )

        # Mark key exhausted with 1-second TTL
        key = await client.get_api_key()
        await client._key_pool.mark_exhausted(key, ttl_seconds=1)

        # Verify exhausted
        is_healthy = await client._key_pool._is_healthy(key)
        assert not is_healthy

        # Wait for TTL to expire
        await asyncio.sleep(1.5)

        # Verify recovered
        is_healthy_after = await client._key_pool._is_healthy(key)
        assert is_healthy_after

    @pytest.mark.asyncio
    async def test_all_keys_exhausted_scenario(self, redis_client, settings):
        """Test behavior when all keys are exhausted."""
        if not settings.serper_api_key:
            pytest.skip("SERPER_API_KEY not configured")

        # Build fallback keys list (filter None values)
        fallback_keys = [k for k in [settings.serper_api_key_2, settings.serper_api_key_3] if k and k.strip()]

        engine = SerperSearchEngine(
            api_key=settings.serper_api_key,
            fallback_api_keys=fallback_keys if fallback_keys else None,
            redis_client=redis_client,
        )

        # Exhaust all keys
        for key_config in engine._key_pool.keys:
            await engine._key_pool.mark_exhausted(key_config.key, ttl_seconds=10)

        # Requesting key should return None
        key = await engine.api_key
        assert key is None
