# Multi-API Key Management - .env Configuration Guide

**Task 10: Update .env.example with Multi-Key Documentation**

## Updates Required for .env.example

### 1. Search Engine API Keys

Add to `.env.example` after existing search engine configuration:

```bash
# =============================================================================
# Multi-API Key Configuration (Failover & Load Distribution)
# =============================================================================

# Serper.dev API Keys (up to 3 keys)
# Strategy: FAILOVER (primary → backup1 → backup2)
# Quota: 2,500 searches/month per key (free tier)
# TTL Recovery: 1 hour (quota resets hourly)
SERPER_API_KEY=your-primary-serper-key-here
SERPER_API_KEY_2=your-backup-serper-key-1
SERPER_API_KEY_3=your-backup-serper-key-2

# Tavily AI Search Keys (up to 9 keys)
# Strategy: FAILOVER (primary → backup1 → ... → backup8)
# Quota: 1,000 searches/month per key (free tier)
# TTL Recovery: 24 hours (quota resets daily)
TAVILY_API_KEY=your-primary-tavily-key-here
TAVILY_API_KEY_2=your-backup-tavily-key-1
TAVILY_API_KEY_3=your-backup-tavily-key-2
TAVILY_API_KEY_4=your-backup-tavily-key-3
TAVILY_API_KEY_5=your-backup-tavily-key-4
TAVILY_API_KEY_6=your-backup-tavily-key-5
TAVILY_API_KEY_7=your-backup-tavily-key-6
TAVILY_API_KEY_8=your-backup-tavily-key-7
TAVILY_API_KEY_9=your-backup-tavily-key-8

# Brave Search API Keys (up to 3 keys)
# Strategy: FAILOVER
# TTL Recovery: 24 hours
BRAVE_SEARCH_API_KEY=your-primary-brave-key-here
BRAVE_SEARCH_API_KEY_2=your-backup-brave-key-1
BRAVE_SEARCH_API_KEY_3=your-backup-brave-key-2

# =============================================================================
# LLM API Keys
# =============================================================================

# OpenAI/OpenRouter API Keys (up to 3 keys)
# Strategy: FAILOVER (preserves prompt caching)
# Used for: Chat completions via OpenAI-compatible API
API_KEY=your-primary-openai-key-here
API_KEY_2=your-backup-openai-key-1
API_KEY_3=your-backup-openai-key-2

# Anthropic API Keys (up to 3 keys)
# Strategy: FAILOVER (preserves prompt caching - critical for cost savings!)
# Prompt caching reduces costs by ~90% - stick with primary key for max benefit
# TTL Recovery: Parsed from anthropic-ratelimit-tokens-reset header
ANTHROPIC_API_KEY=your-primary-anthropic-key-here
ANTHROPIC_API_KEY_2=your-backup-anthropic-key-1
ANTHROPIC_API_KEY_3=your-backup-anthropic-key-2

# =============================================================================
# Embedding API Keys
# =============================================================================

# OpenAI Embedding Keys (up to 3 keys)
# Strategy: ROUND_ROBIN (distributes high-volume load evenly)
# Use case: 10k+ embeddings/day - each key gets 1/3 of requests
# TTL Recovery: Parsed from x-ratelimit-reset-requests header
EMBEDDING_API_KEY=your-primary-embedding-key-here
EMBEDDING_API_KEY_2=your-backup-embedding-key-1
EMBEDDING_API_KEY_3=your-backup-embedding-key-2
```

### 2. Add Multi-Key Management Section

Add new section to `.env.example`:

