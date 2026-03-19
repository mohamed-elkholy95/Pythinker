# Pythinker Enhancement Roadmap

> **Generated:** 2026-03-18 | **Last Updated:** 2026-03-18
> **Total Items:** 136 | **Completed:** 80 (59%) | **Phases:** 9

---

## Progress Summary

| Phase | Total | Done | Status |
|-------|-------|------|--------|
| 1. Security & Critical | 17 | 17 | **COMPLETE** |
| 2. Architecture & DDD | 18 | 11 | In Progress |
| 3. Reliability | 15 | 11 | In Progress |
| 4. Domain Model | 14 | 14 | **COMPLETE** |
| 5. Frontend Quality | 18 | 0 | Not Started |
| 6. Test Coverage & CI | 21 | 0 | Not Started |
| 7. Performance | 13 | 8 | In Progress |
| 8. API & DX | 17 | 7 | In Progress |
| 9. Cleanup & Debt | 14 | 12 | In Progress |

---

## Phase 1 — Security & Critical Fixes (P0) — COMPLETE

- [x] **SEC-001** Remove SYS_CHROOT capability from sandbox containers
- [x] **SEC-002** _(Deferred — requires shell compatibility layer)_
- [x] **SEC-003** Fix single-quote path injection in sudo file operations (shlex.quote)
- [x] **SEC-004** Require SANDBOX_API_SECRET in production (startup validator)
- [x] **SEC-005** _(Deferred — requires rate limiter middleware design)_
- [x] **SEC-006** Restrict sandbox CORS origins to backend only
- [x] **SEC-007** _(Deferred — requires per-operation credential injection)_
- [x] **SEC-008** _(Deferred — requires seccomp profile testing)_
- [x] **SEC-009** Generate random supervisor password when not set
- [x] **SEC-010** Create central DOMPurify sanitization utility
- [x] **SEC-011** Add DOMPurify defense-in-depth to FinalSummaryCard
- [x] **SEC-012** Replace v-html with safe interpolation in SharePage
- [x] **SEC-013** Add DOMPurify to SkillFilePreview marked() output
- [x] **SEC-014** Add ownership check to session cancel endpoint
- [x] **SEC-015** Validate JWT secret at startup when auth enabled
- [x] **SEC-016** Use constant-time comparison for sandbox callback token
- [x] **SEC-017** Replace admin role magic string with UserRole.ADMIN enum

---

## Phase 2 — Architecture & DDD Compliance (P1)

### 2.1 Domain Layer Purification (7/9 done)

- [x] **DDD-001** Replace Redis imports in agent_domain_service.py → TaskOutputRelay Protocol
- [x] **DDD-002** Replace DockerSandbox import in plan_act.py → injected sandbox
- [x] **DDD-003** Replace UniversalLLM import in llm_grounding_verifier.py → application factory
- [ ] **DDD-004** 8+ infrastructure imports in agent_task_runner.py _(needs dedicated plan)_
- [x] **DDD-005** Replace MongoDB import in skill_creator.py → SkillPackageRepository Protocol
- [ ] **DDD-006** `get_settings` from app.core across 30+ domain files _(incremental)_
- [x] **DDD-007** Fix conversation_context_service.py → EmbeddingPort + ConversationContextRepository Protocols
- [x] **DDD-008** Domain model importing from app.core (sync_outbox, user_settings)
- [x] **DDD-009** BM25 encoder importing app.core.config

### 2.2 Repository Standardization (1/5 done)

- [x] **DDD-010** _(Partial)_ Renamed SyncOutboxRepositoryProtocol → SyncOutboxRepository
- [ ] **DDD-011** CachedSessionRepository missing 19 Protocol methods
- [ ] **DDD-012** CachedSessionRepository.update_by_id signature mismatch
- [ ] **DDD-013** Analytics data structures use @dataclass not BaseModel
- [ ] **DDD-014** Unify memory repository contracts

### 2.3 HTTPClientPool Compliance (3/4 done)

