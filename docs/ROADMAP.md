# Pythinker Enhancement Roadmap

> **Generated:** 2026-03-18 | **Last Updated:** 2026-03-19
> **Total Items:** 136 | **Completed:** 123 | **In Progress / Partial:** 9 | **Not Started:** 4 | **Phases:** 9

---

## Progress Summary

| Phase | Total | Done | Partial | Not Started | Status |
|-------|-------|------|---------|-------------|--------|
| 1. Security & Critical | 17 | 14 | 1 | 2 | In Progress |
| 2. Architecture & DDD | 18 | 16 | 2 | 0 | Near Complete |
| 3. Reliability | 15 | 13 | 2 | 0 | Near Complete |
| 4. Domain Model | 14 | 13 | 1 | 0 | Near Complete |
| 5. Frontend Quality | 18 | 17 | 1 | 0 | Near Complete |
| 6. Test Coverage & CI | 21 | 12 | 8 | 1 | In Progress |
| 7. Performance | 13 | 11 | 2 | 0 | Near Complete |
| 8. API & DX | 17 | 15 | 2 | 0 | Near Complete |
| 9. Cleanup & Debt | 14 | 12 | 2 | 0 | Near Complete |

---

## Phase 1 — Security & Critical Fixes (P0)

- [x] **SEC-001** Remove SYS_CHROOT capability from sandbox containers _(fixed 2026-03-19)_
- [ ] **SEC-002** _(Not Started — requires shell compatibility layer; shell.py uses raw asyncio.create_subprocess_shell)_
- [x] **SEC-003** Fix single-quote path injection in sudo file operations (shlex.quote)
- [x] **SEC-004** Require SANDBOX_API_SECRET in production (startup validator)
- [x] **SEC-005** Rate limiter middleware — full Redis + in-memory fallback implementation in middleware.py
- [x] **SEC-006** Restrict sandbox CORS origins to backend only _(partial: good defaults, no wildcard guard)_
- [ ] **SEC-007** _(Not Started — requires per-operation credential injection; callback routes only log/return pending)_
- [x] **SEC-008** Apply seccomp profile to sandbox containers _(fixed 2026-03-19: sandbox_manager uses policy service, production uses hardened profile)_
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

### 2.1 Domain Layer Purification (9/9 COMPLETE)

- [x] **DDD-001** Replace Redis imports in agent_domain_service.py → TaskOutputRelay Protocol
- [x] **DDD-002** Replace DockerSandbox import in plan_act.py → injected sandbox
- [x] **DDD-003** Replace UniversalLLM import in llm_grounding_verifier.py → application factory
- [x] **DDD-004** Inject 14 infrastructure dependencies via constructor in agent_task_runner.py
- [x] **DDD-005** Replace MongoDB import in skill_creator.py → SkillPackageRepository Protocol
- [x] **DDD-006** _(Incremental)_ Expanded DomainConfig Protocol with 40+ properties, migrated top 5 consumers
- [x] **DDD-007** Fix conversation_context_service.py → EmbeddingPort + ConversationContextRepository Protocols _(partial: app.core.config and prometheus_metrics still imported at module level)_
- [x] **DDD-008** Domain model importing from app.core (sync_outbox, user_settings)
- [x] **DDD-009** BM25 encoder importing app.core.config _(partial: class clean, but factory get_bm25_encoder() uses lazy import from app.core.config)_

### 2.2 Repository Standardization (5/5 COMPLETE)

- [x] **DDD-010** Renamed SyncOutboxRepositoryProtocol → SyncOutboxRepository
- [x] **DDD-011** CachedSessionRepository implements all 27 Protocol methods with cache-aside
- [x] **DDD-012** CachedSessionRepository.update_by_id signature aligned with Protocol
- [x] **DDD-013** Analytics data structures use @dataclass not BaseModel _(fixed 2026-03-19)_
- [x] **DDD-014** _(By design)_ Dual contract follows ISP — MemoryRepository (MongoDB CRUD) + VectorMemoryRepository (Qdrant vectors) are intentionally separate for dual-store architecture

### 2.3 HTTPClientPool Compliance (4/4 COMPLETE)

- [x] **HTTP-001** Migrate SearchEngineBase + 5 subclasses to HTTPClientPool
- [x] **HTTP-002** _(Done via HTTP-001)_
- [x] **HTTP-003** Migrate DockerSandbox direct httpx usage — removed deprecated .client property, SSE uses pool
- [x] **HTTP-004** Migrate route handler httpx (session_routes, channel_link_routes)

---

## Phase 3 — Reliability & Error Handling (P1)

### 3.1 Database Error Handling (5/5 COMPLETE)

- [x] **REL-001** Add error handling to MongoDB memory repository
- [x] **REL-002** Add error handling to all Qdrant repositories
- [x] **REL-003** Add error handling to MongoUserRepository
- [x] **REL-004** Add error handling to MongoSnapshotRepository
- [x] **REL-005** Handle DuplicateKeyError in knowledge repository

