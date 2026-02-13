# Multi-API Key Management - Integration Testing Guide

**Task 9 & 13: E2E Integration Tests + Manual Testing**

## Overview

This guide covers integration testing for the multi-API key management system across all providers (Serper, Tavily, Brave, OpenAI Embeddings, Anthropic, OpenAI LLM).

## Automated E2E Tests (Task 9)

### Test File: `backend/tests/integration/test_multikey_e2e.py`

```python
"""End-to-end integration tests for multi-key management."""

import pytest
from app.infrastructure.external.search.serper_search import SerperSearchEngine
from app.infrastructure.external.search.tavily_search import TavilySearchEngine
from app.infrastructure.external.search.brave_search import BraveSearchEngine
from app.infrastructure.external.embedding.client import EmbeddingClient
from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM
from app.infrastructure.external.llm.openai_llm import OpenAILLM


class TestMultiKeyRotationE2E:
    """Test end-to-end key rotation across all providers."""

    async def test_serper_rotation_workflow(self, redis_client, settings):
        """Test Serper exhaustion → rotation → recovery cycle."""
        engine = SerperSearchEngine(
            api_key=settings.serper_api_key,
            fallback_api_keys=[settings.serper_api_key_2, settings.serper_api_key_3],
            redis_client=redis_client,
        )

        # Verify pool initialized
        assert len(engine._key_pool.keys) == 3

        # Simulate exhaustion and rotation
        primary_key = await engine.api_key
        await engine._key_pool.mark_exhausted(primary_key, ttl_seconds=3600)

        # Next key should be fallback
        next_key = await engine.api_key
        assert next_key != primary_key

    async def test_tavily_json_error_detection(self, redis_client, settings):
        """Test Tavily JSON body error detection."""
        engine = TavilySearchEngine(
            api_key=settings.tavily_api_key,
            fallback_api_keys=[settings.tavily_api_key_2],
            redis_client=redis_client,
        )

        # Verify JSON error detection logic exists
        assert hasattr(engine, 'search')
        # Note: Full test requires mocking HTTP responses

    async def test_embedding_round_robin_distribution(self, redis_client, settings):
        """Test embedding client distributes load evenly."""
        client = EmbeddingClient(
            api_key=settings.embedding_api_key,
            fallback_api_keys=[settings.embedding_api_key_2, settings.embedding_api_key_3],
            redis_client=redis_client,
        )

        # Get 9 keys (3 rounds)
        keys_used = [await client.get_api_key() for _ in range(9)]

        # Verify even distribution
        from collections import Counter
        distribution = Counter(keys_used)
        assert all(count == 3 for count in distribution.values())

    async def test_anthropic_cache_locality(self, redis_client, settings):
        """Test Anthropic FAILOVER preserves cache locality."""
        llm = AnthropicLLM(
            api_key=settings.anthropic_api_key,
            fallback_api_keys=[settings.anthropic_api_key_2],
            redis_client=redis_client,
        )

        # Request key 10 times - should always be primary
        keys_used = [await llm.get_api_key() for _ in range(10)]
        assert all(k == settings.anthropic_api_key for k in keys_used)

    async def test_redis_degradation_all_providers(self, settings):
        """Test all providers work without Redis."""
        # Serper
        serper = SerperSearchEngine(
            api_key="test-key",
            redis_client=None,
        )
        assert await serper.api_key == "test-key"

        # Tavily
        tavily = TavilySearchEngine(
            api_key="test-key",
            redis_client=None,
        )
        assert await tavily.api_key == "test-key"

        # Embeddings
        embeddings = EmbeddingClient(
            api_key="test-key",
            redis_client=None,
        )
        assert await embeddings.get_api_key() == "test-key"

        # Anthropic
        anthropic = AnthropicLLM(
            api_key="test-key",
            redis_client=None,
        )
        assert await anthropic.get_api_key() == "test-key"


class TestMultiKeyMetrics:
    """Test Prometheus metrics integration."""

    async def test_metrics_recorded(self, redis_client, settings):
        """Test that key pool operations record metrics."""
        from app.infrastructure.observability.prometheus_metrics import (
            api_key_selections_total,
            api_key_exhaustions_total,
        )

        engine = SerperSearchEngine(
            api_key=settings.serper_api_key,
            redis_client=redis_client,
        )

        # Get key (should increment selection counter)
        await engine.api_key

        # Verify metric recorded (check implementation-specific)
        # Note: Actual assertion depends on custom Prometheus implementation


class TestMultiKeyRecovery:
    """Test TTL-based auto-recovery."""

    async def test_ttl_recovery_cycle(self, redis_client, settings):
        """Test key recovers after TTL expires."""
        engine = SerperSearchEngine(
            api_key=settings.serper_api_key,
            redis_client=redis_client,
        )

        # Mark key exhausted with 1-second TTL
        key = await engine.api_key
        await engine._key_pool.mark_exhausted(key, ttl_seconds=1)

        # Immediately after: key should be unavailable
        import asyncio
        await asyncio.sleep(0.1)
        next_key = await engine.api_key
        assert next_key != key or len(engine._key_pool.keys) == 1

        # After TTL expires: key should recover
        await asyncio.sleep(1.5)
        recovered_key = await engine.api_key
        # Note: FAILOVER always prefers primary, so if primary recovered, it returns primary
```

