# HTTP Client Pool Integration Plan

**Status:** Draft
**Created:** 2026-02-11
**Owner:** Engineering Team
**Priority:** High (Performance & Resource Management)

---

## Executive Summary

This plan outlines the integration of the existing `HTTPClientPool` infrastructure into Pythinker's service communication layer, validated against latest httpx and FastAPI best practices from Context7 MCP.

**Key Findings:**
- ✅ HTTPClientPool infrastructure is well-designed
- ❌ HTTPClientPool is **not being used** (critical gap)
- ❌ DockerSandbox violates httpx best practice: "avoid creating multiple client instances"
- ❌ Missing FastAPI lifespan management for shared HTTP clients
- ✅ Qdrant already using gRPC (optimal for vector operations)

**Expected Impact:**
- **Latency Reduction:** 10-30ms → <1ms for repeated sandbox API calls
- **Memory Efficiency:** 50-100KB per client → shared pool
- **Resource Leaks:** Eliminated via proper lifecycle management
- **Observability:** Centralized metrics for all HTTP operations

---

## Validation Against Context7 MCP Best Practices

### httpx Best Practices (/encode/httpx - Score: 81.4)

| Best Practice | Current State | Compliant? |
|--------------|---------------|------------|
| **Use async with AsyncClient()** | ✅ Using AsyncClient | ✅ Yes |
| **Avoid multiple client instances** | ❌ DockerSandbox creates new client per instance | ❌ **CRITICAL** |
| **Configure connection limits** | ✅ HTTPClientPool has Limits config | ✅ Yes |
| **Use single client for reuse** | ❌ No client reuse across operations | ❌ **CRITICAL** |
| **Proper timeout configuration** | ✅ Granular timeouts (connect/read/write/pool) | ✅ Yes |
| **HTTP/2 for multiplexing** | ❌ Disabled (http2=False default) | ⚠️ Opportunity |

**Context7 Quote:**
> "Avoid creating multiple client instances within hot loops to ensure efficient connection pooling."

**Current Violation:**
```python
# docker_sandbox.py:33 - Creates new client per sandbox instance
class DockerSandbox(Sandbox):
    def __init__(self, ip: str | None = None, container_name: str | None = None):
        self._client: httpx.AsyncClient | None = httpx.AsyncClient(timeout=600)  # ❌
```

### FastAPI Best Practices (/websites/fastapi_tiangolo - Score: 96.8)

| Best Practice | Current State | Compliant? |
|--------------|---------------|------------|
| **Use lifespan context manager** | ❌ Not implemented | ❌ **CRITICAL** |
| **Manage shared resources** | ❌ No HTTPClientPool initialization | ❌ **CRITICAL** |
| **Async startup/shutdown** | ⚠️ Using deprecated on_event (if any) | ⚠️ Needs update |

**Context7 Quote:**
> "The lifespan parameter is the recommended approach for handling application startup and shutdown events. on_startup and on_shutdown are deprecated."

**Missing Implementation:**
```python
# main.py - No lifespan management for HTTPClientPool
app = FastAPI()  # ❌ Should use lifespan parameter
```

---

## Architecture Design

### Current State (Anti-Pattern)

```
┌─────────────────────────────────────────────────┐
│           Pythinker Backend (FastAPI)           │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌─────────────┐  ┌─────────────┐             │
│  │ DockerSandbox│  │ DockerSandbox│   (Each    │
│  │  Instance 1  │  │  Instance 2  │    creates │
│  │              │  │              │    own      │
│  │ httpx.Client │  │ httpx.Client │   client)  │
│  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                     │
│         │  ❌ No Pooling  │                     │
│         │                 │                     │
└─────────┼─────────────────┼─────────────────────┘
          │                 │
          ▼                 ▼
    ┌─────────┐       ┌─────────┐
    │Sandbox 1│       │Sandbox 2│
    │  :8080  │       │  :8080  │
    └─────────┘       └─────────┘

Issues:
- New TCP connections for every operation
- Memory overhead per client instance
- No connection reuse
- No centralized metrics
```

### Target State (Best Practice)