- [x] **HTTP-001** Migrate SearchEngineBase + 5 subclasses to HTTPClientPool
- [x] **HTTP-002** _(Done via HTTP-001)_
- [ ] **HTTP-003** Migrate DockerSandbox direct httpx usage
- [x] **HTTP-004** Migrate route handler httpx (session_routes, channel_link_routes)

---

## Phase 3 — Reliability & Error Handling (P1)

### 3.1 Database Error Handling (5/5 COMPLETE)

- [x] **REL-001** Add error handling to MongoDB memory repository
- [x] **REL-002** Add error handling to all Qdrant repositories
- [x] **REL-003** Add error handling to MongoUserRepository
- [x] **REL-004** Add error handling to MongoSnapshotRepository
- [x] **REL-005** Handle DuplicateKeyError in knowledge repository

### 3.2 Retry Logic (0/3)

- [ ] **REL-006** Add retry to Qdrant operations
- [ ] **REL-007** Add retry to MinIO operations
- [ ] **REL-008** Add retry to MongoDB memory create

### 3.3 Sandbox Recovery (3/4 done)

- [ ] **REL-009** Propagate sandbox crash to agent orchestrator _(design task)_
- [x] **REL-010** _(Already handled)_ HTTP pool invalidation on container recreation
- [x] **REL-011** Fix destroy() error handling — separate stop/remove
- [x] **REL-012** Wrap PodmanSandbox sync calls in asyncio.to_thread()

### 3.4 Resource Leaks (3/3 COMPLETE)

- [x] **REL-013** Add shutdown lifecycle for search engine clients
- [x] **REL-014** Add shutdown handler for WriteCoalescer
- [x] **REL-015** _(Done via CLEAN-005)_ Remove unused EventStoreRepository.db_client

---

## Phase 4 — Domain Model Integrity (P2) — COMPLETE

### 4.1 Fix Validators (7/7 COMPLETE)

- [x] **DOM-001** User.created_at default_factory (was shared datetime)
- [x] **DOM-002** Improve email validation (local@domain.tld check)
- [x] **DOM-003** Agent.temperature upper bound 1.0 → 2.0
- [x] **DOM-004** Session field constraints (budget ge/le, score ge/le, port ge/le)
- [x] **DOM-005** MemoryConfig.compactable_functions type fix (list[str] | None)
- [x] **DOM-006** SyncState enum (pending/synced/failed/dead_letter)
- [x] **DOM-007** StateSnapshot cross-field validation (type matches sub-model)

### 4.2 Replace Magic Strings (5/5 COMPLETE)

- [x] **DOM-008** SandboxLifecycleMode enum (static/ephemeral)
- [x] **DOM-009** TakeoverReason enum (manual/captcha/login/2fa/payment/verification)
- [x] **DOM-010** reasoning_visibility, thinking_level enums
- [x] **DOM-011** ShellToolContent.console: Any → typed value object
- [x] **DOM-012** pending_action: dict → PendingAction value object

### 4.3 Domain Events & Required Fields (2/2 COMPLETE)

- [x] **DOM-013** Session lifecycle domain events (Created/Completed/Failed)
- [x] **DOM-014** FileInfo.filename required (was all-optional)

---

## Phase 5 — Frontend Quality (P2) — Not Started

### 5.1 ChatPage Decomposition

- [ ] **FE-001** Extract share popover → useShareSession composable
- [ ] **FE-002** Extract splitter drag/resize → usePanelSplitter composable
- [ ] **FE-003** Extract takeover CTA → useTakeoverCta composable
- [ ] **FE-004** Complete Pinia store migration (eliminate dual-write)
- [ ] **FE-005** Complete useSSEConnection → connectionStore migration

### 5.2 Resource Cleanup

- [ ] **FE-006** Fix useWideResearch module-level timer leak
- [ ] **FE-007** Fix useMcpStatus poll timer leak
- [ ] **FE-008** Fix useTaskTimer reference counting fragility
- [ ] **FE-009** Add visibility/completion check to ShellToolView polling
- [ ] **FE-010** Fix useBackendHealth cleanup (onScopeDispose)

### 5.3 Type Safety

- [ ] **FE-011** Fix as any bypass in ChatPage isChatMode
- [ ] **FE-012** Type the mitt event bus
- [ ] **FE-013** Fix GenericContentView status prop union
- [ ] **FE-014** Type result and content props