```bash
# =============================================================================
# Multi-API Key Management Configuration
# =============================================================================

# Redis is REQUIRED for multi-instance key coordination
# Without Redis, keys work in single-instance in-memory mode
# See: docs/architecture/MULTI_API_KEY_MANAGEMENT.md
REDIS_HOST=redis
REDIS_PORT=6379

# Key rotation strategies (configured automatically per provider):
# - FAILOVER: Primary → Backup (preserves caching, search engines, LLMs)
# - ROUND_ROBIN: Even distribution (high-volume embeddings)
# - WEIGHTED: Quota-based distribution (future enhancement)

# TTL-based recovery:
# - Serper: 1 hour (3600s) - hourly quota reset
# - Tavily: 24 hours (86400s) - daily quota reset
# - Brave: 24 hours (86400s) - monthly quota, daily TTL is safe
# - OpenAI LLM: Parsed from x-ratelimit-reset header (dynamic)
# - Anthropic: Parsed from anthropic-ratelimit-tokens-reset header (dynamic)
# - Embeddings: Parsed from x-ratelimit-reset-requests header (dynamic)

# Prometheus metrics (automatic):
# - pythinker_api_key_selections_total - Key usage counter
# - pythinker_api_key_exhaustions_total - Quota/auth failures
# - pythinker_api_key_health_score - Current health (0=unhealthy, 1=healthy)
# - pythinker_api_key_latency_seconds - Request latency per key
```

### 3. Update Existing Sections

**Replace single-key comments:**

```bash
# OLD (single key):
SERPER_API_KEY=your-serper-key-here

# NEW (multi-key aware):
# See Multi-API Key Configuration section below for SERPER_API_KEY_2, SERPER_API_KEY_3
SERPER_API_KEY=your-primary-serper-key-here
```

## Configuration Examples

### Example 1: Single Key Mode (Backward Compatible)

```bash
# Works exactly as before - no changes needed
SERPER_API_KEY=sk-abc123
# SERPER_API_KEY_2 and _3 are optional
```

### Example 2: Full Multi-Key Setup

```bash
# Serper: 3 keys (7,500 searches/month total)
SERPER_API_KEY=sk-serper-primary-abc123
SERPER_API_KEY_2=sk-serper-backup1-def456
SERPER_API_KEY_3=sk-serper-backup2-ghi789

# Tavily: 9 keys (9,000 searches/month total)
TAVILY_API_KEY=tvly-primary-abc
TAVILY_API_KEY_2=tvly-backup1-def
TAVILY_API_KEY_3=tvly-backup2-ghi
TAVILY_API_KEY_4=tvly-backup3-jkl
TAVILY_API_KEY_5=tvly-backup4-mno
TAVILY_API_KEY_6=tvly-backup5-pqr
TAVILY_API_KEY_7=tvly-backup6-stu
TAVILY_API_KEY_8=tvly-backup7-vwx
TAVILY_API_KEY_9=tvly-backup8-yz

# Anthropic: 3 keys (FAILOVER for caching)
ANTHROPIC_API_KEY=sk-ant-primary-abc
ANTHROPIC_API_KEY_2=sk-ant-backup1-def
ANTHROPIC_API_KEY_3=sk-ant-backup2-ghi

# Embeddings: 3 keys (ROUND_ROBIN for load)
EMBEDDING_API_KEY=sk-embed-1-abc
EMBEDDING_API_KEY_2=sk-embed-2-def
EMBEDDING_API_KEY_3=sk-embed-3-ghi
```

### Example 3: Mixed Configuration

```bash
# Some providers with multi-key, others single
SERPER_API_KEY=sk-serper-only-one
# No SERPER_API_KEY_2/3 - single key mode

TAVILY_API_KEY=tvly-primary
TAVILY_API_KEY_2=tvly-backup
# Only 2 keys for Tavily (not all 9)

ANTHROPIC_API_KEY=sk-ant-primary
ANTHROPIC_API_KEY_2=sk-ant-backup
ANTHROPIC_API_KEY_3=sk-ant-backup2
# Full 3-key setup for Anthropic
```

## Strategy Selection Guide

