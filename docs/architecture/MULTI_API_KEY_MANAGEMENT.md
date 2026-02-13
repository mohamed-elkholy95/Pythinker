# Multi-API Key Management System

**Production-Grade API Key Rotation, Failover, and Load Distribution**

## Overview

The Multi-API Key Management System provides production-grade key rotation, automatic failover, and load distribution across all external API providers (search engines, LLMs, embeddings).

**Key Features:**
- ✅ **Automatic Failover** - Seamless rotation when keys hit quota limits
- ✅ **TTL-Based Recovery** - Keys auto-recover after quota reset periods
- ✅ **Redis Coordination** - Multi-instance safe state sharing
- ✅ **Prometheus Metrics** - Real-time observability in Grafana
- ✅ **Strategy Selection** - FAILOVER, ROUND_ROBIN, WEIGHTED rotation
- ✅ **Graceful Degradation** - Works without Redis (in-memory mode)

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────┐
│                   Application Layer                      │
│  (SearchEngine, LLM, EmbeddingClient)                   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    APIKeyPool                            │
│  ┌──────────────┬──────────────┬──────────────┐        │
│  │ ROUND_ROBIN  │  FAILOVER    │   WEIGHTED   │        │
│  └──────────────┴──────────────┴──────────────┘        │
│  ┌──────────────────────────────────────────────┐      │
│  │  Health Tracking & TTL Recovery              │      │
│  └──────────────────────────────────────────────┘      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                Redis (Distributed State)                 │
│  api_key:exhausted:{provider}:{hash}  [TTL]            │
│  api_key:invalid:{provider}:{hash}    [No TTL]         │
└─────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Prometheus Metrics                          │
│  api_key_selections_total                               │
│  api_key_exhaustions_total                              │
│  api_key_health_score                                   │
└─────────────────────────────────────────────────────────┘
```

### Rotation Strategies

#### 1. FAILOVER (Primary + Backups)

**Use Cases:**
- Search engines (Serper, Tavily, Brave)
- LLMs with prompt caching (Anthropic, OpenAI)

**Pattern:**
```
Request 1 → Primary Key
Request 2 → Primary Key
Request 3 → Primary Key (quota exhausted!)
Request 4 → Backup1 Key
Request 5 → Backup1 Key
Request 6 → Backup1 Key (quota exhausted!)
Request 7 → Backup2 Key
```

**Benefits:**
- Preserves primary key benefits (caching, quota tier)
- Predictable fallback order
- Max cache hit rate (Anthropic saves ~90% with prompt caching)

**Configuration:**
```python
APIKeyPool(
    provider="anthropic",
    keys=[
        APIKeyConfig(key="primary", priority=0),    # Always tried first
        APIKeyConfig(key="backup1", priority=1),
        APIKeyConfig(key="backup2", priority=2),
    ],
    strategy=RotationStrategy.FAILOVER,
)
```

#### 2. ROUND_ROBIN (Load Distribution)

**Use Cases:**
- High-volume embeddings (10k+ requests/day)
- Distributed workloads

**Pattern:**
```
Request 1 → Key1
Request 2 → Key2
Request 3 → Key3
Request 4 → Key1 (back to start)
Request 5 → Key2
Request 6 → Key3
```

**Benefits:**
- Even load distribution across all keys
- Maximizes total throughput (N keys = N× capacity)
- No single key bottleneck

**Configuration:**
```python
APIKeyPool(
    provider="openai_embedding",
    keys=[
        APIKeyConfig(key="key1"),
        APIKeyConfig(key="key2"),
        APIKeyConfig(key="key3"),
    ],
    strategy=RotationStrategy.ROUND_ROBIN,
)
```

#### 3. WEIGHTED (Quota-Aware)

**Use Cases:**
- Mixed quota tiers (free + paid)
- Cost optimization

**Pattern:**
```python
# key1 (weight=3): 75% of requests
# key2 (weight=1): 25% of requests
APIKeyConfig(key="paid-key", weight=3),
APIKeyConfig(key="free-key", weight=1),
```

**Status:** Future enhancement (not yet implemented)

### Health Tracking

#### States

```python
class KeyHealthStatus(Enum):
    HEALTHY = "healthy"      # Fully operational
    DEGRADED = "degraded"    # Approaching quota (future)
    EXHAUSTED = "exhausted"  # Temporary quota exhaustion (TTL recovery)
    INVALID = "invalid"      # Permanent failure (auth error)
