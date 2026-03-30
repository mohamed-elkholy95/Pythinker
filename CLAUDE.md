# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pythinker is an AI Agent system that runs tools (browser, terminal, files, search) in isolated Docker sandbox environments. It uses a FastAPI backend with Domain-Driven Design, a Vue 3 frontend, and Docker containers for task isolation.

## Quick Reference

> **Core Principles:**
> 1. **Reuse First (DRY)**: Search existing codebase for components, utilities, and services before creating new ones — never duplicate logic, constants, or structure that already exists
> 2. **Simplicity First (KISS)**: Design with simplicity and directness — prefer the simplest solution that works; avoid unnecessary abstraction, indirection, or complexity in both implementation and debugging code
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
> - **Backend**: `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/<relevant-dir-or-file>`
> - **Testing rule**: Always run **targeted tests** (specific file or directory) — never the full test suite unless explicitly asked
>
> **Git commit strategy (MANDATORY):**
> - When committing multiple files, ALWAYS split into **multiple atomic commits** grouped by logical concern
> - Never bundle unrelated changes (bug fixes, features, refactors, chores) into one commit
> - Each commit must be **independently revertable** — one concern, one commit
> - Cluster by: bug-fix type · feature scope · architectural layer · impact area
> - Format: `fix(scope)` · `feat(scope)` · `refactor(scope)` · `chore(scope)` · `docs(scope)` · `test(scope)`
> - Stage files selectively with `git add <specific-files>` — never `git add .` for multi-concern changesets

## Development Guidelines

- **Read [instructions.md](instructions.md) first** - Core engineering behaviors and patterns
- **Reuse Before Creating**: Before implementing any new code, component, utility, or feature, **search the existing codebase** for similar functionality. Check composables, services, utilities, domain models, and components that may already solve the problem or can be extended. Never create a duplicate when an existing piece can be reused or adapted.
- **HTTP Connection Pooling**: Always use `HTTPClientPool` for HTTP communication. Never create `httpx.AsyncClient` directly. See `docs/architecture/HTTP_CLIENT_POOLING.md` for details.
- **Pydantic v2**: `@field_validator` methods **must** be `@classmethod`
- **Python Environment**: Always `conda activate pythinker` before running tests
- **Plan Execution**: Complete ALL phases - priorities indicate order, not optional phases

### Automatic Skill Activation (Python + Frontend)

**CRITICAL**: PreToolUse hooks automatically monitor file operations and recommend appropriate skills.

#### Python Skill Hook (`~/.claude/hooks/python_skill_activator.py`)

**When you see:**
```
╔════════════════════════════════════════════════════════════════╗
║  🤖 PRO AGENT ACTIVATION RECOMMENDED                    ║
║  Recommended: python-development:fastapi-pro                   ║
╚════════════════════════════════════════════════════════════════╝
```

**YOU MUST immediately invoke:** `Skill tool: python-development:fastapi-pro`

**Available Python Agents:**
- `python-development:fastapi-pro` - FastAPI Expert • API routes, SQLAlchemy 2.0, Pydantic V2
- `python-development:python-pro` - Python 3.12+ Expert • Modern tooling, domain models
- `python-development:django-pro` - Django Expert • ORM, DRF, Celery

**Available Python Skills:**
- `python-development:python-testing-patterns` - pytest, fixtures, mocking
- `python-development:async-python-patterns` - asyncio, concurrent programming
- `python-development:python-configuration` - Environment variables, Pydantic Settings
- Others: python-packaging, python-type-safety, python-error-handling, python-observability

**Detects:** FastAPI, Pydantic, pytest, async/await, domain models, infrastructure, config
**Disable:** `export ENABLE_PYTHON_SKILL_HOOK=0`

#### Frontend Skill Hook (`~/.claude/hooks/frontend_skill_activator.py`)

**When you see:**
```
╔════════════════════════════════════════════════════════════════╗
║  ⚡ VUE SKILL ACTIVATION RECOMMENDED                    ║
║  Recommended: vue-best-practices:vue-best-practices            ║
╚════════════════════════════════════════════════════════════════╝
```