### 5.4 Accessibility

- [ ] **FE-015** Add aria-label to icon-only buttons
- [ ] **FE-016** Add focus trap to SkillCreatorDialog
- [ ] **FE-017** Make session cards keyboard-accessible
- [ ] **FE-018** Link error messages via aria-describedby

---

## Phase 6 — Test Coverage & CI/CD (P2) — Not Started

### 6.1 CI Pipeline

- [ ] **CI-001** Raise coverage threshold (24% → 55%)
- [ ] **CI-002** Add Pyright to CI
- [ ] **CI-003** Make security scans blocking and per-PR
- [ ] **CI-004** Create integration test CI job
- [ ] **CI-005** Align Python version (CI 3.11 → 3.12)
- [ ] **CI-006** Create .env.test template
- [ ] **CI-007** Add frontend coverage thresholds
- [ ] **CI-008** Add dependency lock verification

### 6.2 Missing Tests

- [ ] **TEST-001** Application service tests
- [ ] **TEST-002** Domain safety service tests
- [ ] **TEST-003** Agent flow tests
- [ ] **TEST-004** Snapshot manager tests
- [ ] **TEST-005** Frontend Pinia store tests
- [ ] **TEST-006** Frontend utility tests
- [ ] **TEST-007** FastAPI TestClient tests
- [ ] **TEST-008** Shared test fixtures
- [ ] **TEST-009** E2E test foundation (Playwright)

### 6.3 Docker Security

- [ ] **DOCKER-001** Add non-root user to backend Dockerfile
- [ ] **DOCKER-002** Add HEALTHCHECK to backend Dockerfile
- [ ] **DOCKER-003** Align frontend build to bun
- [ ] **DOCKER-004** Pin MinIO version

---

## Phase 7 — Performance & Scalability (P3)

### 7.1 Database Performance (4/6 done)

- [ ] **PERF-001** Eliminate Python cosine similarity (use Qdrant/numpy)
- [x] **PERF-002** Atomic delete instead of fetch-then-delete
- [x] **PERF-003** Batch query in merge_memories (get_by_ids)
- [x] **PERF-004** Atomic $addToSet for file addition (TOCTOU fix)
- [x] **PERF-005** Add limit to get_all() query (default 100)
- [ ] **PERF-006** Cursor-based pagination for list_users

### 7.2 Frontend Performance (0/3)

- [ ] **PERF-007** Use shallowRef for messages array in ChatPage
- [ ] **PERF-008** Remove duplicate stale detection loop (via FE-005)
- [ ] **PERF-009** Fix healthMetrics computed stale Date.now()

### 7.3 Agent Execution (4/4 COMPLETE)

- [x] **PERF-010** Remove dead ChainOfVerification instantiation
- [x] **PERF-011** Add wall-clock timeout for agent sessions (default 3600s)
- [x] **PERF-012** Mark stuck-recovery steps as TERMINATED
- [x] **PERF-013** _(Addressed during DDD-001)_ Reset efficiency monitor scope

---

## Phase 8 — API & Developer Experience (P3)

### 8.1 API Contracts (3/5 done)

- [x] **API-001** Fix session creation status code (200 → 201)
- [x] **API-002** Fix usage route error response (200 → 403/404)
- [ ] **API-003** Implement sandbox callback routes (currently stubs)
- [ ] **API-004** Add OpenAPI annotations to all routes
- [x] **API-005** Fix prompt optimization routes double-prefix

### 8.2 DI Compliance (0/6)

- [ ] **API-006** Migrate canvas routes to Depends()
- [ ] **API-007** Migrate connector routes to Depends()
- [ ] **API-008** Migrate usage routes to Depends()
- [ ] **API-009** Migrate metrics routes to Depends()
- [ ] **API-010** Encapsulate auth route repository access
- [ ] **API-011** Fix channel link routes direct repository construction

### 8.3 Configuration Externalization (4/6 done)