```
┌─────────────────────────────────────────────────┐
│           Pythinker Backend (FastAPI)           │
│                                                 │
│  ┌───────────────────────────────────────────┐ │
│  │        HTTPClientPool (Singleton)         │ │
│  │  ┌─────────────┐  ┌─────────────┐        │ │
│  │  │sandbox-1    │  │sandbox-2    │        │ │
│  │  │ManagedClient│  │ManagedClient│        │ │
│  │  │ (pooled)    │  │ (pooled)    │        │ │
│  │  └─────────────┘  └─────────────┘        │ │
│  │                                           │ │
│  │  ✅ Connection Reuse                      │ │
│  │  ✅ Lifecycle Management                  │ │
│  │  ✅ Centralized Metrics                   │ │
│  └───────────────────────────────────────────┘ │
│         │                 │                     │
│  ┌──────▼─────┐    ┌──────▼─────┐              │
│  │DockerSandbox│    │DockerSandbox│             │
│  │ (uses pool) │    │ (uses pool) │             │
│  └─────────────┘    └─────────────┘             │
└─────────┼─────────────────┼─────────────────────┘
          │                 │
          ▼                 ▼
    ┌─────────┐       ┌─────────┐
    │Sandbox 1│       │Sandbox 2│
    │  :8080  │       │  :8080  │
    └─────────┘       └─────────┘

Benefits:
- Connection reuse (1-5ms vs 10-30ms)
- Shared memory pool
- Centralized stats/metrics
- Proper cleanup on shutdown
```

---

## Implementation Phases

### Phase 1: Foundation (Lifespan & Metrics) - Priority: P0

**Goal:** Add FastAPI lifespan management and observability

**Tasks:**
1. ✅ Add lifespan async context manager to `main.py`
2. ✅ Initialize HTTPClientPool on startup
3. ✅ Cleanup pool on shutdown
4. ✅ Add Prometheus metrics for pool stats
5. ✅ Add logging for lifecycle events

**Files Modified:**
- `backend/app/main.py`
- `backend/app/infrastructure/observability/prometheus_metrics.py`

**Example Implementation:**
```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.infrastructure.external.http_pool import HTTPClientPool

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize shared resources
    logger.info("Initializing HTTP client pool...")

    # Pre-warm critical clients (optional)
    await HTTPClientPool.get_client(
        name="default-sandbox",
        base_url="http://localhost:8080",
        timeout=600.0,
    )

    yield

    # Shutdown: Cleanup all clients
    count = await HTTPClientPool.close_all()
    logger.info(f"Closed {count} HTTP clients")

app = FastAPI(lifespan=lifespan)
```

**Acceptance Criteria:**
- [ ] FastAPI starts/stops without errors
- [ ] HTTPClientPool.close_all() called on shutdown
- [ ] Metrics exposed at /metrics endpoint
- [ ] Logs show initialization/cleanup

**Estimated Effort:** 4 hours
**Risk:** Low (additive, no breaking changes)

---

### Phase 2: DockerSandbox Migration - Priority: P0

**Goal:** Migrate DockerSandbox to use HTTPClientPool

**Tasks:**
1. ✅ Remove `self._client` from `__init__`
2. ✅ Convert `client` property to async method
3. ✅ Update all callsites to use pooled client
4. ✅ Add sandbox-specific pool configuration
5. ✅ Update `destroy()` to release pool connections
6. ✅ Add unit tests for pooled behavior

**Files Modified:**
- `backend/app/infrastructure/external/sandbox/docker_sandbox.py`
- `backend/app/core/sandbox_pool.py` (if needed)

**Breaking Change:**
```python
# BEFORE
class DockerSandbox(Sandbox):
    def __init__(self, ...):
        self._client = httpx.AsyncClient(timeout=600)

    async def exec_command(self, ...):
        response = await self.client.post(...)  # sync property

# AFTER
class DockerSandbox(Sandbox):
    def __init__(self, ...):
        self._pool_client_name = f"sandbox-{self.id}"

    async def get_client(self) -> ManagedHTTPClient:
        return await HTTPClientPool.get_client(
            name=self._pool_client_name,
            base_url=self.base_url,
            timeout=600.0,
            config=HTTPClientConfig(
                max_connections=10,
                max_keepalive_connections=5,
                connect_timeout=5.0,
                read_timeout=30.0,
            )
        )

    async def exec_command(self, ...):
        client = await self.get_client()
        response = await client.post(...)  # async method
```

**Migration Strategy:**
1. Add `get_client()` method alongside existing `client` property
2. Migrate callsites one-by-one to `await self.get_client()`
3. Run tests after each migration
4. Remove old `client` property once all callsites migrated

**Acceptance Criteria:**
- [ ] All sandbox operations use pooled clients
- [ ] Connection reuse verified (pool stats show <10 clients for 100+ operations)
- [ ] Latency improvement measured (expect 15-25ms reduction per call)
- [ ] No memory leaks (run for 1000 sessions, memory stable)
- [ ] All tests pass

**Estimated Effort:** 8 hours
**Risk:** Medium (breaking change, requires careful testing)

---

