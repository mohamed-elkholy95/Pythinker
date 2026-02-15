# Clean Code and Clean Architecture Guidelines for Pythinker

## Table of Contents

1. Why this architecture is critical in Pythinker
2. Clean architecture blueprint for this stack
3. Layer boundary rules (hard constraints)
4. Backend guidelines (FastAPI, Pydantic v2, asyncio)
5. Data and integration guidelines (MongoDB, Redis, Qdrant, MinIO, SSE)
6. AI and browser automation guidelines (OpenAI, Anthropic, Playwright)
7. Frontend guidelines (Vue 3, TypeScript, Vite, Vitest)
8. Security, observability, and delivery gates
9. Pull request review checklist

## 1. Why this architecture is critical in Pythinker

Pythinker combines:

- FastAPI orchestration and streaming APIs
- Async I/O across multiple stores and providers
- MongoDB + Redis + Qdrant + object storage
- LLM providers (Anthropic/OpenAI)
- Browser automation/sandbox execution

This is an integration-heavy system where failures cluster at boundaries: network calls, queues, retries, and streaming cancellation. Clean architecture reduces accidental coupling, improves testability, and limits regression blast radius.

## 2. Clean architecture blueprint for this stack

Use dependency direction only inward:

- Domain -> Application -> Infrastructure -> Interfaces (inward imports only)

Example shape:

```text
pythinker/
  domain/
    entities.py
    value_objects.py
    events.py
    errors.py
    services.py
  application/
    ports/
      llm.py
      search.py
      storage.py
      clock.py
    use_cases/
      run_agent.py
      stream_session.py
    dto/
  infrastructure/
    mongo/
      documents.py
      repositories.py
    redis/
      cache.py
      runtime_state.py
    qdrant/
      vector_store.py
      bm25.py
    minio/
      object_store.py
    llm/
      openai_client.py
      anthropic_client.py
    browser/
      playwright_driver.py
      sandbox_client.py
  interfaces/
    api/
      routers/
      schemas/
      dependencies.py
      sse.py
      websocket.py
  main.py
```

Folder names can vary; dependency direction cannot.

## 3. Layer boundary rules (hard constraints)

### Domain

- Keep domain free of FastAPI, Starlette, ODM/DB SDKs, and provider SDK imports.
- Encode business rules, invariants, domain errors, and value objects only.

### Application

- Implement use-case orchestration.
- Depend on domain + ports (protocols/interfaces), not concrete adapters.
- Return typed DTOs/results rather than framework responses.

### Infrastructure

- Implement ports for external systems.
- Handle DB I/O, cache access, vector retrieval, object storage, provider SDK calls, browser automation.
- Keep translation/mapping logic close to adapters.

### Interfaces

- Parse/validate transport payloads.
- Delegate to application use-cases.
- Keep route handlers thin.
- Map application results/errors to HTTP/SSE/WebSocket responses.

## 4. Backend guidelines (FastAPI, Pydantic v2, asyncio)

### 4.1 FastAPI app assembly and lifecycle

- Split routers/modules; avoid monolithic `main.py` logic.
- Use `lifespan` with async context manager for startup/shutdown resources.
- Create shared clients once and close them cleanly.

Example:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = make_httpx_client()
    app.state.mongo = make_mongo_client()
    yield
    await app.state.http.aclose()
    app.state.mongo.close()

app = FastAPI(lifespan=lifespan)
```

### 4.2 Dependency injection and testability

- Inject abstractions using `Depends`.
- Override dependencies in tests via `app.dependency_overrides`.
- Replace LLM/search/storage dependencies with fakes in API tests.

### 4.3 Pydantic v2 boundaries

- Keep validation at boundaries: API schemas, infra documents, DTO contracts.
- Configure with `model_config = ConfigDict(...)`.
- Use `@field_validator` with `@classmethod`.
- Prefer explicit strictness where needed:
  - `extra="forbid"` for inbound request models
  - `frozen=True` for immutable DTO/event objects
  - `validate_assignment=True` where post-init mutation is expected

### 4.4 Async safety and reliability

- Bound all outbound calls by timeout budgets.
- Configure HTTPX with explicit connect/read/write/pool timeout components.
- Configure connection pool limits.
- Use `asyncio.TaskGroup` for fan-out workflows.
- Ensure cancellation propagates through streaming and background tasks.

HTTPX pattern:

```python
import httpx

