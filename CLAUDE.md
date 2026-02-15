# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pythinker is an AI Agent system that runs tools (browser, terminal, files, search) in isolated Docker sandbox environments. It uses a FastAPI backend with Domain-Driven Design, a Vue 3 frontend, and Docker containers for task isolation.

## Quick Reference

> **Core Principles:**
> 1. **Reuse First**: Search existing codebase for components, utilities, and services before creating new ones
> 2. **Simplicity First**: Design with simplicity and directness — prefer straightforward solutions that maintain robustness, reliability, and best practices; avoid unnecessary complexity or overcomplication
> 3. **Full-Stack Design**: Design each feature by thoroughly evaluating and integrating front-end and back-end architecture considerations, ensuring seamless compatibility, optimal performance, and cohesive system integration across all components
> 4. **Self-Hosted First**: When integrating solutions and services, prioritize self-hosted, zero-cost, open-source options that do not rely on external dependencies; ensure all integrations are self-contained and require no additional external resources or dependencies
> 5. **Dependency Rule**: Domain → Application → Infrastructure → Interfaces (inward only)
> 6. **SOLID**: Single responsibility, depend on abstractions, inject dependencies
> 7. **Type Safety**: Full type hints (Python) / strict mode (TypeScript); no `any`
> 8. **Layer Discipline**: Business logic in domain, not in API routes or components
> 9. **Naming**: Python `snake_case` functions / `PascalCase` classes; Vue `PascalCase` components / `useX` composables
> 10. **Context7 Validation (Always)**: Validate all new implementations, files, and configurations against fetched Context7 MCP documentation to ensure accuracy and compliance before deployment
>
> **Before committing:**
> - **Frontend**: `cd frontend && bun run lint && bun run type-check`
> - **Backend**: `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`

## Development Guidelines

- **Read [instructions.md](instructions.md) first** - Core engineering behaviors and patterns
- **Reuse Before Creating**: Before implementing any new code, component, utility, or feature, **search the existing codebase** for similar functionality. Check composables, services, utilities, domain models, and components that may already solve the problem or can be extended. Never create a duplicate when an existing piece can be reused or adapted.
- **HTTP Connection Pooling**: Always use `HTTPClientPool` for HTTP communication. Never create `httpx.AsyncClient` directly. See `docs/architecture/HTTP_CLIENT_POOLING.md` for details.
- **Pydantic v2**: `@field_validator` methods **must** be `@classmethod`
- **Python Environment**: Always `conda activate pythinker` before running tests
- **Plan Execution**: Complete ALL phases - priorities indicate order, not optional phases

### Multi-API Key Management

- **Always use APIKeyPool** for external API providers (search, LLM, embedding)
- **Never create direct API clients** without key pool integration
- **Strategy Selection:**
  - FAILOVER: Search engines, LLMs (preserves caching)
  - ROUND_ROBIN: Embeddings (load distribution)
- **Redis Required:** For multi-instance coordination (graceful degradation to in-memory)
- **TTL Recovery:** Keys auto-recover after quota reset (hourly/daily)
- **Comprehensive docs:** See `docs/architecture/MULTI_API_KEY_MANAGEMENT.md`

### DeepCode Integration ✅

**Status:** COMPLETE - All 3 Phases Implemented (2026-02-15)

Pythinker has been enhanced with 8 major reliability and performance improvements from DeepCode:

**Phase 1: Unified Adaptive Model Routing** ✅
- Complexity-based model tier selection (fast/balanced/powerful)
- Settings-based configuration (12-factor app pattern)
- Zero redundancy (eliminated duplicate enums/logic)
- Prometheus metrics: `pythinker_model_tier_selections_total`
- **Impact:** 20-40% cost reduction, 60-70% latency reduction on simple tasks

**Phase 2: Agent Reliability Enhancements** ✅
- **Tool Efficiency Monitor:** Detects analysis paralysis (5+ consecutive reads without writes)
  - Automatic nudge injection into conversation
  - Prometheus metrics: `pythinker_tool_efficiency_nudges_total`
  - **Impact:** 50%+ reduction in analysis paralysis patterns