```

#### State Transitions

```
HEALTHY ──[429]──> EXHAUSTED ──[TTL expires]──> HEALTHY
   │
   └──[401]──> INVALID (permanent)
```

#### Redis Keys

```
# Temporary exhaustion (auto-recovers after TTL)
api_key:exhausted:{provider}:{key_hash}  [TTL: 3600-86400s]

# Permanent invalidation (manual intervention required)
api_key:invalid:{provider}:{key_hash}  [No TTL]
```

### TTL Recovery

**Concept:** Keys automatically recover after quota reset period.

**Implementation:**
```python
# Serper: 1-hour TTL (hourly quota reset)
await pool.mark_exhausted(key, ttl_seconds=3600)

# Tavily: 24-hour TTL (daily quota reset)
await pool.mark_exhausted(key, ttl_seconds=86400)

# OpenAI: Parse X-RateLimit-Reset header (dynamic)
ttl = parse_rate_limit_header(response.headers)
await pool.mark_exhausted(key, ttl_seconds=ttl)
```

**Benefits:**
- No manual intervention required
- Keys auto-recover after provider quota reset
- Multi-instance coordination via Redis TTL

## Provider Integration

### Search Engines

| Provider | Strategy | Max Keys | TTL | Error Detection |
|----------|----------|----------|-----|-----------------|
| **Serper** | FAILOVER | 3 | 1 hour | HTTP 401/429 |
| **Tavily** | FAILOVER | 9 | 24 hours | HTTP 401/429 + JSON body errors |
| **Brave** | FAILOVER | 3 | 24 hours | HTTP 401/429 |

**Example (Serper):**
```python
from app.infrastructure.external.search.serper_search import SerperSearchEngine

engine = SerperSearchEngine(
    api_key="primary-key",
    fallback_api_keys=["backup1", "backup2"],
    redis_client=redis,
)

# Automatic rotation on quota exhaustion
result = await engine.search("Python programming")
```

### LLM Providers

| Provider | Strategy | Max Keys | TTL | Caching |
|----------|----------|----------|-----|---------|
| **Anthropic** | FAILOVER | 3 | Dynamic (header) | ✅ Prompt caching (~90% savings) |
| **OpenAI** | FAILOVER | 3 | Dynamic (header) | ⚠️ Limited caching |

**Example (Anthropic):**
```python
from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM

llm = AnthropicLLM(
    api_key="primary-key",
    fallback_api_keys=["backup1", "backup2"],
    redis_client=redis,
)

# FAILOVER preserves prompt caching benefits
response = await llm.ask(messages=[...])
```

### Embedding Provider

| Provider | Strategy | Max Keys | TTL | Use Case |
|----------|----------|----------|-----|----------|
| **OpenAI** | ROUND_ROBIN | 3 | Dynamic | High-volume (10k+ embeddings/day) |

**Example:**
```python
from app.infrastructure.external.embedding.client import EmbeddingClient

client = EmbeddingClient(
    api_key="key1",
    fallback_api_keys=["key2", "key3"],
    redis_client=redis,
)

# Even load distribution across all keys
embeddings = await client.embed_batch(texts)
```

## Observability

### Prometheus Metrics

```python
# Key selection counter
api_key_selections_total{provider="serper", key_id="f0e4c2f7", status="success"}

# Exhaustion events
api_key_exhaustions_total{provider="anthropic", reason="quota"}

# Current health score
api_key_health_score{provider="tavily", key_id="81740996"}  # 0 or 1