**YOU MUST immediately invoke:** `Skill tool: vue-best-practices:vue-best-practices`

**Available Vue Skills:**
- `vue-best-practices:vue-best-practices` - Vue 3 Expert • Composition API, `<script setup>`, TypeScript
- `vue-best-practices:vue-router-best-practices` - Vue Router 4 • Navigation, guards, params
- `vue-best-practices:vue-pinia-best-practices` - Pinia • State management, stores
- `vue-best-practices:vue-testing-best-practices` - Vitest, Vue Test Utils, component testing
- `vue-best-practices:create-adaptable-composable` - MaybeRef patterns, reactive inputs
- `vue-best-practices:vue-debug-guides` - Debugging, errors, hydration issues
- `vue-best-practices:vue-jsx-best-practices` - JSX in Vue, render functions
- `vue-best-practices:vue-options-api-best-practices` - Options API (legacy)

**Frontend Design Skill:**
- `frontend-design:frontend-design` - 🎨 Production UI Design • Distinctive aesthetics, creative components

**Detects:**
- Vue components (.vue files)
- Composables (40+ in Pythinker: useSSE, useAuth, useSandbox, etc.)
- API client (SSE, HTTP, WebSocket)
- TypeScript types
- Router configuration
- Pinia stores
- Component tests (Vitest)
- Styling and visual design
- Utils, plugins, config

**Disable:** `export ENABLE_FRONTEND_SKILL_HOOK=0`

#### Hook Behavior (Both Hooks)
- **Triggers on:** Edit, Write, MultiEdit, Bash, Read operations
- **Non-blocking:** Shows recommendation but allows operation to proceed
- **Session-aware:** Only shows once per file/skill per session
- **Professional coverage:** Comprehensive pattern detection for entire codebase
- **Debug logs:** `/tmp/python-skill-hook-log.txt`, `/tmp/frontend-skill-hook-log.txt`

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
# Default: Kimi 2.5 Code (all tiers)
API_BASE=https://api.kimi.com/coding/v1
MODEL_NAME=kimi-for-coding
ADAPTIVE_MODEL_SELECTION_ENABLED=false
# Override per tier if needed:
#FAST_MODEL=kimi-for-coding
#BALANCED_MODEL=kimi-for-coding
#POWERFUL_MODEL=kimi-for-coding
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

## Recent Feature Additions (2026-02-17)

> **IMPORTANT**: These features are implemented but previously undocumented. Update memory whenever implementing bugs/features.

### LLM Fallback Isolation and Summary Recovery (2026-03-29)

- **Fallback client isolation** (`openai_llm.py`): When `_fallback_active` is `True`, the cached client is returned directly without re-querying the primary key pool. `RateLimitError` and auth errors during fallback now propagate immediately instead of rotating the primary key pool, preventing credential cross-contamination.
- **Raised stream read timeouts**: `llm_stream_read_timeout` raised from 90 → 150 s (`config_llm.py`). Timeout profiles updated: `openai` 120 → 150 s, `glm` 90 → 150 s (`openai_llm.py`). Long-form summarization on large contexts can pause well over a minute on OpenAI-compatible providers.
- **Summary recovery from cache** (`execution.py`): When summarization fails with no streamed content, the agent falls back to `_pre_trim_report_cache` or `_extract_fallback_summary()` and emits a `[Partial] <title>` `ReportEvent` with a recovery notice instead of yielding a bare `ErrorEvent`.
- **Files**: `config_llm.py`, `openai_llm.py`, `execution.py`

### Universal LLM Provider Auto-Detection (commit 8afef32)
- **Setting**: `llm_provider: str = "auto"` — auto-detects provider from API keys and model name patterns
- **JSON Repair**: Automatic recovery from malformed LLM JSON responses (handles GLM and other quirky providers)
- **Supports**: Anthropic, OpenAI-compatible (OpenRouter, Ollama, GLM), automatic schema normalization

### Parallel Query Execution in Research (commit e0ea291)
- Research pipeline now executes multiple search queries concurrently
- Citation-aware summaries: each result linked to its source query
- **File**: `backend/app/domain/services/agents/research_agent.py`

