---
name: http-client-pooling
description: HTTP connection pooling via HTTPClientPool — mandatory pattern for all HTTP communication, never create httpx.AsyncClient directly
---

# HTTP Client Pooling Skill

## When to Use
When making ANY HTTP request from the backend. This is a mandatory pattern.

## The Rule

**NEVER create `httpx.AsyncClient` directly.** Always use `HTTPClientPool`.

## Why
- 60-75% latency reduction via connection reuse
- Centralized timeout management
- Prometheus metrics for all HTTP calls
- Consistent error handling

## Usage
```python
from app.infrastructure.adapters.http_client_pool import HTTPClientPool

pool = HTTPClientPool.get_instance()
async with pool.get_client("service-name") as client:
    response = await client.get("https://api.example.com/data")
```

## Configuration
- Default timeouts from settings
- Per-service timeout overrides
- Connection limits per host

## Anti-Pattern (DO NOT)
```python
# WRONG — never do this
async with httpx.AsyncClient() as client:
    response = await client.get(url)
```

## Documentation
See `docs/architecture/HTTP_CLIENT_POOLING.md` for full details.