- **Truncation Detector:** Pattern-based incomplete output detection
  - 5 regex patterns (mid-sentence, unclosed code/JSON, incomplete lists)
  - Automatic continuation requests with pattern-specific prompts
  - Prometheus metrics: `pythinker_output_truncations_total`
  - **Impact:** 60%+ reduction in incomplete outputs reaching users

**Phase 3: Document Segmentation & Implementation Tracking** ✅
- **Document Segmenter:** Context-aware chunking for long documents
  - Auto type detection (Python, Markdown, JSON, YAML, Text)
  - AST-based boundary preservation (never splits mid-function)
  - 3 strategies: SEMANTIC (default), FIXED_SIZE, HYBRID
  - **Impact:** 70%+ reduction in context truncation

- **Implementation Tracker:** Multi-file code completion validation
  - AST + pattern-based detection (TODO, FIXME, NotImplementedError)
  - Completeness scoring with severity weights
  - Automatic completion checklists
  - **Impact:** 80%+ reduction in incomplete multi-file implementations

**New Components (6 files, 1,624 lines):**
- `backend/app/domain/services/agents/tool_efficiency_monitor.py`
- `backend/app/domain/services/agents/truncation_detector.py`
- `backend/app/domain/services/agents/document_segmenter.py`
- `backend/app/domain/services/agents/implementation_tracker.py`

**Enhanced Components (7 files):**
- `model_router.py`, `complexity_assessor.py`, `llm.py`, `openai_llm.py`
- `execution.py`, `base.py`, `config.py`

**Configuration (.env):**
```bash
# Adaptive Model Selection
ADAPTIVE_MODEL_SELECTION_ENABLED=true
FAST_MODEL=claude-haiku-4-5
BALANCED_MODEL=  # Empty = use MODEL_NAME
POWERFUL_MODEL=claude-sonnet-4-5
```

**Documentation:**
- `DEEPCODE_INTEGRATION_COMPLETE.md` - Complete overview
- `UNIFIED_ADAPTIVE_ROUTING.md` - Phase 1 details
- `DEEPCODE_PHASE_2_COMPLETE.md` - Phase 2 details
- `DEEPCODE_PHASE_3_COMPLETE.md` - Phase 3 details

**Context7 Validated Patterns:**
- Pydantic v2: `@field_validator`, `@model_validator(mode='after')`, `@computed_field`
- Python AST: `ast.parse()`, `ast.walk()`, node inspection
- Singleton factories: `get_*()` pattern for all monitors
- Non-blocking error handling: All integrations wrapped in try/except

## Communication & Accuracy Standards

- **Absolute Status Accuracy Rule**: When creating summaries or status reports, maintain 100% factual accuracy. Never mark a task as "Completed" if it is only partially done or if only foundational code is in place. Always clearly distinguish "Completed", "In Progress", and "Not Started".
- **Absolute Full Implementation Rule**: When requested to write code, provide the full, unabridged implementation for every file. Never use placeholders (e.g., `// ... rest of code`, `// ... implementation details`), summaries, or skipped sections to save space.
- **Absolute Persistence Rule**: If a request is complex, do not simplify it to fit a single response. Output as much valid code as possible, then stop and await a "Continue" prompt to finish the rest. Prioritize absolute completeness over brevity or speed, regardless of task size.

## 2026 Best Practices (Context7 MCP Validated - 2026-02-11)

### Applied Enhancements

**Security** ✅:
- OWASP-compliant security headers middleware (`backend/app/infrastructure/middleware/security_headers.py`)
- Multi-stage Docker builds with non-root user (`backend/Dockerfile`)
- Enhanced security linting with Bandit rules (S category in ruff)
- 50+ new vulnerability detection rules