### Running E2E Tests

```bash
cd backend
pytest tests/integration/test_multikey_e2e.py -v --tb=short
```

## Manual Integration Testing (Task 13)

### Test Plan

#### 1. Serper Multi-Key Rotation

```python
# Manual test in Python REPL
from app.infrastructure.external.search.serper_search import SerperSearchEngine
from app.infrastructure.storage.redis import get_redis

redis = get_redis()
engine = SerperSearchEngine(
    api_key="YOUR_KEY_1",
    fallback_api_keys=["YOUR_KEY_2", "YOUR_KEY_3"],
    redis_client=redis,
)

# Test 1: Perform search
result = await engine.search("Python programming")
print(f"Success: {result.success}, Results: {len(result.data.results)}")

# Test 2: Exhaust primary key
primary = await engine.api_key
await engine._key_pool.mark_exhausted(primary, ttl_seconds=10)

# Test 3: Verify rotation
next_key = await engine.api_key
print(f"Rotated: {next_key != primary}")

# Test 4: Wait for recovery
import asyncio
await asyncio.sleep(11)
recovered = await engine.api_key
print(f"Recovered: {recovered == primary}")
```

#### 2. Tavily JSON Error Detection

```python
from app.infrastructure.external.search.tavily_search import TavilySearchEngine

engine = TavilySearchEngine(
    api_key="YOUR_KEY_1",
    fallback_api_keys=["YOUR_KEY_2"],
    redis_client=redis,
)

# Test: Search with quota exhaustion scenario
# (Requires hitting actual quota limit or mocking)
result = await engine.search("test query")
```

#### 3. Embedding Round-Robin Distribution

```python
from app.infrastructure.external.embedding.client import EmbeddingClient

client = EmbeddingClient(
    api_key="YOUR_KEY_1",
    fallback_api_keys=["YOUR_KEY_2", "YOUR_KEY_3"],
    redis_client=redis,
)

# Test: Get 9 keys and verify even distribution
keys = [await client.get_api_key() for _ in range(9)]
from collections import Counter
distribution = Counter(keys)
print(f"Distribution: {distribution}")
# Expected: {'key1': 3, 'key2': 3, 'key3': 3}
```

#### 4. Anthropic Cache Locality

```python
from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

llm = AnthropicLLM(
    api_key="YOUR_KEY_1",
    fallback_api_keys=["YOUR_KEY_2"],
    redis_client=redis,
)

# Test: Verify FAILOVER always returns primary
for i in range(5):
    key = await llm.get_api_key()
    print(f"Iteration {i+1}: {key == 'YOUR_KEY_1'}")
# Expected: All True
```

#### 5. Multi-Instance Coordination (Redis)

**Terminal 1:**
```python
engine = SerperSearchEngine(api_key="key1", redis_client=redis)
primary = await engine.api_key
await engine._key_pool.mark_exhausted(primary, ttl_seconds=60)
print(f"Instance 1 marked {primary} exhausted")
```

**Terminal 2:**
```python
engine = SerperSearchEngine(api_key="key1", fallback_api_keys=["key2"], redis_client=redis)
key = await engine.api_key
print(f"Instance 2 got: {key}")  # Should get key2 (primary exhausted)
```

### Success Criteria

- ✅ All E2E tests pass
- ✅ Manual rotation tests show correct key switching
- ✅ TTL recovery works as expected
- ✅ Round-robin distributes load evenly
- ✅ FAILOVER preserves cache locality
- ✅ Multi-instance coordination via Redis works
- ✅ Graceful degradation without Redis works

### Common Issues

**Issue: "All keys exhausted" error**
- Verify all keys are valid (check .env)
- Check Redis connection (run `redis-cli ping`)
- Verify TTL hasn't expired for all keys

**Issue: Round-robin not distributing evenly**
- Check that strategy is ROUND_ROBIN (not FAILOVER)
- Verify key pool has multiple keys (`len(pool.keys) > 1`)

**Issue: Multi-instance coordination not working**
- Verify Redis is running and accessible
- Check Redis keys: `redis-cli keys "api_key:*"`
- Verify both instances use same Redis instance

## Monitoring

### Grafana Dashboard Queries

**Key Selection Rate:**
```promql
rate(pythinker_api_key_selections_total[5m])
```

**Key Exhaustion Events:**
```promql
sum by (provider, reason) (pythinker_api_key_exhaustions_total)
```

**Key Health Score:**
```promql
pythinker_api_key_health_score
```

## Completion Checklist

- [ ] E2E test file created
- [ ] All E2E tests passing
- [ ] Manual rotation tests performed for all providers
- [ ] TTL recovery verified
- [ ] Multi-instance coordination tested
- [ ] Grafana queries verified
- [ ] Documentation updated

---

**Status:** Tasks 9 & 13 can be marked complete after running all tests and verifying manual scenarios.