| Provider | Strategy | Reason | Max Keys |
|----------|----------|--------|----------|
| Serper | FAILOVER | Preserve primary quota tier | 3 |
| Tavily | FAILOVER | Priority-based rotation | 9 |
| Brave | FAILOVER | Standard search pattern | 3 |
| OpenAI LLM | FAILOVER | Preserve prompt caching (if supported) | 3 |
| Anthropic | FAILOVER | **Critical:** Prompt caching ~90% cost savings | 3 |
| Embeddings | ROUND_ROBIN | High-volume load distribution (10k+/day) | 3 |

## Quota Calculations

### Serper (Free Tier)
- Single key: 2,500 searches/month
- 3 keys (FAILOVER): 7,500 searches/month
- Pattern: Primary exhausts → Backup1 → Backup2

### Tavily (Free Tier)
- Single key: 1,000 searches/month
- 9 keys (FAILOVER): 9,000 searches/month
- Pattern: Try keys in priority order

### Embeddings (OpenAI Free Tier)
- Single key: Rate limited by tokens/min
- 3 keys (ROUND_ROBIN): 3x throughput
- Pattern: Request 1 → Key1, Request 2 → Key2, Request 3 → Key3, Request 4 → Key1

## Migration Guide

### Upgrading from Single Key to Multi-Key

**Step 1: Get Additional API Keys**
- Sign up for additional free tier accounts
- Or purchase additional keys from provider

**Step 2: Add to .env**
```bash
# Add new keys (existing key becomes primary)
SERPER_API_KEY_2=your-new-key-here
SERPER_API_KEY_3=your-another-key-here
```

**Step 3: Restart Services**
```bash
docker-compose restart backend
```

**Step 4: Verify**
```bash
# Check logs for "initialized with N API key(s)"
docker logs pythinker-backend-1 | grep "initialized with"

# Expected output:
# Serper search initialized with 3 API key(s)
# Tavily search initialized with 2 API key(s)
```

## Troubleshooting

### "All keys exhausted" Error

**Cause:** All configured keys hit quota limits.

**Solution:**
1. Wait for TTL recovery (check provider's quota reset time)
2. Add more keys to .env
3. Upgrade to paid tier for higher quotas

### "Redis unavailable" Warning

**Cause:** Redis not running or not accessible.

**Impact:** System degrades to in-memory mode (no multi-instance coordination).

**Solution:**
```bash
# Start Redis
docker-compose up -d redis

# Verify Redis is accessible
docker exec pythinker-backend-1 redis-cli -h redis ping
# Expected: PONG
```

### Keys Not Rotating

**Check 1: Verify Multiple Keys Configured**
```bash
grep -E "SERPER_API_KEY" .env
# Should show SERPER_API_KEY, SERPER_API_KEY_2, SERPER_API_KEY_3
```

**Check 2: Verify Keys are Different**
```bash
# All three values should be unique
```

**Check 3: Check Logs**
```bash
docker logs pythinker-backend-1 | grep "Key.*marked EXHAUSTED"
```

## Best Practices

1. **Use descriptive key names** in your API provider dashboard:
   - `pythinker-primary-serper`
   - `pythinker-backup1-serper`

2. **Monitor key health** via Grafana:
   - Set alerts for `pythinker_api_key_exhaustions_total`
   - Watch `pythinker_api_key_health_score`

3. **Rotate keys regularly**:
   - Free tier keys: Create new accounts every few months
   - Paid keys: Rotate annually for security

4. **Test failover**:
   - Periodically mark primary key exhausted
   - Verify system switches to backup
   - Verify primary recovers after TTL

## Completion Checklist

- [ ] .env.example updated with all new key fields
- [ ] Multi-key management section added
- [ ] Strategy selection documented
- [ ] Quota calculations provided
- [ ] Migration guide written
- [ ] Troubleshooting section complete
- [ ] Examples cover single/multi/mixed scenarios

---

**Status:** Task 10 complete when .env.example is updated with all sections above.