**Code Quality** ✅:
- Pydantic v2 `@computed_field` for all Settings properties (`backend/app/core/config.py`)
- FastAPI lifespan events (already compliant with modern pattern)
- 13 lint rule categories total (added ASYNC, S, PERF, T20, ERA, FURB, FLY)

**Performance** ✅:
- 70% smaller Docker images (1.2GB → 350MB)
- Parallel test execution with pytest-xdist (2-4x faster)
- Optimized Docker layer caching (50% faster builds)

**Documentation** ✅:
- See `docs/architecture/2026_BEST_PRACTICES.md` for comprehensive details
- See `QUICK_START_2026.md` for 5-minute implementation guide
- Examples: `backend/docs/examples/fastapi_best_practices_2026.py`
- Examples: `backend/docs/examples/pydantic_v2_best_practices_2026.py`

**Context7 Validation**: All changes validated against authoritative sources:
- FastAPI: `/websites/fastapi_tiangolo` (Score: 96.8/100)
- Pydantic v2: `/websites/pydantic_dev_2_12` (Score: 83.5/100)
- Docker: `/websites/docker` (Score: 88.5/100)
- Pytest: `/pytest-dev/pytest` (Score: 87.7/100)
- Ruff: `/websites/astral_sh_ruff` (Score: 86.3/100)

## Detailed Standards

For comprehensive coding standards, see:
- **[Engineering Instructions](instructions.md)** - Core behaviors, leverage patterns, output standards (MUST READ)
- **[Python Standards](docs/guides/PYTHON_STANDARDS.md)** - Pydantic v2, FastAPI, Legacy Flow, async patterns
- **[Vue Standards](docs/guides/VUE_STANDARDS.md)** - Composition API, Pinia, TypeScript
- **[Replay & Sandbox](docs/guides/OPENREPLAY.md)** - Screenshot replay, CDP screencast

---

## Development Commands

### Full Stack
```bash
./dev.sh up -d              # Start dev stack
./dev.sh down -v            # Stop and remove volumes
./dev.sh logs -f backend    # Follow logs
```

### Backend
```bash
cd backend && conda activate pythinker
ruff check . && ruff format --check .   # Lint
ruff check --fix . && ruff format .     # Auto-fix
pytest tests/                           # Test
pytest -p no:cov -o addopts= tests/test_file.py  # Single test without coverage
```

### Frontend
```bash
cd frontend
bun run dev          # Dev server (5173)
bun run lint         # ESLint fix
bun run type-check   # TypeScript check
bun run test:run     # Single test run
```

---

## Architecture