# Latency histogram (future)
api_key_latency_seconds{provider="openai", key_id="abc12345"}
```

### Grafana Queries

**Key Usage Rate:**
```promql
rate(pythinker_api_key_selections_total{status="success"}[5m])
```

**Exhaustion Rate by Provider:**
```promql
sum by (provider) (rate(pythinker_api_key_exhaustions_total[1h]))
```

**Unhealthy Keys:**
```promql
pythinker_api_key_health_score == 0
```

**Alert: All Keys Exhausted:**
```promql
sum by (provider) (pythinker_api_key_health_score) == 0
```

### Loki Logs

**Key Rotation Events:**
```logql
{container_name="pythinker-backend-1"} |= "marked EXHAUSTED"
```

**Key Recovery:**
```logql
{container_name="pythinker-backend-1"} |= "auto-recovery"
```

**Invalid Keys:**
```logql
{container_name="pythinker-backend-1"} |= "marked INVALID"
```

## Configuration

### Environment Variables

See [Multi-Key .env Documentation](../guides/MULTI_KEY_ENV_DOCUMENTATION.md) for complete configuration guide.

**Quick Start:**
```bash
# Serper (3 keys)
SERPER_API_KEY=primary
SERPER_API_KEY_2=backup1
SERPER_API_KEY_3=backup2

# Anthropic (3 keys, cache-aware)
ANTHROPIC_API_KEY=primary
ANTHROPIC_API_KEY_2=backup1
ANTHROPIC_API_KEY_3=backup2

# Embeddings (3 keys, load distribution)
EMBEDDING_API_KEY=key1
EMBEDDING_API_KEY_2=key2
EMBEDDING_API_KEY_3=key3
```

### Factory Integration

Keys are automatically collected from settings:

```python
# backend/app/infrastructure/external/search/factory.py

if provider == "serper":
    return SerperSearchEngine(
        api_key=settings.serper_api_key,
        fallback_api_keys=[
            settings.serper_api_key_2,
            settings.serper_api_key_3,
        ],
        redis_client=redis_client,
    )
```

## Best Practices

### 1. Strategy Selection

**Use FAILOVER when:**
- Preserving caching benefits (Anthropic prompt caching)
- Hierarchical quota tiers (free → paid)
- Predictable fallback order preferred

**Use ROUND_ROBIN when:**
- High-volume workload (10k+ requests/day)
- All keys have equal quotas
- Maximizing total throughput

### 2. Key Quantity

**Minimum (Production):**
- Search engines: 2 keys (primary + backup)
- LLMs: 2 keys (primary + backup)
- Embeddings: 3 keys (load distribution)

**Recommended (High Availability):**
- Search engines: 3 keys
- LLMs: 3 keys
- Embeddings: 3+ keys (scale with volume)

### 3. Quota Monitoring

**Set Grafana alerts:**
```yaml
- alert: HighKeyExhaustionRate
  expr: rate(pythinker_api_key_exhaustions_total[1h]) > 10
  for: 5m
  annotations:
    summary: "High key exhaustion rate for {{ $labels.provider }}"

- alert: AllKeysExhausted
  expr: sum by (provider) (pythinker_api_key_health_score) == 0
  for: 1m
  annotations:
    summary: "All {{ $labels.provider }} keys exhausted!"
```

### 4. Key Rotation Schedule

**Free Tier Keys:**
- Create new accounts every 3-6 months
- Add new keys to .env
- Gradual rotation (add new, remove old after TTL)

**Paid Keys:**
- Annual rotation for security
- Use key naming conventions in provider dashboard

### 5. Testing

**Before Production:**
```python
# Test 1: Verify failover
primary_key = await pool.get_healthy_key()
await pool.mark_exhausted(primary_key, ttl_seconds=10)
backup_key = await pool.get_healthy_key()
assert backup_key != primary_key

# Test 2: Verify TTL recovery
await asyncio.sleep(11)
recovered_key = await pool.get_healthy_key()
assert recovered_key == primary_key  # FAILOVER returns primary when recovered
```

## Troubleshooting

### Issue: "All keys exhausted"

**Symptoms:**
- All requests failing
- Logs: "All N keys exhausted after M attempts"

**Diagnosis:**
```bash
# Check Redis for exhausted keys
docker exec pythinker-backend-1 redis-cli keys "api_key:exhausted:*"