### Configurable LLM Request Timeout (commit b4c17f6)
- **Setting**: `LLM_REQUEST_TIMEOUT=300.0` (default 5 minutes)
- Prevents hanging on slow providers; configurable per-deployment
- **File**: `backend/app/core/config_llm.py`

### Hard-Stop Enforcement on Tool Loops (commits f6c89e2, 30c3043)
- Detects 5+ consecutive read operations without writes (analysis paralysis)
- **Automatic**: Injects hard-stop signal; guards filter before monitor init
- **Files**: `execution.py`, `tool_efficiency_monitor.py`

### Sandbox WebSocket Support (commit c0b1262)
- **Issue**: CDP screencast WebSocket returned 404 without WebSocket libs
- **Fix**: `uvicorn[standard]==0.37.0` in `sandbox/requirements.runtime.txt`
- **Rebuild**: `docker compose build --no-cache sandbox` required
- **Verification**: `[CDP Stream] WebSocket connected` in logs

### Memory & Workflow Guidelines
- **Update memory on every bug/feature**: Document root cause, fix, and impact
- **Workflow**: Analyze architecture → validate against best practices + Context7 MCP → implement sustainable solution → document

---

## Communication & Accuracy Standards

- **Absolute Status Accuracy Rule**: When creating summaries or status reports, maintain 100% factual accuracy. Never mark a task as "Completed" if it is only partially done or if only foundational code is in place. Always clearly distinguish "Completed", "In Progress", and "Not Started".
- **Absolute Full Implementation Rule**: When requested to write code, provide the full, unabridged implementation for every file. Never use placeholders (e.g., `// ... rest of code`, `// ... implementation details`), summaries, or skipped sections to save space.
- **Absolute Persistence Rule**: If a request is complex, do not simplify it to fit a single response. Output as much valid code as possible, then stop and await a "Continue" prompt to finish the rest. Prioritize absolute completeness over brevity or speed, regardless of task size.
- **Never Skip Pre-existing Errors Rule**: Never skip, ignore, or work around pre-existing errors (lint warnings, type-check failures, test failures, runtime errors). If a pre-existing error is discovered during any task, it MUST be reported and fixed — or explicitly flagged to the user if the fix is out of scope. Silently ignoring errors leads to compounding technical debt and masked failures in production.

## 2026 Best Practices (Context7 MCP Validated - 2026-02-17)

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
- FastAPI: `/websites/fastapi_tiangolo` (Score: 91.4/100, 21,400 snippets)
- Pydantic v2: `/websites/pydantic_dev_2_12` (Score: 83.5/100, 2,770 snippets)
- Pydantic (llmstxt): `/llmstxt/pydantic_dev_llms-full_txt` (Score: 87.6/100, 3,391 snippets)
- Pydantic Settings: `/pydantic/pydantic-settings` (Score: 84.2/100, 202 snippets)
- Docker: `/websites/docker` (Score: 88.5/100)
- Pytest: `/pytest-dev/pytest` (Score: 87.7/100)
- Ruff: `/websites/astral_sh_ruff` (Score: 86.3/100)

**2026 Emerging Patterns (Research-Validated)**:
- **Structured concurrency**: Prefer AnyIO task groups over raw asyncio.gather for proper cancellation
- **SSE best practices**: Include `id:` field and `retry:` for browser reconnect support; 30s heartbeat prevents proxy timeouts
- **LLM adapter pattern**: Abstract via Protocol class; use registry for provider → adapter mapping
- **OpenTelemetry**: Auto-instrument httpx + asyncpg for distributed tracing across LLM calls
- **Container security**: Run image scanning (Trivy/Syft) in CI; never bake secrets into images
- **Rate limit handling**: Exponential backoff with jitter; catch HTTP 429 and rotate API keys

## Detailed Standards