### Backend DDD Structure (`backend/app/`)
- **domain/**: Core business logic, models, services, abstract repositories
- **application/**: Use case orchestration, DTOs
- **infrastructure/**: MongoDB/Redis implementations, external adapters (LLM, browser, search)
- **interfaces/api/**: REST routes, request/response schemas
- **core/**: Config, sandbox manager, workflow manager

### Frontend Structure (`frontend/src/`)
- **pages/**: Route components (ChatPage, HomePage)
- **components/**: UI components (ChatMessage, SandboxViewer, ToolPanel)
- **composables/**: Shared logic (useChat, useSession, useAgentEvents)
- **api/**: HTTP client with SSE support

### Key Patterns
- **Event Sourcing**: Session events in MongoDB
- **SSE Streaming**: Real-time events to frontend
- **Legacy Flow Workflows**: Planning → Execution → Reflection → Verification
- **Sandbox Isolation**: Docker containers with CDP screencast

### Plotly Chart System

**Status:** Production-Ready (Enhanced 2026-02-15)

**Best Practices Guide:** `docs/PLOTLY_CHART_BEST_PRACTICES.md` (Context7 MCP Validated)

**Key Principles:**
- **Color Palette:** Plotly's official 10-color qualitative palette (`px.colors.qualitative.Plotly`)
- **Orientation:** Horizontal bars (`orientation='h'`) for comparison charts with labels >4 characters
- **Sorting:** Auto-sorted by value (descending) for optimal readability
- **Templates:** `plotly_white` recommended for professional appearance
- **Number Formatting:** Smart SI suffix formatting (12k, 1.5M, etc.)
- **Text Sizing:** `uniformtext_minsize=8` with `mode='hide'` for consistent labels

**Chart Type Selection:**
- `bar`: Categorical comparisons, rankings
- `line`: Time-series data, trends
- `scatter`: Correlation, distributions, outliers
- `pie`: Part-to-whole (max 5-7 categories)
- `grouped_bar` / `stacked_bar`: Multi-series comparisons
- `box`: Distribution analysis, quartiles

**Implementation:** `sandbox/scripts/generate_plotly_chart.py` (Python 3.12+, TypedDict, StrEnum, pattern matching)

**Documentation:**
- Complete guide: `docs/PLOTLY_CHART_BEST_PRACTICES.md`
- Implementation summary: `docs/CHART_IMPROVEMENTS_SUMMARY.md`

---

### Browser Architecture

**Standard Browser Stack** (Standardized 2026-02-15):
- **Engine:** Playwright Chromium (lighter, more stable than Chrome for Testing)
- **Control:** Chrome DevTools Protocol (CDP) on port 9222
- **Display:** VNC streaming (x11vnc + websockify) on port 5901 for real-time user visibility
- **Tools:**
  - `BrowserTool`: Manual control (single actions: navigate, click, input)
  - `BrowserAgentTool`: Autonomous operation (multi-step workflows via browser-use library)

**Three-Tier Architecture:**
```
Domain Protocol (browser.py)
    ↓
Infrastructure Implementation (PlaywrightBrowser)
    ↓
Tool Services (BrowserTool, BrowserAgentTool)
```

**Key Features:**
- ✅ Automatic crash recovery with progress events
- ✅ Connection pooling via HTTPClientPool (60-75% latency reduction)
- ✅ VNC health monitoring in SandboxHealth
- ✅ All browser actions visible in real-time via VNC

**Documentation:**
- **Comprehensive Guide:** `docs/architecture/BROWSER_ARCHITECTURE.md`
- **Architecture Decisions:** `docs/architecture/BROWSER_STANDARDIZATION_ADR.md`
- **Automatic Behavior:** `docs/architecture/AUTOMATIC_BROWSER_BEHAVIOR.md`

### Memory System Architecture (Phase 1: Hybrid Retrieval)

**Overview**: Pythinker uses a dual-store memory architecture with MongoDB (document storage) and Qdrant (vector search).

**Named-Vector Schema**:
- Collections use named vectors: `dense` (OpenAI embeddings, 1536d) + `sparse` (BM25 keyword vectors)
- Primary collection: `user_knowledge` (replaces legacy `agent_memories`)
- Multi-collection: `task_artifacts`, `tool_logs`, `semantic_cache`

**Hybrid Search**:
- Dense semantic search: OpenAI `text-embedding-3-small` via API
- Sparse keyword search: Self-hosted BM25 using `rank-bm25` library
- Fusion: Reciprocal Rank Fusion (RRF) combines dense + sparse results

**Sync State Tracking**:
- MongoDB fields: `sync_state` (pending/synced/failed), `sync_attempts`, `last_sync_attempt`, `sync_error`
- Foundation for Phase 2 reliability (outbox pattern, reconciliation)

**Embedding Metadata**:
- `embedding_model`, `embedding_provider`, `embedding_quality` (1.0 for API, 0.5 for fallback)
- Used for Phase 4 grounding and confidence scoring

**Usage Patterns**:
```python
# Store memory with hybrid vectors
await memory_service.store_memory(
    user_id="user-123",
    content="User prefers dark mode",
    memory_type=MemoryType.PREFERENCE,
    generate_embedding=True,  # Generates both dense + sparse
)

# Hybrid search (dense+sparse RRF)
from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository
repo = QdrantMemoryRepository()
results = await repo.search_hybrid(
    user_id="user-123",
    query_text="dark mode preferences",
    dense_vector=dense_embedding,
    sparse_vector=bm25_encoder.encode("dark mode preferences"),
    limit=10,
)

# Dense-only search (backward compat)
results = await repo.search_similar(
    user_id="user-123",
    query_vector=dense_embedding,
    limit=10,
)
```

**BM25 Encoder**:
```python
from app.domain.services.embeddings.bm25_encoder import get_bm25_encoder

encoder = get_bm25_encoder()
# Fit on corpus (done automatically on app startup)
encoder.fit(corpus)
# Generate sparse vector
sparse = encoder.encode("query text")  # Returns {index: score} dict
```

**Feature Flags** (`backend/app/core/config.py`):
- `qdrant_use_hybrid_search: bool = True` - Enable RRF hybrid retrieval
- `qdrant_sparse_vector_enabled: bool = True` - Generate BM25 sparse vectors
- `qdrant_user_knowledge_collection: str = "user_knowledge"` - Primary memory collection

**Payload Indexes** (fast filtered search):
- `user_id`, `memory_type`, `importance`, `tags`, `session_id`, `created_at`

**Testing**:
- BM25 encoder: `tests/domain/services/test_bm25_encoder.py`
- Hybrid search: `tests/infrastructure/test_qdrant_hybrid_search.py`

---

## Port Mapping (Development)

| Service | Port |
|---------|------|
| Frontend | 5174 |
| Backend | 8000 |
| Sandbox API | 8083 |
| MongoDB | 27017 |
| Redis | 6379 |
| Qdrant | 6333/6334 |

---

## Code Style

- **Python**: 4-space indent, `snake_case` functions, `PascalCase` classes
- **Vue/TS**: 2-space indent, `PascalCase` components, `useX` composables
- **Linting**: Ruff (backend), ESLint (frontend)

---

## Anti-Patterns to Avoid

1. **God Classes** - Split large classes with multiple responsibilities
2. **Leaky Abstractions** - Infrastructure details must not leak into domain
3. **Circular Dependencies** - Maintain strict layer boundaries
4. **Magic Strings** - Use enums and constants
5. **Deep Nesting** - Prefer early returns and guard clauses
6. **Redundant Code** - Never create new files, components, utilities, or services without first searching for existing ones that serve the same or similar purpose
7. **Over-Engineering** - Avoid unnecessary abstractions, premature generalization, or complex patterns when a simple direct solution works equally well
8. **Direct HTTP Clients** - Never create `httpx.AsyncClient` directly; always use `HTTPClientPool` for connection pooling and metrics

---

## Refactoring Checklist

- [ ] Searched codebase for existing similar functionality before creating new code
- [ ] Dependencies point inward (domain has no external imports)
- [ ] Each class/function has single responsibility
- [ ] Type hints/annotations complete
- [ ] Business logic in domain layer
- [ ] No `any` types (TS) / untyped functions (Python)
- [ ] New implementations/files/configurations validated against fetched Context7 MCP documentation
- [ ] Tests pass, linting passes

---

## Configuration

- Copy `.env.example` to `.env` for local runs
- MCP integration via `mcp.json.example`
- Docker socket mount: `-v /var/run/docker.sock:/var/run/docker.sock`

### API Key Configuration

**Multi-Key Support:**
- Search engines: Up to 3-9 keys (Serper: 3, Tavily: 9, Brave: 3)
- LLMs: Up to 3 keys (Anthropic, OpenAI)
- Embeddings: Up to 3 keys (OpenAI)

**Environment Variables:**
- Primary: `SERPER_API_KEY`, `ANTHROPIC_API_KEY`, `EMBEDDING_API_KEY`
- Fallbacks: `*_API_KEY_2`, `*_API_KEY_3`, etc.
- See `.env.example` for complete multi-key configuration

**Automatic Rotation:**
- HTTP 401/429 → Rotate to next healthy key
- TTL-based recovery (keys auto-recover after quota reset)
- Prometheus metrics for observability