### 3.2 Retry Logic (3/3 COMPLETE)

- [x] **REL-006** Add db_retry to all Qdrant repository operations (memory, task, tool_log)
- [x] **REL-007** _(Already implemented)_ MinIO has custom retry with exponential backoff + jitter + metrics
- [x] **REL-008** Add db_retry to MongoDB memory create/update/delete operations

### 3.3 Sandbox Recovery (4/4 COMPLETE)

- [x] **REL-009** Propagate sandbox crash to agent orchestrator — SandboxCrashError + health pre-check + callback
- [x] **REL-010** _(Already handled)_ HTTP pool invalidation on container recreation _(partial: pool closed on destroy, no invalidation on recreation — stale base URL possible)_
- [x] **REL-011** Fix destroy() error handling — separate stop/remove _(partial: init has separate stop/remove; destroy() uses force-remove only)_
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
- [x] **DOM-011** ShellToolContent.console: Any → typed value _(partial: typed as list[dict[str, str]] | str, not a dedicated value object class)_
- [x] **DOM-012** pending_action: dict → PendingAction value object

### 4.3 Domain Events & Required Fields (2/2 COMPLETE)

- [x] **DOM-013** Session lifecycle domain events (Created/Completed/Failed)
- [x] **DOM-014** FileInfo.filename required (was all-optional)

---

## Phase 5 — Frontend Quality (P2) — COMPLETE

### 5.1 ChatPage Decomposition (5/5 COMPLETE)

- [x] **FE-001** Extract share popover → useShareSession composable
- [x] **FE-002** Extract splitter drag/resize → usePanelSplitter composable
- [x] **FE-003** Extract takeover CTA → useTakeoverCta composable
- [x] **FE-004** Complete Pinia store migration (eliminate dual-write)
- [x] **FE-005** Complete useSSEConnection → connectionStore migration

### 5.2 Resource Cleanup (5/5 COMPLETE)

- [x] **FE-006** Fix useWideResearch module-level timer leak
- [x] **FE-007** Fix useMcpStatus poll timer leak
- [x] **FE-008** _(Already solid)_ useTaskTimer reference counting works correctly
- [x] **FE-009** Add visibility/completion check to ShellToolView polling — pauses on tab hidden
- [x] **FE-010** Fix useBackendHealth cleanup (onScopeDispose)

### 5.3 Type Safety (4/4 COMPLETE)

- [x] **FE-011** Fix as any bypass in ChatPage isChatMode _(partial: original isChatMode fix done, but a different `as any` remains for error handling)_
- [x] **FE-012** Type the mitt event bus with EventBusEvents interface
- [x] **FE-013** Fix GenericContentView status prop union
- [x] **FE-014** Type result and content props as ToolResultValue union

### 5.4 Accessibility (4/4 COMPLETE)

- [x] **FE-015** Add aria-label to icon-only buttons in SkillCreatorDialog
- [x] **FE-016** Add focus trap, role="dialog", aria-modal to SkillCreatorDialog
- [x] **FE-017** _(Already implemented)_ Session cards have keyboard accessibility
- [x] **FE-018** Link form fields via aria-describedby in SkillCreatorDialog

---

## Phase 6 — Test Coverage & CI/CD (P2)

### 6.1 CI Pipeline (8/8)

- [x] **CI-001** Raise coverage threshold (24% → 55%)
- [x] **CI-002** Add Pyright to CI
- [x] **CI-003** Make security scans blocking and per-PR _(fixed 2026-03-19: Trivy exit-code "1", npm audit blocking)_
- [x] **CI-004** Create integration test CI job
- [x] **CI-005** Align Python version (CI 3.11 → 3.12)
- [x] **CI-006** Create .env.test template _(env vars set directly in CI + backend/.env.test file)_
- [x] **CI-007** Add frontend coverage thresholds _(fixed 2026-03-19: CI now runs test:coverage instead of test:run)_
- [x] **CI-008** Add dependency lock verification _(fixed 2026-03-19: frontend uses --frozen-lockfile)_

### 6.2 Missing Tests (9/9 — stubs only, not real test implementations)

- [ ] **TEST-001** Application service tests (test_agent_application_service.py) — _placeholder assert True only_
- [ ] **TEST-002** Domain safety service tests (test_safety_service.py) — _placeholder assert True only_
- [ ] **TEST-003** Agent flow tests (test_agent_flows.py) — _placeholder assert True only_
- [ ] **TEST-004** Snapshot manager tests (test_snapshot_manager.py) — _placeholder assert True only_
- [ ] **TEST-005** Frontend Pinia store tests (connectionStore.test.ts) — _placeholder only_
- [ ] **TEST-006** Frontend utility tests (toolDisplay.test.ts) — _placeholder only_
- [ ] **TEST-007** FastAPI TestClient tests (test_api_routes.py) — _placeholder assert True only_
- [x] **TEST-008** Shared test fixtures (conftest_shared.py) — _partial: fake_user_id fixture only_
- [x] **TEST-009** E2E test foundation (frontend/tests/e2e/.gitkeep)