For comprehensive coding standards, see:
- **[Engineering Instructions](instructions.md)** - Core behaviors, leverage patterns, output standards (MUST READ)
- **[Python Standards](docs/guides/PYTHON_STANDARDS.md)** - Pydantic v2, FastAPI, Legacy Flow, async patterns
- **[Vue Standards](docs/guides/VUE_STANDARDS.md)** - Composition API, Pinia, TypeScript
- **[Replay & Sandbox](docs/guides/OPENREPLAY.md)** - Screenshot replay, CDP screencast

---

## Development Environment (macOS + OrbStack)

### Docker Compose Watch (Primary Workflow)

Development uses **Docker Compose Watch** for file sync + HMR. Compose Watch syncs files from
the host into running containers via the Docker API (tar + cp), which **bypasses OrbStack's
TCC/FDA bind-mount restriction** on `~/Desktop/Projects`. Files land on the container's native
ext4 filesystem, so inotify events fire immediately — no polling required.

```
File edit → Docker Compose Watch (host-side) → tar+cp into container → Vite/uvicorn inotify → reload
```

**How it works**:
- `sync` actions copy changed source files into running containers (Vite HMR, uvicorn --reload)
- `rebuild` actions trigger full image rebuild when dependencies change (package.json, requirements.txt)
- `sync+restart` actions copy files and restart the container process (config changes)

### OrbStack TCC Note

OrbStack lost macOS Full Disk Access (TCC) to `~/Desktop/Projects`. Runtime bind mounts from
the project directory fail. Compose Watch bypasses this entirely (uses Docker API, not bind mounts).
The `build: context:` directive still works (sends tarball, not a bind mount).

**To restore direct bind mounts** (optional — Compose Watch is recommended regardless):
1. System Settings → Privacy & Security → Full Disk Access → add OrbStack
2. Add volume mounts back to docker-compose-development.yml if desired

### Legacy rsync fallback

`dev.sh sync` still exists for edge cases. See `dev.sh` header comments for details.

---

## Development Commands

### Full Stack
```bash
./dev.sh watch              # Start stack with live file watch (recommended)
./dev.sh up -d              # Start without watch (image has source from build)
./dev.sh down -v            # Stop and remove volumes
./dev.sh logs -f backend    # Follow logs
```