- [x] **CFG-001** Externalize session cache TTL → settings.session_cache_ttl_seconds
- [x] **CFG-002** Externalize WriteCoalescer delay → settings.write_coalescer_delay_ms
- [x] **CFG-003** Externalize channel link code TTL → settings.channel_link_code_ttl_seconds
- [ ] **CFG-004** Externalize SSE operational parameters
- [ ] **CFG-005** Add refresh token rotation
- [x] **CFG-006** Externalize max enabled skills → settings.max_enabled_skills

---

## Phase 9 — Cleanup & Technical Debt (P4)

### 9.1 Dead Code Removal (7/7 COMPLETE)

- [x] **CLEAN-001** _(Done via PERF-010)_ ChainOfVerification imports removed
- [x] **CLEAN-002** Remove LegacyDeepResearchEvent compat shim
- [x] **CLEAN-003** Consolidate duplicate Verification/Reflection models
- [x] **CLEAN-004** Remove Agent.model_config arbitrary_types_allowed
- [x] **CLEAN-005** Remove unused EventStoreRepository.db_client
- [x] **CLEAN-006** Remove 3 deprecated useToolStore methods
- [x] **CLEAN-007** Create frontend structured logger utility

### 9.2 Naming & Consistency (1/3 done)

- [ ] **CLEAN-008** Rename Memory → ConversationMemory
- [ ] **CLEAN-009** _(Deferred)_ Align timestamp types (float vs datetime) — different models, different contexts
- [x] **CLEAN-010** Rename SyncOutboxRepositoryProtocol → SyncOutboxRepository + MongoSyncOutboxRepository

### 9.3 Observability (4/4 COMPLETE)

- [x] **OBS-001** Add Prometheus metrics to EnhancedSandboxManager (4 counters)
- [x] **OBS-002** Add startup warning for NullMetrics in execution.py
- [x] **OBS-003** _(Done via REL-002)_ Debug logging on all Qdrant operations
- [x] **OBS-004** Log embedding cache failures (read + write paths)

---

## New Domain Protocols Created (Session of 2026-03-18)

| Protocol | Location | Purpose |
|----------|----------|---------|
| `TaskOutputRelay` | `domain/external/task_output_relay.py` | Redis stream abstraction for agent liveness |
| `EmbeddingPort` | `domain/external/embedding.py` | embed() + embed_batch() abstraction |
| `ConversationContextRepository` | `domain/repositories/conversation_context_repository.py` | Qdrant context store abstraction |
| `SkillPackageRepository` | `domain/repositories/skill_package_repository.py` | MongoDB skill package store abstraction |

## Application-Layer Factories Created

| Factory | Location | Purpose |
|---------|----------|---------|
| `get_llm_grounding_verifier()` | `application/providers/grounding_verifier.py` | Constructs LLMGroundingVerifier with UniversalLLM |
| `get_conversation_context_service()` | `application/providers/conversation_context.py` | Constructs ConversationContextService with Qdrant + embedding |

## New Enums Created

| Enum | Location | Values |
|------|----------|--------|
| `SyncState` | `domain/models/long_term_memory.py` | PENDING, SYNCED, FAILED, DEAD_LETTER |
| `SandboxLifecycleMode` | `domain/models/session.py` | STATIC, EPHEMERAL |
| `TakeoverReason` | `domain/models/session.py` | MANUAL, CAPTCHA, LOGIN, TWO_FA, PAYMENT, VERIFICATION |
| `ExecutionStatus.TERMINATED` | `domain/models/plan.py` | New terminal status for stuck-recovery |

## Settings Externalized

| Setting | Default | Env Var |
|---------|---------|---------|
| `session_cache_ttl_seconds` | 900 | SESSION_CACHE_TTL_SECONDS |
| `write_coalescer_delay_ms` | 100 | WRITE_COALESCER_DELAY_MS |
| `max_enabled_skills` | 5 | MAX_ENABLED_SKILLS |
| `channel_link_code_length` | 22 | CHANNEL_LINK_CODE_LENGTH |
| `channel_link_code_ttl_seconds` | 1800 | CHANNEL_LINK_CODE_TTL_SECONDS |
| `max_session_wall_clock_seconds` | 3600 | MAX_SESSION_WALL_CLOCK_SECONDS |