timeout = httpx.Timeout(
    10.0,
    connect=5.0,
    read=30.0,
    write=10.0,
    pool=5.0,
)
limits = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=100,
    keepalive_expiry=5.0,
)
client = httpx.AsyncClient(timeout=timeout, limits=limits)
```

### 4.5 Readability baseline

- Keep implementations explicit and boring.
- Prefer small composable functions over large orchestrators.
- Use full type hints.
- Avoid hidden mutable global state.

## 5. Data and integration guidelines

### 5.1 MongoDB + Beanie

- Keep Beanie `Document` models in infrastructure.
- Initialize Beanie once in lifespan startup.
- Map `Document` <-> domain entities in repositories.
- Do not leak DB-only fields into domain entities.

### 5.2 Redis

- Separate runtime state from cache responsibilities.
- Define key naming/versioning and TTL policy explicitly.
- Use persistence strategy appropriate to data criticality.

### 5.3 Qdrant hybrid retrieval

Implement staged retrieval pipeline:

1. Candidate generation (dense + sparse)
2. Score fusion
3. Reranking

Persist score/rationale metadata for observability and debugging.

### 5.4 MinIO/object storage

- Use pre-signed URLs for upload/download flows.
- Keep credentials server-side.
- Expose only short-lived access artifacts to clients.

### 5.5 SSE/WebSocket streaming

- Use explicit event contracts (versioned schema).
- Emit structured error events; never stream raw exceptions.
- Exit quickly on disconnect and cancel child tasks.

## 6. AI and browser automation guidelines

### 6.1 Provider abstraction

- Define one internal `LLMClient` port.
- Implement provider adapters in infrastructure.
- Keep provider-specific knobs out of domain/application logic.

### 6.2 Rate limits and retries

- Apply request throttling and per-user/session budgets.
- Retry only retryable failures (timeouts, 429, transient 5xx).
- Keep explicit timeout budgets on provider requests.

### 6.3 Playwright isolation

- Use browser contexts to isolate sessions.
- Keep deterministic cleanup/teardown.
- Avoid brittle automation tied to implementation details.

### 6.4 Sandbox safety

- Never inject long-lived production secrets into sandbox contexts.
- Prefer short-lived credentials (tokens, pre-signed URLs).
- Enforce CPU/memory/pid/network constraints consistent with threat model.

## 7. Frontend guidelines (Vue 3, TypeScript, Vite, Vitest)

### 7.1 Composition API architecture

- Keep components mostly presentational.
- Put orchestration and side effects in focused composables (`useX`).
- One composable, one concern.

### 7.2 Resource cleanup

- Close SSE/WebSocket connections on unmount.
- Abort pending requests when no longer needed.
- Clear timers and listeners.

### 7.3 Type safety

- Use strict TypeScript settings.
- Avoid `any`.
- Handle nullable/late-arriving async state explicitly.

### 7.4 Environment boundaries

- Treat `import.meta.env` as public client config only.
- Keep secrets and credentials on server-side boundaries.

### 7.5 Testing strategy

- Unit test composables as primary behavior unit.
- Keep component tests focused on rendering and core interactions.
- Mock streams and timers deterministically.

## 8. Security, observability, and delivery gates

### 8.1 JWT and API security

- Centralize token encode/decode/verification.
- Enforce explicit algorithms, issuer, audience, and expiry checks.
- Do not place sensitive data in token payloads unless explicitly acceptable.

### 8.2 Structured logging

- Emit canonical structured events for lifecycle steps:
  - session start/finish
  - tool invocation and latency
  - provider request metadata
  - sandbox lifecycle and limits
- Avoid secret leakage in logs.

### 8.3 Metrics and labels

- Keep metric names consistent and dimensionality low.
- Avoid high-cardinality labels (e.g., `user_id`, `session_id`).
- Keep dynamic identifiers in logs/traces, not metric labels.

### 8.4 Container/runtime baseline

- Prefer small trusted base images.
- Use multi-stage builds.
- Run as non-root when possible.

### 8.5 Local quality gates

Backend:

```bash
conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
```

Frontend:

```bash
cd frontend && bun run lint && bun run type-check
```

Single pytest target without coverage:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/test_file.py
```

## 9. Pull request review checklist

Use this checklist before merge:

1. Are layer boundaries respected (no outward dependency leaks)?
2. Are route handlers thin and delegated to use-cases?
3. Is boundary validation explicit and minimal (no Pydantic spread into domain)?
4. Are async operations timeout-bounded and cancellation-safe?
5. Are external provider calls abstracted behind ports/adapters?
6. Are logs structured, safe, and useful for incident analysis?
7. Are metrics low-cardinality and naming-consistent?
8. Are tests added/updated at the correct layer?
9. Are project-mandated lint/type/test checks passing?

## Context7 Validation Note

Before final handoff, validate framework-specific implementation details using Context7 docs for the exact library versions used in this repository.
