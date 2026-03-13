---
name: api-key-management
description: Multi-API key pool management — rotation strategies, health tracking, Redis coordination, TTL recovery
---

# API Key Management Skill

## When to Use
When integrating external API providers or working with API key configuration.

## Architecture

### APIKeyPool
Central abstraction for managing multiple API keys per provider.

### Strategies
- **FAILOVER**: Use first healthy key, rotate on error (search engines, LLMs)
- **ROUND_ROBIN**: Distribute load across keys (embeddings)

### Key Rotation
- HTTP 401/429 → Rotate to next healthy key
- TTL-based recovery: Keys auto-recover after quota reset
- `engine._key_pool.get_healthy_key_or_wait()` for current key access

### Redis Coordination
- Required for multi-instance coordination
- Graceful degradation to in-memory when Redis unavailable

### Environment Variables
```bash
# Primary keys
SERPER_API_KEY=...
ANTHROPIC_API_KEY=...
EMBEDDING_API_KEY=...

# Fallback keys (up to 9)
SERPER_API_KEY_2=...
TAVILY_API_KEY_2=...
```

### Capacity
- Search: 3-9 keys per engine (Serper: 3, Tavily: 9, Brave: 3)
- LLMs: Up to 3 keys (Anthropic, OpenAI)
- Embeddings: Up to 3 keys

## Key Rule
**NEVER create direct API clients without key pool integration.** Always use `APIKeyPool` for external providers.

## Key Files
- `backend/app/infrastructure/adapters/api_key_pool.py`
- `backend/app/core/config.py` — Multi-key environment variables