### Phase 3: HTTP/2 Evaluation - Priority: P1

**Goal:** Evaluate HTTP/2 for sandbox communication

**Tasks:**
1. ✅ Check sandbox API HTTP/2 support
2. ✅ Add feature flag `sandbox_http2_enabled`
3. ✅ Install httpx[http2] (h2 library)
4. ✅ Benchmark HTTP/1.1 vs HTTP/2
5. ✅ Document performance results

**Files Modified:**
- `backend/app/core/config.py`
- `backend/requirements.txt`
- `docs/benchmarks/HTTP2_EVALUATION.md`

**Configuration:**
```python
# config.py
class Settings(BaseSettings):
    # HTTP/2 Configuration
    sandbox_http2_enabled: bool = False  # Feature flag

# http_pool.py
async def get_sandbox_client():
    settings = get_settings()
    return await HTTPClientPool.get_client(
        name=f"sandbox-{sandbox_id}",
        config=HTTPClientConfig(
            http2=settings.sandbox_http2_enabled,  # Controlled by flag
            max_connections=10,
        )
    )
```

**Benchmark Plan:**
```python
# Compare 100 concurrent requests
# HTTP/1.1: Sequential over 5 keepalive connections
# HTTP/2: Multiplexed over 1 connection

async def benchmark():
    tasks = [
        client.get(f"/api/v1/file/list?path=/home/ubuntu")
        for _ in range(100)
    ]
    start = time.perf_counter()
    await asyncio.gather(*tasks)
    duration = time.perf_counter() - start
    print(f"Total: {duration:.2f}s, Avg: {duration/100*1000:.2f}ms")
```

**Expected Results:**
- **HTTP/1.1:** ~3-5s total (sequential pipelining)
- **HTTP/2:** ~2-3s total (multiplexing) - 30-40% improvement

**Acceptance Criteria:**
- [ ] Feature flag controls HTTP/2 usage
- [ ] Performance benchmarks documented
- [ ] Fallback to HTTP/1.1 if h2 not installed
- [ ] Decision documented (enable or keep disabled)

**Estimated Effort:** 6 hours
**Risk:** Low (behind feature flag)

---

### Phase 4: Service-Wide Adoption - Priority: P2

**Goal:** Migrate other services to HTTPClientPool

**Services to Migrate:**
1. **Search APIs** (Tavily, Serper, Brave, etc.)
2. **Alert Webhooks** (if using httpx directly)
3. **External APIs** (non-LLM integrations)

**Note:** LLM providers (OpenAI SDK) already use internal connection pooling, so migration not needed.

**Files Modified:**
- `backend/app/infrastructure/external/search/*.py`
- `backend/app/infrastructure/observability/alerting.py` (if exists)

**Example Migration:**
```python
# BEFORE (tavily_search.py)
class TavilySearch:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)  # ❌

# AFTER
class TavilySearch:
    async def get_client(self) -> ManagedHTTPClient:
        return await HTTPClientPool.get_client(
            name="tavily-search",
            base_url="https://api.tavily.com",
            timeout=30.0,
        )
```

**Acceptance Criteria:**
- [ ] All external HTTP calls use HTTPClientPool
- [ ] Pool stats show expected client count
- [ ] No performance regressions

**Estimated Effort:** 8 hours
**Risk:** Low (isolated changes)

---

### Phase 5: Testing & Documentation - Priority: P0

**Goal:** Comprehensive testing and documentation

**Testing Tasks:**
1. ✅ Unit tests for HTTPClientPool
2. ✅ Integration tests for DockerSandbox pooling
3. ✅ Performance benchmarks
4. ✅ Memory leak tests (long-running sessions)
5. ✅ Pool exhaustion tests (PoolTimeout handling)

**Documentation Tasks:**
1. ✅ Create `docs/architecture/HTTP_CLIENT_POOLING.md`
2. ✅ Update `CLAUDE.md` with pooling guidelines
3. ✅ Update `docs/guides/PYTHON_STANDARDS.md`
4. ✅ Add troubleshooting guide

**Test Coverage Target:** >90% for http_pool.py

**Acceptance Criteria:**
- [ ] All tests pass
- [ ] Coverage meets target
- [ ] Documentation reviewed and approved
- [ ] Migration guide tested by another developer

**Estimated Effort:** 12 hours
**Risk:** Low

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Breaking changes in DockerSandbox** | High | Gradual migration, feature flag, thorough testing |
| **Pool exhaustion under load** | Medium | Proper timeout config, monitoring, alerts |
| **Memory leaks from unclosed clients** | Medium | Lifespan cleanup, automated leak tests |
| **Performance regression** | Low | Benchmarking before/after, rollback plan |
| **HTTP/2 compatibility issues** | Low | Feature flag, fallback to HTTP/1.1 |