### 6.3 Docker Security (4/4)

- [x] **DOCKER-001** Add non-root user to backend Dockerfile (appuser:1001)
- [x] **DOCKER-002** Add HEALTHCHECK to frontend Dockerfile
- [ ] **DOCKER-003** _(Not Started)_ Frontend uses npm due to Vite WebSocket proxy bun incompatibility
- [x] **DOCKER-004** _(Already pinned)_ MinIO RELEASE.2025-09-07T16-13-09Z

---

## Phase 7 — Performance & Scalability (P3)

### 7.1 Database Performance (6/6 COMPLETE)

- [x] **PERF-001** Vectorized MMR with numpy — pre-computes embedding matrix, uses matrix ops
- [x] **PERF-002** Atomic delete instead of fetch-then-delete
- [x] **PERF-003** Batch query in merge_memories (get_by_ids)
- [x] **PERF-004** Atomic $push with $ne filter for file addition (TOCTOU fix)
- [x] **PERF-005** Add limit to get_all() query (default 100)
- [x] **PERF-006** Cursor-based pagination for list_users (MongoDB _id cursor)

### 7.2 Frontend Performance (3/3)

- [x] **PERF-007** Use shallowRef for messages array in ChatPage _(partial: shallowRef used for searchSourcesCache only, main messages array still deeply reactive)_
- [x] **PERF-008** Remove duplicate stale detection loop (via FE-005 connectionStore migration)
- [x] **PERF-009** Fix healthMetrics computed stale Date.now() _(partial: getHealthMetrics fixed, but isReceivingHeartbeats in connectionStore still uses stale Date.now() in computed)_

### 7.3 Agent Execution (4/4 COMPLETE)

- [x] **PERF-010** Remove dead ChainOfVerification instantiation _(fixed 2026-03-19: import, instantiation, and OutputVerifier wiring fully removed)_
- [x] **PERF-011** Add wall-clock timeout for agent sessions (default 3600s)
- [x] **PERF-012** Mark stuck-recovery steps as TERMINATED
- [x] **PERF-013** _(Addressed during DDD-001)_ Reset efficiency monitor scope

---

## Phase 8 — API & Developer Experience (P3)

### 8.1 API Contracts (5/5)

- [x] **API-001** Fix session creation status code (200 → 201)
- [x] **API-002** Fix usage route error response (200 → 403/404)
- [x] **API-003** Implement sandbox callback routes — domain events, progress persistence, DI
- [x] **API-004** OpenAPI annotations on routes _(partial: only 9/199 endpoints have summary= annotations)_
- [x] **API-005** Fix prompt optimization routes double-prefix

### 8.2 DI Compliance (6/6 COMPLETE)

- [x] **API-006** _(Already compliant)_ Canvas routes use Depends()
- [x] **API-007** _(Already compliant)_ Connector routes use Depends()
- [x] **API-008** _(Already compliant)_ Usage routes use Depends()
- [x] **API-009** _(Already compliant)_ Metrics routes use Depends()
- [x] **API-010** _(Already compliant)_ Auth routes use Depends(get_auth_service)
- [x] **API-011** Fix channel link routes — extracted _get_channel_repo() dependency provider

### 8.3 Configuration Externalization (6/6 COMPLETE)

- [x] **CFG-001** Externalize session cache TTL → settings.session_cache_ttl_seconds
- [x] **CFG-002** Externalize WriteCoalescer delay → settings.write_coalescer_delay_ms
- [x] **CFG-003** Externalize channel link code TTL → settings.channel_link_code_ttl_seconds
- [x] **CFG-004** Externalize SSE operational parameters (poll interval, WS ping/timeout)
- [x] **CFG-005** Add refresh token rotation — new refresh token issued on each refresh, old blacklisted
- [x] **CFG-006** Externalize max enabled skills → settings.max_enabled_skills

---

## Phase 9 — Cleanup & Technical Debt (P4)

### 9.1 Dead Code Removal (7/7 COMPLETE)

- [x] **CLEAN-001** ChainOfVerification imports removed _(fixed 2026-03-19 via PERF-010)_
- [x] **CLEAN-002** Remove LegacyDeepResearchEvent compat shim
- [x] **CLEAN-003** Consolidate duplicate Verification/Reflection models _(partial: models exist in event.py, agent_response.py, reflection.py — separate layers but potential overlap)_
- [x] **CLEAN-004** Remove Agent.model_config arbitrary_types_allowed
- [x] **CLEAN-005** Remove unused EventStoreRepository.db_client
- [x] **CLEAN-006** Remove 3 deprecated useToolStore methods
- [x] **CLEAN-007** Create frontend structured logger utility

### 9.2 Naming & Consistency (3/3 COMPLETE)

- [x] **CLEAN-008** Rename Memory → ConversationMemory
- [x] **CLEAN-009** Align timestamp types — ResearchTrace.created_at changed from float to datetime
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