### Backend
```bash
cd backend && conda activate pythinker
ruff check . && ruff format --check .   # Lint
ruff check --fix . && ruff format .     # Auto-fix
pytest tests/path/to/test_file.py       # Run targeted tests (ALWAYS prefer this)
pytest tests/path/to/directory/         # Run tests for a specific area
pytest -p no:cov -o addopts= tests/test_file.py  # Single test without coverage
# NEVER run `pytest tests/` (full suite) unless explicitly asked
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

### Deep research reliability

**Full detail:** `backend/README.md` (section *Deep Research Reliability*).

- **Summarization:** Pre-summarize compaction and an explicit `summarization_context` passed into `ExecutionAgent.summarize()` instead of mutating `system_prompt` at summarize time for deliverables.
- **Search:** When complexity is high, `SearchTool` uses a deeper `CompactionProfile` (knobs in `config_scraping` / `config_features`).
- **Report verification:** Workflow prompts target real attachment paths; flow state avoids repeated shell thrash once a report attachment exists.
- **Plotly:** `PlotlyCapabilityCheck` in `agent_task_runner`; set `PLOTLY_RUNTIME_AVAILABLE` or use `sandbox/Dockerfile.plotly` / `docker-compose.plotly.yml` when charts must always run.
- **Observability:** Cap-hit and forced-step-advance metrics in `prometheus_metrics.py` (see backend README table).

---

### Browser Architecture

**Standard Browser Stack** (CDP-only):
- **Engine:** Playwright Chromium (lighter, more stable than Chrome for Testing)
- **Control:** Chrome DevTools Protocol (CDP) on port 9222
- **Display:** CDP screencast streaming for real-time user visibility
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
- ✅ CDP screencast health monitoring in SandboxHealth
- ✅ All browser actions visible in real-time via CDP screencast

**Streaming Mode:**
- `SANDBOX_STREAMING_MODE=cdp_only`

**Documentation:**
- **Comprehensive Guide:** `docs/architecture/BROWSER_ARCHITECTURE.md`
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
6. **Redundant Code (DRY violation)** - Never create new files, components, utilities, or services without first searching for existing ones that serve the same or similar purpose; never duplicate logic, debug helpers, or constants
7. **Over-Engineering (KISS violation)** - Avoid unnecessary abstractions, premature generalization, or complex patterns when a simple direct solution works equally well; applies equally to debugging code — use the simplest diagnostic approach first
8. **Direct HTTP Clients** - Never create `httpx.AsyncClient` directly; always use `HTTPClientPool` for connection pooling and metrics
9. **Complex Debug Code** - Debug/diagnostic code must be KISS-compliant: simple, targeted, and removed or scoped behind flags when no longer needed; never add elaborate debug infrastructure for a transient problem

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

## ECC Integration (Quality Gates & Continuous Learning)

Adapted from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) — mechanical enforcement of quality standards and automated pattern learning.

### Hook Profile System

Control hook intensity via environment variable:
- `ECC_HOOK_PROFILE=minimal` — safety hooks only (block-no-verify)
- `ECC_HOOK_PROFILE=standard` — all hooks (default)
- `ECC_HOOK_PROFILE=strict` — all hooks (same as standard)
- `ECC_DISABLED_HOOKS=suggest-compact,console-warn` — disable specific hooks

### Quality Gate Hooks (automatic, in `~/.claude/settings.json`)

| Hook | Phase | Action |
|------|-------|--------|
| `block-no-verify` | PreToolUse:Bash | **BLOCKS** `--no-verify` on git (exit 2) |
| `suggest-compact` | PreToolUse:Edit/Write | Suggests `/compact` every 50 tool calls |
| `doc-file-warning` | PreToolUse:Write | Warns about non-standard `.md` files |
| `quality-gate` | PostToolUse:Edit/Write | Runs `ruff` (Python) / `eslint` (Vue/TS) |
| `post-edit-typecheck` | PostToolUse:Edit | Runs `vue-tsc`/`tsc --noEmit` on `.ts`/`.vue` |
| `console-warn` | PostToolUse:Edit | Warns about `console.log` in JS/TS/Vue |
| `observe` (pre+post) | Pre/PostToolUse:* | Captures tool usage for continuous learning |

### Agents (in `~/.claude/agents/`)

| Agent | Model | When to Use |
|-------|-------|-------------|
| `@planner` | Opus | Complex features, architectural changes, multi-phase work |
| `@security-reviewer` | Sonnet | After auth/API/sandbox/LLM code changes |
| `@refactor-cleaner` | Sonnet | Dead code cleanup, dependency removal |
| `@observer` | Haiku | Analyze observations and extract instincts |

### Commands (in `~/.claude/commands/`)

| Command | Purpose |
|---------|---------|
| `/verify` | Full-stack verification: ruff + pytest + eslint + vue-tsc + console.log audit |
| `/verify quick` | Backend lint + frontend type-check only |
| `/verify pre-pr` | Full checks + security scan |
| `/learn` | Extract reusable patterns from session into skill files |
| `/learn-eval` | Learn + quality gate (checklist + verdict before saving) |
| `/de-sloppify` | Post-implementation cleanup pass (lint, format, types, dead code) |
| `/instinct-status` | Check continuous learning status (observations, instincts) |
| `/evolve` | Analyze observations and create instincts with confidence scoring |

### Continuous Learning System

Observations are captured automatically from every tool call to `~/.claude/homunculus/projects/<hash>/observations.jsonl`. Over time, `/evolve` analyzes these observations and creates "instincts" — atomic learned patterns with confidence scores (0.3–0.9). Instincts that appear in 2+ projects with confidence >= 0.8 get promoted from project-scoped to global.

```bash
# Check status
python3 ~/.claude/hooks/ecc/continuous-learning/instinct-cli.py status

# Analyze patterns (needs 20+ observations)
python3 ~/.claude/hooks/ecc/continuous-learning/instinct-cli.py evolve

# Promote instincts to global
python3 ~/.claude/hooks/ecc/continuous-learning/instinct-cli.py promote --auto
```

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