# Check TTL
docker exec pythinker-backend-1 redis-cli ttl "api_key:exhausted:serper:abc123"
```

**Solutions:**
1. **Wait for TTL recovery** - Check provider's quota reset time
2. **Add more keys** - Update .env with additional keys
3. **Upgrade quota** - Purchase paid tier from provider

### Issue: Keys not rotating

**Check 1: Multiple keys configured?**
```bash
grep "SERPER_API_KEY" .env | wc -l
# Should be 3 (SERPER_API_KEY, _2, _3)
```

**Check 2: Redis accessible?**
```bash
docker exec pythinker-backend-1 redis-cli -h redis ping
# Expected: PONG
```

**Check 3: Verify pool initialization**
```bash
docker logs pythinker-backend-1 | grep "initialized with"
# Expected: "Serper search initialized with 3 API key(s)"
```

### Issue: Cache locality broken (Anthropic)

**Symptoms:**
- High Anthropic costs (no caching benefit)
- Frequent key switches

**Diagnosis:**
```python
# Verify FAILOVER strategy
assert llm._key_pool.strategy == RotationStrategy.FAILOVER

# Verify always returns primary
for _ in range(10):
    key = await llm.get_api_key()
    assert key == primary_key
```

**Solution:**
- Ensure FAILOVER strategy (not ROUND_ROBIN)
- Don't manually rotate unless primary exhausted

## Performance

### Overhead

**Per-Request Overhead:**
- Key pool lookup: ~0.1ms (in-memory)
- Redis health check: ~1-2ms (local), ~10-20ms (network)
- Total: **~2-20ms additional latency**

**Acceptable for:**
- Search API calls (100-1000ms response time)
- LLM calls (1-10s response time)
- Embedding batches (500ms-5s response time)

### Optimization

**Connection Pooling:**
```python
# APIKeyPool reuses same Redis connection
redis = get_redis()  # Connection pool

# All pools share connection
serper_pool = APIKeyPool(..., redis_client=redis)
tavily_pool = APIKeyPool(..., redis_client=redis)
```

**Batch Operations:**
```python
# Embedding client: Get key once, use for entire batch
key = await client.get_api_key()
results = await client._embed_batch_with_key(texts, key)
```

## Migration Guide

### Phase 1: Add Configuration

```bash
# .env
SERPER_API_KEY_2=backup1
SERPER_API_KEY_3=backup2
```

### Phase 2: Restart Services

```bash
docker-compose restart backend
```

### Phase 3: Verify

```bash
# Check logs
docker logs pythinker-backend-1 | grep "initialized with 3 API key"

# Check Prometheus
curl localhost:9090/api/v1/query?query=pythinker_api_key_health_score

# Check Redis
docker exec pythinker-backend-1 redis-cli keys "api_key:*"
```

### Phase 4: Monitor

- Add Grafana dashboard
- Set up alerts
- Track exhaustion rates

## Future Enhancements

**Planned (Phase 5):**
- [ ] WEIGHTED strategy implementation
- [ ] QUOTA_AWARE strategy (real-time quota tracking)
- [ ] Predictive rotation (rotate before exhaustion)
- [ ] Cost optimization (prefer cheaper keys)
- [ ] Multi-region support (route by latency)

**Under Consideration:**
- [ ] Async key pre-warming
- [ ] Circuit breaker pattern integration
- [ ] Key performance scoring
- [ ] Auto-scaling key pool size

## References

- **Implementation Plan:** `docs/plans/2026-02-13-multi-api-key-management.md`
- **.env Configuration:** `docs/guides/MULTI_KEY_ENV_DOCUMENTATION.md`
- **Integration Testing:** `docs/guides/MULTI_KEY_INTEGRATION_TESTING.md`
- **APIKeyPool Source:** `backend/app/infrastructure/external/key_pool.py`

---

**Status:** Production-ready as of 2026-02-13. All providers integrated and tested.
