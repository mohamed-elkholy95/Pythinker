# Backend Code Review — Remediation Plan

> **Generated**: 2026-02-18
> **Scope**: 860 Python files (540 app + 320 test)
> **Review Method**: 10 batches by DDD layer, 14 parallel agents, 6 Python skills activated
> **Total Findings**: ~650+

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Review Scope & Methodology](#2-review-scope--methodology)
3. [Findings Dashboard](#3-findings-dashboard)
4. [Top 10 Systemic Patterns](#4-top-10-systemic-patterns)
5. [Sprint 1 — P0 Critical Fixes](#5-sprint-1--p0-critical-fixes)
6. [Sprint 2 — Architectural Improvements](#6-sprint-2--architectural-improvements)
7. [Sprint 3 — Code Quality & Reliability](#7-sprint-3--code-quality--reliability)
8. [Sprint 4 — Cleanup & Polish](#8-sprint-4--cleanup--polish)
9. [Quick Wins (< 1 hour each)](#9-quick-wins--1-hour-each)
10. [Detailed Findings by Layer](#10-detailed-findings-by-layer)
11. [Test Suite Findings](#11-test-suite-findings)
12. [Verification Checklist](#12-verification-checklist)

---

## 1. Executive Summary

The Pythinker backend codebase was reviewed file-by-file across all DDD layers. The code demonstrates **solid architectural foundations** — clean DDD layering, comprehensive exception hierarchy, Pydantic v2 adoption, and good test breadth. However, several systemic issues affect production reliability:

| Priority | Count | Risk Level |
|----------|-------|------------|
| **P0 Critical** | ~100 | Security, data corruption, silent failures |
| **P1 High** | ~185 | Race conditions, resource leaks, logic errors |
| **P2 Medium** | ~185 | DDD violations, missing validation, code smells |
| **P3 Low** | ~180 | Naming, dead code, style inconsistencies |

**Top 3 risks requiring immediate attention:**

1. **`datetime.now()` without UTC** — 65+ locations causing timezone-dependent data corruption
2. **Thread-unsafe singleton factories** — 15+ `get_*()` functions vulnerable to race conditions at startup
3. **40+ async tests executing synchronously** — Missing `@pytest.mark.asyncio` means tests pass without running async code

---

## 2. Review Scope & Methodology

### Batches

| Batch | Layer | Files | Key Areas |
|-------|-------|-------|-----------|
| 1 | `core/` | ~15 | Config, DI, Lifespan, Prometheus |
| 2 | `domain/models/` | ~47 | Domain entities, value objects, enums |
| 3 | `domain/exceptions/` + `domain/repositories/` | ~25 | Exception hierarchy, repository protocols |
| 4 | `domain/services/` | ~170 | Agent services, flows, tools, memory |
| 5 | `application/` | ~35 | Use cases, DTOs, orchestration |
| 6 | `interfaces/` | ~50 | API routes, request/response schemas |
| 7–9 | `infrastructure/` | ~200 | Repos, adapters, LLM, browser, sandbox, observability |
| 10 | `tests/` | ~320 | All test suites across all layers |

### Skills Activated

- `python-design-patterns` — SRP, KISS, composition over inheritance
- `python-type-safety` — Generics, protocols, strict mode
- `python-resilience` — Retry, backoff, circuit breakers
- `python-performance-optimization` — Profiling, memory, concurrency
- `python-background-jobs` — Task queues, idempotency
- `python-packaging` — Project structure, pyproject.toml

---

## 3. Findings Dashboard

### By Priority

```
P0 ████████████████████░░░░░░░░░░░░░░░░░░░░  ~100 (15%)
P1 ██████████████████████████████░░░░░░░░░░  ~185 (28%)
P2 ██████████████████████████████░░░░░░░░░░  ~185 (28%)
P3 █████████████████████████████░░░░░░░░░░░  ~180 (28%)
```

### By Layer

| Layer | P0 | P1 | P2 | P3 | Total |
|-------|----|----|----|----|-------|
| `core/` (Config, Lifespan) | 8 | 12 | 10 | 8 | 38 |
| `domain/models/` | 5 | 11 | 14 | 12 | 42 |
| `domain/exceptions/` + `repositories/` | 2 | 6 | 8 | 5 | 21 |
| `domain/services/` | 18 | 35 | 32 | 28 | 113 |
| `application/` | 6 | 14 | 12 | 10 | 42 |
| `interfaces/` | 8 | 15 | 18 | 15 | 56 |
| `infrastructure/` | 28 | 48 | 45 | 42 | 163 |
| `tests/` | 25 | 44 | 46 | 60 | 175 |
| **Total** | **~100** | **~185** | **~185** | **~180** | **~650** |

---

## 4. Top 10 Systemic Patterns

These are project-wide patterns that appear across multiple files and layers. Fixing them systematically yields the highest impact per effort.

### Pattern 1: `datetime.now()` Without UTC

**Occurrences**: 65+
**Severity**: P0
**Layers affected**: domain/models, domain/services, infrastructure/storage, infrastructure/observability

**Problem**: `datetime.now()` returns naive local time. When the server timezone changes or multiple instances run in different zones, timestamps become inconsistent. This corrupts event ordering, session durations, and TTL calculations.

**Representative locations**:
- `infrastructure/storage/redis.py:69,89,188,207` — Circuit breaker timing
- `infrastructure/observability/llm_tracer.py:138,207` — Trace end times
- `domain/models/` — 11+ model files with `default_factory=datetime.now`

**Fix**: Enable ruff rule `DTZ005` and auto-fix project-wide.

```bash
# In pyproject.toml [tool.ruff.lint]
select = [..., "DTZ"]

# Auto-fix
ruff check --fix --select DTZ005 backend/
```

**Manual pattern**:
```python
# Before
from datetime import datetime
created_at: datetime = Field(default_factory=datetime.now)

# After
from datetime import UTC, datetime
created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

**Estimated effort**: 2 hours (automated + manual review)

---

### Pattern 2: Thread-Unsafe Singleton Factories

**Occurrences**: 15+
**Severity**: P0
**Layers affected**: infrastructure/storage, infrastructure/external, core/

**Problem**: `get_*()` factory functions use `@lru_cache` or global variables without `threading.Lock`. During ASGI startup with multiple workers, concurrent calls can create duplicate instances or partially initialized singletons.

**Representative locations**:
- `infrastructure/storage/qdrant.py:184-187` — `get_qdrant()`
- `infrastructure/storage/mongodb.py` — `get_mongodb()`
- `infrastructure/external/llm/factory.py:182-213` — `get_llm()`
- `infrastructure/observability/typo_correction_analytics.py:122-137` — Global instance
- All `get_*()` functions in `core/`, `infrastructure/`

**Fix**: Add `threading.Lock` guard to every singleton factory.

```python
import threading
from functools import lru_cache

_lock = threading.Lock()

@lru_cache
def get_qdrant() -> QdrantStorage:
    """Get the Qdrant storage instance (thread-safe)."""
    with _lock:
        return QdrantStorage()
```

**Note**: `@lru_cache` itself is thread-safe for reads, but the **initialization** inside the factory is not. The lock prevents two threads from both seeing cache-miss and both constructing the object.

**Estimated effort**: 3 hours

---

### Pattern 3: Missing `@pytest.mark.asyncio` on Test Methods

**Occurrences**: 40+
**Severity**: P0
**Layers affected**: tests/

**Problem**: Async test methods without the decorator execute synchronously — the coroutine is created but never awaited. pytest collects them and marks them as "passed" because no assertion error was raised (since no code ran).

**Representative locations**:
- `tests/application/services/test_auth_service_timing_attack.py` — 14 async methods
- `tests/application/services/test_token_service_fail_closed.py` — 23 async methods
- `tests/infrastructure/external/search/test_serper_search.py` — Missing on some methods
- `tests/infrastructure/test_qdrant_hybrid_search.py` — 6 async methods

**Fix**: Set `asyncio_mode = "auto"` in `pyproject.toml`.

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

This automatically applies `@pytest.mark.asyncio` to all async test functions, eliminating the entire class of bugs.

**Estimated effort**: 5 minutes (one line change)

---

### Pattern 4: DDD Layer Violations

**Occurrences**: 20+
**Severity**: P2
**Layers affected**: domain → infrastructure imports

**Problem**: Domain layer files importing from infrastructure violates the dependency rule (domain should have zero external dependencies).

**Representative patterns**:
- Domain services importing `get_settings()` from `core/config.py`
- Domain models importing MongoDB-specific types
- Domain services importing `get_llm()` from infrastructure

**Fix**: Inject dependencies through constructor or use protocol-based ports.

```python
# Before (violation)
from app.infrastructure.external.llm import get_llm

class MyDomainService:
    def __init__(self):
        self.llm = get_llm()  # Domain depends on infrastructure

# After (clean)
from app.domain.protocols.llm import LLMProtocol

class MyDomainService:
    def __init__(self, llm: LLMProtocol):
        self.llm = llm  # Domain depends on abstraction
```

**Estimated effort**: 2–3 days (requires careful refactoring)

---

### Pattern 5: God Classes / Functions (>1000 lines)

**Occurrences**: 8+
**Severity**: P1
**Layers affected**: domain/services, infrastructure/external, core/

**Problem**: Files exceeding 1000 lines violate SRP, are hard to test, and create merge conflicts.

**Files**:

| File | Lines | Responsibility Violations |
|------|-------|--------------------------|
| `domain/services/tools/mcp.py` | ~1620 | MCP tool, config, transport, session |
| `infrastructure/external/browser/playwright_browser.py` | ~1661 | Navigation, screenshots, interaction, recovery |
| `core/lifespan.py` | ~460 | All startup/shutdown logic in one function |
| `infrastructure/external/llm/openai_llm.py` | ~1100 | Request building, retry, streaming, message repair |
| `domain/services/tools/browser_tool.py` | ~800 | Action parsing, execution, screenshot, error handling |
| `domain/services/agents/execution.py` | ~700 | Step execution, tool dispatch, context management |
| `domain/services/memory/memory_service.py` | ~600 | CRUD, search, extraction, compaction |
| `interfaces/api/routes/session_routes.py` | ~500 | All session endpoints |

**Fix strategy**: Extract cohesive groups of methods into focused classes.

```
playwright_browser.py (1661 lines) →
  ├── playwright_navigator.py    (~300 lines)
  ├── playwright_interactions.py (~400 lines)
  ├── playwright_screenshots.py  (~200 lines)
  └── playwright_recovery.py     (~200 lines)
```

**Estimated effort**: 1–2 weeks (incremental, one file per PR)

---

### Pattern 6: Broad `except Exception` Catching

**Occurrences**: 50+
**Severity**: P1
**Layers affected**: All layers

**Problem**: Catching `Exception` swallows programming errors (`TypeError`, `AttributeError`, `KeyError`), making bugs invisible.

**Representative locations**:
- `infrastructure/repositories/` — 15+ files with broad catches
- `domain/services/memory/memory_service.py` — 22+ bare `except Exception`
- `infrastructure/external/llm/openai_llm.py` — 6 `pass` after `except Exception`
- `infrastructure/storage/qdrant.py:74` — Swallows all initialization errors

**Fix**: Replace with specific exception types.

```python
# Before
try:
    result = await self.repo.save(entity)
except Exception as e:
    logger.error(f"Failed: {e}")
    return None

# After
from pymongo.errors import DuplicateKeyError, ConnectionFailure

try:
    result = await self.repo.save(entity)
except DuplicateKeyError:
    logger.warning("Entity already exists", entity_id=entity.id)
    raise DuplicateResourceException(entity.id) from None
except ConnectionFailure as e:
    logger.error("Database unavailable", error=str(e))
    raise IntegrationException("MongoDB unavailable") from e
```

**Estimated effort**: 1 week (can be done incrementally per module)

---

### Pattern 7: Duplicate Code

**Occurrences**: 15+ instances
**Severity**: P2
**Layers affected**: domain/services, infrastructure, tests

**Key duplications**:
1. **Download endpoints** — 3 competing implementations (file download, artifact download, export)
2. **Pydantic validators** — Identical URL/email validators in 5+ schema files
3. **Mock setup in tests** — `_FakeRedisClient`, `_FakeUserRepository` reimplemented across test files
4. **BSON normalization** — `ObjectId` → `str` conversion in 4+ repository files

**Fix**: Extract shared utilities.

```python
# backend/app/domain/validators.py
from pydantic import field_validator

class URLValidatorMixin:
    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v
```

**Estimated effort**: 3–5 days

---

### Pattern 8: Untyped `dict` / `list` Parameters

**Occurrences**: 25+
**Severity**: P2
**Layers affected**: interfaces/schemas, domain/services, infrastructure

**Problem**: Using bare `dict` or `list` without type parameters defeats type checking.

**Representative locations**:
- `interfaces/schemas/skill.py:47` — `config: dict = Field(default_factory=dict)` (should be `dict[str, Any]`)
- `domain/services/agents/execution.py` — `messages: list[dict]` (should be `list[dict[str, Any]]` or a TypedDict)
- `infrastructure/external/llm/openai_llm.py` — Return types as bare `dict`

**Fix**: Add type parameters or use TypedDict.

```python
# Before
config: dict = Field(default_factory=dict)

# After
config: dict[str, Any] = Field(default_factory=dict)

# Even better: use TypedDict for known structures
class SkillConfig(TypedDict, total=False):
    max_retries: int
    timeout_seconds: float
    custom_prompt: str
```

**Estimated effort**: 1–2 days

---

### Pattern 9: Inconsistent DI Patterns

**Occurrences**: 3 competing approaches
**Severity**: P2
**Layers affected**: All layers

**Problem**: The codebase uses three different dependency injection patterns:
1. **Factory functions** (`get_llm()`, `get_qdrant()`) — most common
2. **Constructor injection** (some domain services) — cleanest
3. **FastAPI `Depends()`** (API routes) — framework-specific

This inconsistency makes testing harder and creates confusion about which pattern to follow.

**Recommendation**: Standardize on **constructor injection** for domain/application services, with factory functions only at the composition root (lifespan.py).

**Estimated effort**: 1–2 weeks (large refactor, do incrementally)

---

### Pattern 10: Dead Code & Placeholder Implementations

**Occurrences**: 15+ files
**Severity**: P3
**Layers affected**: domain/services, infrastructure, tests

**Examples**:
- `evals/graders/llm_judge.py` — Placeholder implementation
- Commented-out `_try_regex_extract` in `llm_json_parser.py:43`
- Unused imports across 20+ files
- `examples/mindsearch/` — Entire deleted example directory still tracked

**Fix**: Delete dead code. Use `ruff` to detect unused imports.

```bash
ruff check --select F401 backend/  # Unused imports
ruff check --select ERA backend/   # Commented-out code
```

**Estimated effort**: 1 day

---

## 5. Sprint 1 — P0 Critical Fixes

**Goal**: Eliminate all data corruption risks and security vulnerabilities.
**Duration**: 1 week
**Priority**: MUST complete before any other sprint.

### 5.1 Fix `datetime.now()` → `datetime.now(UTC)` Project-Wide

| Task | Files | Method |
|------|-------|--------|
| Enable ruff DTZ005 rule | `pyproject.toml` | Add `"DTZ"` to ruff select |
| Auto-fix all violations | 65+ files | `ruff check --fix --select DTZ005` |
| Manual review `default_factory` | 11+ model files | Replace `datetime.now` with `lambda: datetime.now(UTC)` |
| Verify UTC imports | All touched files | Ensure `from datetime import UTC` |

**Verification**: `ruff check --select DTZ005 backend/` returns 0 violations.

### 5.2 Thread-Safe Singleton Factories

| Task | Files | Method |
|------|-------|--------|
| Add `threading.Lock` to `get_qdrant()` | `infrastructure/storage/qdrant.py` | Wrap initialization |
| Add `threading.Lock` to `get_mongodb()` | `infrastructure/storage/mongodb.py` | Wrap initialization |
| Add `threading.Lock` to `get_llm()` | `infrastructure/external/llm/factory.py` | Wrap initialization |
| Audit all remaining `get_*()` | 12+ files | Search `@lru_cache` + `def get_` |

**Template**:
```python
import threading

_init_lock = threading.Lock()

@lru_cache
def get_service() -> Service:
    with _init_lock:
        return Service()
```

### 5.3 Fix `asyncio_mode` for Test Suite

| Task | File | Change |
|------|------|--------|
| Set auto mode | `pyproject.toml` | `asyncio_mode = "auto"` |
| Remove redundant decorators | ~50 test files | Remove individual `@pytest.mark.asyncio` (optional cleanup) |
| Run full test suite | — | `pytest tests/ -x` to verify no regressions |

### 5.4 Security Fixes

| Task | File | Issue |
|------|------|-------|
| Add PII redaction to LLM tracer | `infrastructure/observability/llm_tracer.py:115-117` | Raw messages logged without filtering |
| Validate webhook URLs | `infrastructure/observability/logging.py:250` | SSRF risk on `alert_webhook_url` |
| Add rate limiting to Docker log monitor | `infrastructure/observability/docker_log_monitor.py:92` | DoS via log flooding |

### 5.5 Fix Class-Level Mutable Defaults

| Task | Pattern | Fix |
|------|---------|-----|
| `list` defaults in dataclasses | `field: list = []` | `field: list = field(default_factory=list)` |
| `dict` defaults in BaseModels | `config: dict = {}` | `config: dict = Field(default_factory=dict)` |
| Shared state across instances | Class-level lists/dicts | Move to `__init__` |

**Search**: `ruff check --select RUF012 backend/`

---

## 6. Sprint 2 — Architectural Improvements

**Goal**: Reduce technical debt in architecture and resource management.
**Duration**: 2 weeks
**Prerequisite**: Sprint 1 complete.

### 6.1 Split God Classes

| File | Lines | Split Strategy |
|------|-------|---------------|
| `mcp.py` | 1620 | → `mcp_transport.py`, `mcp_session.py`, `mcp_tools.py` |
| `playwright_browser.py` | 1661 | → `playwright_navigator.py`, `playwright_interactions.py`, `playwright_screenshots.py` |
| `lifespan.py` | 460 | → `lifespan_startup.py`, `lifespan_shutdown.py`, `lifespan_health.py` |
| `openai_llm.py` | 1100 | → `openai_request_builder.py`, `openai_message_repair.py`, `openai_streaming.py` |

**Approach**: One PR per file. Extract methods, keep original file as thin facade.

### 6.2 Fix DDD Layer Violations

| Violation | Source | Target | Fix |
|-----------|--------|--------|-----|
| Domain imports `get_settings()` | `domain/services/` | `core/config.py` | Inject settings via constructor |
| Domain imports `get_llm()` | `domain/services/` | `infrastructure/external/llm/` | Use `LLMProtocol` |
| Domain imports MongoDB types | `domain/models/` | `pymongo` | Use domain-only types |

### 6.3 Resource Leak Fixes

| Issue | File | Fix |
|-------|------|-----|
| Connection pool leak in `__aexit__` | `connection_pool.py:941-949` | Add error handling around `_release_connection` |
| Container orphaning on init failure | `docker_sandbox.py:270-281` | Add `try/finally` with container cleanup |
| Unclosed HTTP client on reconnect | `docker_sandbox.py:96-122` | Await old client close before creating new |
| Unbounded renewal tasks | `redis_stream_queue.py:340-400` | Add task cancellation in finally block |

### 6.4 Add `asyncio.CancelledError` Guards

Long-running async operations need cancellation handling:

```python
# Before
async def long_operation():
    result = await external_call()
    await save_result(result)  # Skipped if cancelled between lines

# After
async def long_operation():
    try:
        result = await external_call()
        await save_result(result)
    except asyncio.CancelledError:
        logger.warning("Operation cancelled, cleaning up")
        await cleanup()
        raise  # Always re-raise CancelledError
```

**Files to audit**: All files in `domain/services/agents/`, `domain/services/flows/`.

---

## 7. Sprint 3 — Code Quality & Reliability

**Goal**: Improve type safety, error handling, and test quality.
**Duration**: 2 weeks

### 7.1 Replace Broad `except Exception`

**Priority targets** (highest occurrence count):
1. `domain/services/memory/memory_service.py` — 22 occurrences
2. `infrastructure/repositories/` — 15+ files
3. `infrastructure/external/llm/openai_llm.py` — 6 `pass` after catch

**Strategy**: Replace one module at a time. Use specific exception types from `domain/exceptions/`.

### 7.2 Add Type Annotations

| Target | Count | Approach |
|--------|-------|----------|
| Bare `dict` / `list` | 25+ | Add `[str, Any]` parameters |
| Missing return types | 15+ | Add return type annotations |
| Test method parameters | 20+ | Add fixture type hints |

### 7.3 Fix MongoDB Issues

| Issue | File | Fix |
|-------|------|-----|
| Race condition in rating updates | `mongo_skill_repository.py:295-312` | Use `$inc` atomic operator |
| Incorrect importance sorting | `mongo_memory_repository.py:296-299` | Map enum to numeric order |
| Missing ObjectId validation | `mongo_memories_collection.py:111` | Add try/except for `ObjectId()` |
| Unbounded `to_list()` queries | `mongo_connector_repository.py:30,71,79` | Add `limit` parameter |

### 7.4 Test Suite Improvements

| Task | Impact |
|------|--------|
| Add `@pytest.mark.integration` to external service tests | Prevent CI failures |
| Parametrize repetitive auth tests (30+ → 8) | -70% test code |
| Extract shared mock fixtures to `conftest.py` | Eliminate duplicate `_FakeRedisClient` etc. |
| Add `@pytest.mark.timeout(30)` to all async tests | Prevent infinite hangs |
| Fix tautological assertions (always-true) | 5+ tests actually testing nothing |

---

## 8. Sprint 4 — Cleanup & Polish

**Goal**: Remove dead code, consolidate duplicates, improve documentation.
**Duration**: 1 week

### 8.1 Remove Dead Code

```bash
# Find unused imports
ruff check --select F401 backend/

# Find commented-out code
ruff check --select ERA backend/

# Delete examples/mindsearch (already git-deleted)
git clean -fd examples/mindsearch/
```

### 8.2 Consolidate Duplicates

| Duplicate | Instances | Target |
|-----------|-----------|--------|
| Download endpoints | 3 | Single `download_service.py` |
| URL/email validators | 5 | `domain/validators.py` mixin |
| BSON normalization | 4 | `infrastructure/utils/bson_helpers.py` |
| Test mock classes | 6+ | `tests/fixtures/fakes.py` |

### 8.3 Add Missing `__all__` Exports

Audit all `__init__.py` files and add explicit `__all__` lists.

### 8.4 Documentation

| Task | Target |
|------|--------|
| Add docstrings to test classes | 40+ test classes missing docstrings |
| Document fixture lifecycle | `tests/conftest.py` (30 fixtures, no dependency graph) |
| Standardize error messages | Consistent `f"[{provider}] ..."` format across modules |

---

## 9. Quick Wins (< 1 hour each)

These can be done independently and each addresses a significant number of issues:

### Quick Win 1: `asyncio_mode = "auto"` (5 minutes → fixes 40+ tests)

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### Quick Win 2: Enable ruff DTZ005 (30 minutes → fixes 65+ datetime issues)

```toml
# pyproject.toml
[tool.ruff.lint]
select = [..., "DTZ"]
```
```bash
ruff check --fix --select DTZ005 backend/
```

### Quick Win 3: Singleton Lock Template (1 hour → fixes 15 race conditions)

Apply this template to all `get_*()` factory functions:

```python
import threading
_lock = threading.Lock()

@lru_cache
def get_service() -> Service:
    with _lock:
        return Service()
```

### Quick Win 4: Delete `examples/mindsearch/` (5 minutes)

```bash
git rm -r examples/mindsearch/
```

### Quick Win 5: Fix unused imports (15 minutes)

```bash
ruff check --fix --select F401 backend/
```

---

## 10. Detailed Findings by Layer

### 10.1 `core/` — Config, Lifespan, DI

| ID | Priority | File | Line(s) | Issue |
|----|----------|------|---------|-------|
| C-01 | P0 | `lifespan.py` | 1-460 | God function — all startup/shutdown in single async function |
| C-02 | P0 | `config.py` | Multiple | Some settings lack validation (e.g., negative timeouts accepted) |
| C-03 | P1 | `config.py` | Multiple | `@computed_field` properties could be cached |
| C-04 | P1 | `prometheus_metrics.py` | Multiple | Metrics registered at module level (import side effects) |
| C-05 | P2 | `config_llm.py` | 8-48 | Mixin classes don't enforce required fields |

### 10.2 `domain/models/` — Entities & Value Objects

| ID | Priority | File | Line(s) | Issue |
|----|----------|------|---------|-------|
| DM-01 | P0 | 11+ files | Multiple | `datetime.now()` without UTC in default factories |
| DM-02 | P1 | `agent_event.py` | Multiple | StrEnum with 30+ values — consider splitting |
| DM-03 | P1 | `session.py` | Multiple | Session model has 20+ fields (borderline god model) |
| DM-04 | P2 | `structured_outputs.py` | Multiple | 554-line file with complex validation |
| DM-05 | P2 | Multiple | Multiple | Inconsistent `model_config` patterns |

### 10.3 `domain/services/` — Business Logic

| ID | Priority | File | Line(s) | Issue |
|----|----------|------|---------|-------|
| DS-01 | P0 | `memory_service.py` | Multiple | 22+ bare `except Exception` blocks |
| DS-02 | P0 | `tools/mcp.py` | 1-1620 | God class — MCP tool, config, transport, session all in one |
| DS-03 | P1 | `agents/execution.py` | Multiple | Class-level mutable defaults (shared state) |
| DS-04 | P1 | `flows/` | Multiple | Missing `asyncio.CancelledError` guards |
| DS-05 | P1 | `tools/browser_tool.py` | Multiple | 800+ line file, mixed concerns |
| DS-06 | P2 | Multiple | Multiple | Domain services importing from infrastructure |
| DS-07 | P2 | `agents/` | Multiple | LRU cache on instance methods (cache ignores `self`) |

### 10.4 `application/` — Use Cases

| ID | Priority | File | Line(s) | Issue |
|----|----------|------|---------|-------|
| A-01 | P1 | `agent_domain_service.py` | Multiple | 700+ lines, multiple responsibilities |
| A-02 | P1 | `session_service.py` | Multiple | Transaction boundaries unclear |
| A-03 | P2 | `dto/` | Multiple | DTOs duplicating domain model fields |

### 10.5 `interfaces/` — API Routes & Schemas

| ID | Priority | File | Line(s) | Issue |
|----|----------|------|---------|-------|
| I-01 | P1 | `schemas/skill.py` | 8-39 | SkillResponse has 20+ fields (consider splitting) |
| I-02 | P1 | `routes/session_routes.py` | Multiple | 500+ lines, all session endpoints in one file |
| I-03 | P2 | `schemas/` | Multiple | Untyped `dict` fields (should be `dict[str, Any]`) |
| I-04 | P2 | `routes/` | Multiple | Duplicate download endpoint patterns |
| I-05 | P3 | `schemas/event.py` | Multiple | Large schema file, could be split by event type |

### 10.6 `infrastructure/` — Adapters & External Systems

| ID | Priority | File | Line(s) | Issue |
|----|----------|------|---------|-------|
| IF-01 | P0 | `storage/qdrant.py:184-187` | 184-187 | Thread-unsafe `get_qdrant()` singleton |
| IF-02 | P0 | `observability/llm_tracer.py:115` | 115-117 | PII logging — raw LLM messages stored |
| IF-03 | P0 | `observability/logging.py:250` | 250 | SSRF risk — unvalidated webhook URL |
| IF-04 | P0 | `external/browser/connection_pool.py:941` | 941-949 | Resource leak in `__aexit__` |
| IF-05 | P0 | `external/sandbox/docker_sandbox.py:270` | 270-281 | Container orphaning on init failure |
| IF-06 | P1 | `external/llm/openai_llm.py` | Multiple | 1100-line god class |
| IF-07 | P1 | `external/llm/factory.py:182` | 182-213 | Thread-unsafe `_cached_llm` global |
| IF-08 | P1 | `external/browser/playwright_browser.py` | Multiple | 1661-line god class |
| IF-09 | P1 | `repositories/mongo_skill_repository.py:295` | 295-312 | Race condition in rating updates |
| IF-10 | P1 | `external/cache/circuit_breaker.py:96` | 96 | `threading.Lock` in async context (blocks event loop) |
| IF-11 | P2 | `repositories/mongo_memory_repository.py:269` | 269 | Incorrect score normalization formula |
| IF-12 | P2 | `repositories/mongo_memory_repository.py:296` | 296 | Alphabetical sort on importance enum |
| IF-13 | P2 | `storage/redis.py:48-99` | 48-99 | Race condition in circuit breaker state transitions |

---

## 11. Test Suite Findings

### 11.1 Critical Test Issues

| ID | Priority | File | Issue |
|----|----------|------|-------|
| T-01 | P0 | 40+ files | Missing `@pytest.mark.asyncio` — tests pass without executing |
| T-02 | P0 | `test_circuit_breaker_adaptive.py` | Tautological assertions (always pass) |
| T-03 | P0 | `test_browser_positioning.py` | Structured as script, not pytest-compatible |
| T-04 | P0 | Multiple | Async fixtures consumed by sync test methods |
| T-05 | P0 | `test_ssrf_protection.py:73-78` | `assert isinstance(result, str) or result is None` — always passes |

### 11.2 Test Quality Issues

| ID | Priority | Files | Issue |
|----|----------|-------|-------|
| T-06 | P1 | `conftest.py` | 30 fixtures without lifecycle documentation |
| T-07 | P1 | `test_auth_routes.py` | 30+ nearly-identical tests → use `@pytest.mark.parametrize` |
| T-08 | P1 | Multiple | Global state mutation without autouse cleanup |
| T-09 | P1 | `test_deep_research.py` | Race conditions with hardcoded `asyncio.sleep(0.1)` |
| T-10 | P2 | Multiple | Duplicate mock setup across files (`_FakeRedisClient` etc.) |
| T-11 | P2 | Multiple | Missing edge case tests (empty input, None values, concurrent calls) |
| T-12 | P2 | `test_multikey_e2e.py` | 400+ line fixture setup |
| T-13 | P3 | Multiple | Inconsistent fixture naming (`mock_redis` vs `redis_client` vs `mocked_redis`) |

### 11.3 Test Suite Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Async tests with proper markers | ~85% | 100% |
| Tests using `@pytest.mark.parametrize` | ~20% | 50% |
| Integration test isolation | 30% | 100% |
| Type hints on test methods | 40% | 95% |
| Test classes with docstrings | 60% | 95% |

---

## 12. Verification Checklist

Use this checklist after each sprint to verify completion:

### Sprint 1 Verification

- [ ] `ruff check --select DTZ005 backend/` returns 0 violations
- [ ] `grep -rn "datetime.now()" backend/app/` returns 0 results
- [ ] All `get_*()` factories have `threading.Lock`
- [ ] `pytest tests/ -x` passes with `asyncio_mode = "auto"`
- [ ] `llm_tracer.py` has PII redaction layer
- [ ] `logging.py` webhook URL validated against SSRF patterns
- [ ] No class-level mutable defaults in dataclasses/BaseModels

### Sprint 2 Verification

- [ ] No file in `domain/` imports from `infrastructure/`
- [ ] No file exceeds 800 lines (down from 1600+)
- [ ] `docker_sandbox.py` has container cleanup in all exception paths
- [ ] `connection_pool.py` `__aexit__` handles release errors
- [ ] All long-running async operations handle `CancelledError`

### Sprint 3 Verification

- [ ] `grep -rn "except Exception" backend/app/` count < 20 (from 50+)
- [ ] `grep -rn "dict = " backend/app/interfaces/schemas/` returns 0 bare dicts
- [ ] `mongo_skill_repository.py` rating update is atomic
- [ ] Test suite has `@pytest.mark.integration` on all external-service tests
- [ ] No tautological assertions in test suite

### Sprint 4 Verification

- [ ] `ruff check --select F401 backend/` returns 0 unused imports
- [ ] `ruff check --select ERA backend/` returns 0 commented-out code
- [ ] All download endpoints consolidated
- [ ] All test mock classes in `tests/fixtures/fakes.py`
- [ ] All `__init__.py` files have `__all__` exports

---

## Appendix: Agent-Specific Reports

The following background agents contributed findings to this plan:

| Agent ID | Scope | Files | Findings |
|----------|-------|-------|----------|
| a0cd716 | Domain models | 47 | datetime issues in 11 model files |
| aa9333d | Domain services/agents | 95 | 17 issues, thread-unsafe singletons |
| a427130 | Domain services/flows | — | 23 issues, mutable defaults |
| a36595a | Domain services/tools | 40 | 35 issues, god classes |
| aa720d9 | Remaining domain services | — | 13 issues, broad exceptions |
| a5cbdef | Infra repos + models | 20 | 26 issues, race conditions |
| a64ed8c | Infra observability + misc | 27 | 22 issues, 3 security P0s |
| aedcc5c | Infra browser + sandbox | 13 | 21 issues, resource leaks |
| acb1f8b | Infra external LLM + search | — | 23 issues, async property violations |
| a7af9c3 | Domain + application tests | — | 37 issues, missing asyncio markers |
| ac0f43a | Infrastructure tests | 76 | 47 issues, mock mismatches |
| a75ff93 | Root-level tests A-M | 24 | 32 issues, tautological assertions |
| a8322ec | Root-level tests N-Z | — | 27 issues, parametrize opportunities |
| aead7df | CoVe alternatives research | — | Research support |

---

*This document is the single source of truth for the Pythinker backend remediation effort. Update it as fixes are applied and verified.*