---

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| **Sandbox API Latency (p50)** | 15-25ms | <10ms | Prometheus histogram |
| **Active HTTP Clients** | ~50-100 | <20 | HTTPClientPool.get_all_stats() |
| **Memory per Session** | ~150MB | ~140MB | Docker stats |
| **Connection Reuse Rate** | 0% | >80% | Pool stats (use_count) |
| **Pool Exhaustion Events** | N/A | <0.1% | Prometheus counter |

---

## Rollout Plan

### Week 1: Foundation
- [ ] Day 1-2: Implement Phase 1 (FastAPI lifespan)
- [ ] Day 3-4: Add metrics and monitoring
- [ ] Day 5: Testing and validation

### Week 2: Core Migration
- [ ] Day 1-3: Implement Phase 2 (DockerSandbox)
- [ ] Day 4: Integration testing
- [ ] Day 5: Performance benchmarking

### Week 3: Optimization & Expansion
- [ ] Day 1-2: Phase 3 (HTTP/2 evaluation)
- [ ] Day 3-4: Phase 4 (service-wide adoption)
- [ ] Day 5: Final testing

### Week 4: Documentation & Release
- [ ] Day 1-2: Complete documentation
- [ ] Day 3: Code review
- [ ] Day 4: Staging deployment
- [ ] Day 5: Production rollout (canary → full)

**Total Timeline:** 4 weeks
**Total Effort:** ~48 hours engineering

---

## Rollback Plan

**If issues arise in production:**

1. **Immediate:** Disable HTTP/2 (set `sandbox_http2_enabled=False`)
2. **Short-term:** Revert DockerSandbox to direct client (keep lifespan)
3. **Full Rollback:** Revert entire integration (git revert to baseline)

**Rollback Triggers:**
- >5% increase in error rate
- >20% increase in p99 latency
- Memory leak detected (>10% growth over 1 hour)
- Pool exhaustion rate >1%

---

## References

### Context7 MCP Documentation
- **httpx:** `/encode/httpx` (Score: 81.4, High Reputation)
  - Connection pooling best practices
  - AsyncClient lifecycle management
  - HTTP/2 multiplexing
  - Timeout configuration

- **FastAPI:** `/websites/fastapi_tiangolo` (Score: 96.8, High Reputation)
  - Lifespan context manager pattern
  - Dependency injection for shared resources
  - Testing with TestClient

### Research Report
- "Inter-Service Communication in Python (gRPC vs. HTTP/REST)"
- Key recommendation: Start with HTTP/REST + httpx, migrate to gRPC only when latency becomes bottleneck

### Internal Documentation
- `backend/app/infrastructure/external/http_pool.py` - Implementation
- `docs/guides/PYTHON_STANDARDS.md` - Coding standards
- `CLAUDE.md` - Project guidelines

---

## Approval

**Reviewed By:**
- [ ] Backend Lead
- [ ] DevOps Engineer
- [ ] QA Lead

**Approved By:**
- [ ] Engineering Manager
- [ ] Product Owner

**Date:** ______________

---

## Appendix A: HTTPClientPool API Reference

### Key Methods

```python
class HTTPClientPool:
    @classmethod
    async def get_client(
        cls,
        name: str,
        base_url: str | None = None,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        config: HTTPClientConfig | None = None,
    ) -> ManagedHTTPClient:
        """Get or create an HTTP client for a service."""

    @classmethod
    async def close_all(cls) -> int:
        """Close all HTTP clients. Returns count closed."""

    @classmethod
    def get_all_stats(cls) -> dict[str, dict[str, Any]]:
        """Get statistics for all clients."""
```

### HTTPClientConfig

```python
@dataclass
class HTTPClientConfig:
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
    max_retries: int = 3
    retry_statuses: tuple = (429, 500, 502, 503, 504)

    verify_ssl: bool = True
    http2: bool = False  # Enable for HTTP/2 support
```

---

## Appendix B: Performance Benchmark Results

*To be filled after Phase 3 completion*

| Scenario | HTTP/1.1 | HTTP/2 | Improvement |
|----------|----------|--------|-------------|
| Single Request | TBD | TBD | TBD |
| 10 Sequential | TBD | TBD | TBD |
| 100 Concurrent | TBD | TBD | TBD |
| Connection Reuse | TBD | TBD | TBD |

---

**Plan Version:** 1.0
**Last Updated:** 2026-02-11
**Next Review:** 2026-02-18
