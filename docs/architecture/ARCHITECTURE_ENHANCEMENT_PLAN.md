# Comprehensive Pythinker Architecture Enhancement Plan

> **Status**: In Progress (Sprint 1)
> **Created**: 2026-02-25
> **Scope**: 12 phases, 42 new files, ~48 modified files

---

## Context

Pythinker is a 155K+ LOC AI agent platform with strong DDD foundations but significant technical debt:

| Problem | Metric |
|---------|--------|
| God classes | `execution.py` (2,879 LOC), `plan_act.py` (3,563 LOC), `ChatPage.vue` (4,498 LOC) |
| Reactive token management | Catches `TokenLimitExceededError` instead of proactive budget |
| No Pinia state management | 50+ scattered reactive refs across composables |
| String-based tool names | Magic strings across 43 tools in 4+ files |
| DSPy offline-only | `dspy_adapter.py` exists but no runtime structured prompting |
| Scattered verification | 7+ services invoked at random points |
| No frontend observability | Sparse Grafana dashboards |

---

## Execution Order & Dependencies

```
Sprint 1 (parallel — no dependencies):
  ✅ Phase 1: Tool Registry Reformation
  ✅ Phase 2: Token Budget Manager & Context Handler
  ✅ Phase 7: Pinia State Architecture

Sprint 2 (depends on Sprint 1):
  ✅ Phase 3: God Class Decomposition (needs Phase 2)
  ⬜ Phase 8: ChatPage Decomposition (needs Phase 7)

Sprint 3 (depends on Sprint 2):
  ⬜ Phase 4: DDD Enforcement (needs Phase 3)
  ⬜ Phase 5: Verification Pipeline (needs Phase 3 + Phase 1)
  ⬜ Phase 9: Frontend Performance (needs Phase 8)

Sprint 4 (depends on Sprint 3):
  ⬜ Phase 6: DSPy Runtime Integration (needs Phase 2 + 3 + 5)
  ⬜ Phase 10: Sandbox Enhancement
  ⬜ Phase 11: Observability Layer

Sprint 5:
  ⬜ Phase 12: Infrastructure Hardening (needs Phase 11)
```

---

## BACKEND PHASES

### Phase 1: Tool Registry Reformation [S — 3 days]

**Problem**: 43 tools referenced by magic strings (`"file_read"`, `"shell_exec"`) across `base.py`, `execution.py`, `dynamic_toolset.py`, `tool_efficiency_monitor.py`. Fragile coupling, no compile-time safety.

**Status**: ✅ Complete (permanently enabled — no rollback flag)

#### New Files

| File | Purpose | Status |
|------|---------|--------|
| `backend/app/domain/models/tool_name.py` | `ToolName(str, Enum)` with all 43+ tools + classmethods `is_read_only()`, `is_safe_parallel()`, `for_phase()` | ✅ Created |
| `backend/app/domain/models/tool_capability.py` | `ToolCapability` Pydantic model: `name: ToolName`, `parallelizable: bool`, `risk_level`, `phase_restrictions`, `max_concurrent` | ✅ Created |

#### Modified Files

| File | Change | Status |
|------|--------|--------|
| `backend/app/domain/services/agents/base.py` | Replace `SAFE_PARALLEL_TOOLS`, `PHASE_TOOL_GROUPS`, `search_functions` with `ToolName` enum methods | ✅ Done |
| `backend/app/domain/services/agents/execution.py` | Replace string tool checks in `_track_sources_from_tool_event`, `_track_multimodal_findings` | ✅ Done |
| `backend/app/domain/services/tools/dynamic_toolset.py` | Register tools using `ToolCapability` | ✅ Done |
| `backend/app/domain/services/agents/tool_efficiency_monitor.py` | Use `ToolName.is_read_only()` instead of `_is_read_tool()` heuristic | ✅ Done |

**Rollback**: Permanently enabled (no feature flag). ToolName enum is backward-compatible (`str` subclass).

#### Key Design

```python
class ToolName(str, Enum):
    FILE_READ = "file_read"
    # ... 43+ members

    @property
    def is_read_only(self) -> bool: ...

    @classmethod
    def for_phase(cls, phase: str) -> frozenset[ToolName] | None: ...

    @classmethod
    def is_read_tool(cls, tool_name: str) -> bool: ...
```

---

### Phase 2: Token Budget Manager & Context Handler [L — 7 days]

**Problem**: Context assembly is unbudgeted. `TokenManager` counts tokens reactively. `MemoryManager` compacts only after `TokenLimitExceededError`. No phase-level allocation.

**Status**: ✅ New files created

#### Existing Infrastructure

- `backend/app/domain/services/agents/token_manager.py` — `TokenManager` with `PressureStatus`, `count_tokens()`, LRU cache
- `backend/app/domain/services/agents/memory_manager.py` — `MemoryManager` with `SemanticCompressor`, `TemporalCompressor`

#### New Files

| File | Purpose | Status |
|------|---------|--------|
| `backend/app/domain/services/agents/token_budget_manager.py` | `TokenBudgetManager` — proactive phase-level budget allocation: system_prompt (15%), planning (10%), execution (50%), memory (10%), summarization (15%) | ✅ Created |
| `backend/app/domain/services/agents/sliding_window_context.py` | `SlidingWindowContextManager` — priority-based message retention with `MessagePriority` enum (SYSTEM=100, USER_CURRENT=90, TOOL_RECENT=70, etc.) | ✅ Created |
| `backend/app/domain/services/agents/context_compression_pipeline.py` | Three-stage pipeline: summarize → truncate → drop | ✅ Created |

#### Modified Files

| File | Change | Status |
|------|--------|--------|
| `backend/app/domain/services/agents/base.py` | Inject `TokenBudgetManager`, call `sliding_window.prepare_messages()` before every LLM call | ✅ Done |
| `backend/app/domain/services/agents/execution.py` | Replace `_ensure_within_token_limit()` with `budget.check_before_call()` | ✅ Done |
| `backend/app/domain/services/agents/step_context_assembler.py` | Accept `TokenBudget`, enforce phase budget during assembly | ✅ Done |
| `backend/app/domain/services/flows/plan_act.py` | Create `TokenBudget` at flow start, pass through phases, call `rebalance()` at transitions | ✅ Done |
| `backend/app/domain/services/agents/memory_manager.py` | Integrate with `TokenBudgetManager` for proactive compaction triggers | ✅ Done |

**Feature flag**: `feature_token_budget_manager: bool = False` (gates the budget-aware path; sliding window activates automatically with it)

#### Key Design

```python
class TokenBudgetManager:
    DEFAULT_ALLOCATIONS = {
        BudgetPhase.SYSTEM_PROMPT: 0.15,
        BudgetPhase.PLANNING: 0.10,
        BudgetPhase.EXECUTION: 0.50,
        BudgetPhase.MEMORY_CONTEXT: 0.10,
        BudgetPhase.SUMMARIZATION: 0.15,
    }

    def check_before_call(self, budget, phase, messages, tools) -> tuple[bool, str]:
        """Pre-flight: can this LLM call fit within phase budget?"""

    def compress_to_fit(self, budget, phase, messages, target) -> list[dict]:
        """Graceful degradation: summarize → truncate → drop"""

    def rebalance(self, budget, completed_phase, next_phase) -> None:
        """Redistribute unused tokens from completed to next phase."""
```

---

### Phase 3: God Class Decomposition [XL — 14 days]

**Dependencies**: Phase 2

#### 3A: ExecutionAgent Decomposition (2,879 LOC → 4 classes)

| New File | Extracted From | Key Methods |
|----------|---------------|-------------|
| `backend/app/domain/services/agents/step_executor.py` | `execute_step()` (lines 274-516) | `async execute(plan, step, message, context, budget) -> AsyncGenerator` |
| `backend/app/domain/services/agents/response_generator.py` | `summarize()` (lines 517-820+) | `async generate(policy, budget, bibliography) -> AsyncGenerator` |
| `backend/app/domain/services/agents/output_verifier.py` | Hallucination/critic/CoVe calls | `async verify(content, request, sources) -> VerificationResult` |
| `backend/app/domain/services/agents/source_tracker.py` | `_track_sources_from_tool_event`, citation counter | `track(tool_event)`, `build_bibliography() -> str` |

**Result**: `ExecutionAgent` becomes a thin coordinator (~400 LOC).

#### 3B: PlanActFlow Decomposition (3,563 LOC → 5 classes)

| New File | Extracted From | Key Methods |
|----------|---------------|-------------|
| `backend/app/domain/services/flows/phase_router.py` | `_assign_phases_to_plan()`, `_should_skip_step()`, `_check_step_dependencies()` | `route(plan, step) -> PhaseDecision` |
| `backend/app/domain/services/flows/flow_step_executor.py` | Step execution loop, multi-agent dispatch | `async execute_steps(plan, message) -> AsyncGenerator` |
| `backend/app/domain/services/flows/error_recovery_handler.py` | `handle_error_state()`, error counting, recovery | `async handle(error, state) -> RecoveryAction` |
| Existing `checkpoint_manager.py` | Already partially extracted | Extend with `_save_progress_artifact()` |

**Result**: `PlanActFlow` → `PlanActOrchestrator` (~800 LOC).

#### 3C: AgentTaskRunner Decomposition (2,144 LOC → 3 classes)

| New File | Extracted From | Key Methods |
|----------|---------------|-------------|
| `backend/app/domain/services/file_sync_manager.py` | `_sync_file_to_storage()`, `_sweep_workspace_files()` | `async sync_file(path, content_type) -> FileInfo` |
| Existing `tool_event_handler.py` | Extend with event enrichment logic | `handle_tool_event(event) -> EnrichedEvent` |

**Result**: `AgentTaskRunner` (~600 LOC).

**Rollback**: Permanently enabled (no feature flag). Decomposed classes are unconditionally active and fully replace inline implementations.

---

### Phase 4: DDD Enforcement [L — 7 days]

**Dependencies**: Phase 3

#### New Files

| File | Purpose |
|------|---------|
| `backend/app/domain/models/value_objects.py` | `SessionId`, `AgentId`, `UserId` — immutable Pydantic value objects |
| `backend/app/domain/aggregates/session_aggregate.py` | `SessionAggregate` — session state machine invariants |
| `backend/app/domain/aggregates/plan_aggregate.py` | `PlanAggregate` — step lifecycle, dependency validation |
| `backend/app/domain/ports/settings_port.py` | `AgentSettingsPort(Protocol)` — domain-level port for config |

#### Layer Violations to Fix

| File | Current Violation | Fix |
|------|------------------|-----|
| `plan_act.py` line 90 | `from app.core.config import get_settings` | Inject via `AgentSettingsPort` |
| `plan_act.py` line 753 | `from app.infrastructure.external.sandbox...` | Use `Sandbox` protocol |
| `agent_task_runner.py` line 360 | `from app.infrastructure.external.scraper` | DI via constructor |

**Feature flag**: `feature_ddd_value_objects: bool = False`

---

### Phase 5: Verification Pipeline Abstraction [M — 5 days]

**Dependencies**: Phase 3, Phase 1

**Problem**: 7+ verification services invoked at scattered points: `CriticAgent`, `ChainOfVerification`, `GroundingValidator`, `LettuceVerifier`, `OutputCoverageValidator`, `DeliveryFidelityChecker`, `ComplianceGates`.

#### New Files

| File | Purpose |
|------|---------|
| `backend/app/domain/services/verification/__init__.py` | Package |
| `backend/app/domain/services/verification/orchestrator.py` | `VerificationOrchestrator` — pluggable pipeline with `VerificationLevel` and `VerificationStage` |
| `backend/app/domain/services/verification/adapters.py` | Adapter wrappers implementing `Validator(Protocol)` |

#### Key Design

```python
class VerificationOrchestrator:
    def __init__(self, validators: list[Validator], level: VerificationLevel): ...

    async def verify(self, content, context, stage) -> PipelineResult:
        """Run validators for stage/level. Short-circuit on hard reject."""
```

#### Modified Files

| File | Change |
|------|--------|
| `execution.py` | Replace scattered validator calls with `orchestrator.verify()` |
| `plan_act.py` | Inject `VerificationOrchestrator` with flow-appropriate level |
| `config_features.py` | Add `verification_level: str = "standard"` |

---

### Phase 6: DSPy Runtime Integration [XL — 14 days]

**Dependencies**: Phase 2 + 3 + 5

**Problem**: `dspy_adapter.py` exists with signatures but is offline-only. No runtime structured prompting, no output assertions.

#### New Files

| File | Purpose |
|------|---------|
| `backend/app/domain/services/agents/dspy_assertions.py` | `OutputAssertions` — pure-Python runtime validators: `assert_plan_structure()`, `assert_no_hallucinated_tools()`, `assert_citation_coverage()`, `assert_entity_preservation()` |
| `backend/app/domain/services/agents/structured_prompting.py` | `StructuredPromptBuilder` — budget-aware structured prompt construction integrating `TokenBudgetManager`, `PromptProfileResolver`, and `OutputAssertions` |

#### Modified Files

| File | Change |
|------|--------|
| `dspy_adapter.py` | Add `ReflectionSignature`, `SummarizationSignature` |
| `optimizer_orchestrator.py` | Add reflection/summarization optimization targets |
| `plan_act.py` | Wire `StructuredPromptBuilder` into flow phases |
| `base.py` | Run `OutputAssertions.validate()` after every `ask()`, retry on failure (max 1) |

**Feature flags**: `feature_dspy_runtime_assertions: bool = False`, `feature_structured_prompting: bool = False`

---

## FRONTEND PHASES

### Phase 7: Pinia State Architecture [H — 3 days]

**Problem**: No Pinia. State scattered across 50+ `ref()` in `ChatPage.vue` `createInitialState()` and module-level singletons in composables.

**Status**: ✅ All stores created, Pinia installed and mounted. Composable wrappers pending.

#### New Files (6)

| File | State Domain | Status |
|------|-------------|--------|
| `frontend/src/stores/authStore.ts` | Auth: `currentUser`, `isAuthenticated`, `authError` | ✅ Created |
| `frontend/src/stores/sessionStore.ts` | Session: `sessionId`, `messages[]`, `title`, `plan`, `agentMode`, ~30 more fields | ✅ Created |
| `frontend/src/stores/toolStore.ts` | Tools: `lastTool`, `toolTimeline[]`, `panelToolId`, `streamingContentBuffer` | ✅ Created |
| `frontend/src/stores/connectionStore.ts` | SSE: `responsePhase`, `lastEventId`, `lastHeartbeatAt`, `isStale`, `autoRetryCount` | ✅ Created |
| `frontend/src/stores/uiStore.ts` | UI: `isLeftPanelShow`, `isRightPanelOpen`, `theme`, settings dialog, file preview | ✅ Created |
| `frontend/src/stores/index.ts` | Re-exports | ✅ Created |

#### Modified Files

| File | Change | Status |
|------|--------|--------|
| `frontend/package.json` | Add `pinia` dependency | ✅ Done |
| `frontend/src/main.ts` | Add `app.use(createPinia())` | ✅ Done |
| `frontend/src/composables/useAuth.ts` | Thin wrapper → `useAuthStore()` | ⬜ Pending |
| `frontend/src/composables/useLeftPanel.ts` | Wrapper → `useUIStore()` | ⬜ Pending |
| `frontend/src/composables/useResponsePhase.ts` | Delegate → `useConnectionStore()` | ⬜ Pending |
| `frontend/src/composables/useSSEConnection.ts` | Delegate → `useConnectionStore()` | ⬜ Pending |

#### Migration Strategy

Backward-compatible wrappers. Every composable becomes a thin facade returning computed refs from the store. No component changes needed initially.

---

### Phase 8: ChatPage Decomposition (4,498 LOC → 7 modules) [H — 4 days]

**Dependencies**: Phase 7

#### New Files (6)

| File | LOC | Extracted From |
|------|-----|---------------|
| `frontend/src/composables/useSSEEventProcessor.ts` | ~800 | `processEvent()` + all 15+ `handle*Event()` functions |
| `frontend/src/components/chat/ChatHeader.vue` | ~200 | Template lines 19-158 |
| `frontend/src/components/chat/ChatTimeline.vue` | ~400 | Template lines 159-337 |
| `frontend/src/components/chat/ChatComposer.vue` | ~250 | Template lines 370-527 |
| `frontend/src/components/chat/ChatStatusBar.vue` | ~150 | Status indicators |
| `frontend/src/components/chat/ToolPanelController.vue` | ~100 | Replaces 3-layer prop drilling |

**Result**: `ChatPage.vue` reduces from 4,498 → ~300 LOC.

**Eliminates**: `WorkspacePanel.vue` (67 LOC pure passthrough — delete).

**Migration order**: B-1: `useSSEEventProcessor` → B-2: ChatHeader + ChatStatusBar → B-3: ChatComposer → B-4: ChatTimeline → B-5: ToolPanelController

---

### Phase 9: Frontend Performance [M — 3 days]

**Dependencies**: Phase 8

| Optimization | Files | Impact |
|-------------|-------|--------|
| Virtual scrolling | `ChatTimeline.vue` + `@tanstack/vue-virtual` | O(n) → O(1) rendering for 100+ messages |
| Lazy components | `ToolPanelContent`, `TiptapReportEditor`, `MonacoEditor`, `PlotlyChart` → `defineAsyncComponent()` | Reduced initial bundle |
| Markdown memoization | New `frontend/src/utils/markdownRenderer.ts` — LRU cache (200 entries) | Eliminate re-parsing |
| SSE event coalescence | `useSessionStreamController.ts` — batch `tool_stream` events | Reduce rendering churn |

---

## INFRASTRUCTURE PHASES

### Phase 10: Sandbox Architecture Enhancement [M — 4 days]

#### New Files

| File | Purpose |
|------|---------|
| `backend/app/core/sandbox_health_scorer.py` | Composite health score per sandbox (latency, error rate, memory, CPU, age) |
| `sandbox/app/services/cdp_connection_pool.py` | CDP WebSocket connection pool (max 3 per sandbox) |
| `sandbox/app/services/resource_meter.py` | Per-tool resource metering via `/proc` cgroup stats |

#### Modified Files

| File | Change |
|------|--------|
| `backend/app/core/sandbox_pool.py` | Integrate health scorer, add `max_age_seconds` rotation |
| `backend/app/core/config_sandbox.py` | Add `sandbox_pool_max_age_seconds: int = 7200` |
| `sandbox/app/services/cdp_screencast.py` | Use connection pool |
| `sandbox/app/services/shell.py` | Wrap execution with resource meter |

---

### Phase 11: Observability Layer [M — 3 days]

#### New Files

| File | Purpose |
|------|---------|
| `frontend/src/services/logger.ts` | `FrontendLogger` — structured logs, batch-send every 50 entries |
| `backend/app/interfaces/api/telemetry_routes.py` | `POST /api/v1/telemetry/frontend-logs` — ingest into Loki |

#### Modified Files

| File | Change |
|------|--------|
| `frontend/src/composables/useErrorBoundary.ts` | Wire into `FrontendLogger` |
| `backend/requirements.txt` | Add `opentelemetry-*` packages |
| `backend/app/infrastructure/observability/otel_exporter.py` | Auto-instrumentation for `httpx` + `motor` |
| `backend/app/domain/services/agent_task_runner.py` | Add trace spans around flow execution |
| `backend/app/core/prometheus_metrics.py` | Add SSE connection and sandbox resource gauges |

---

### Phase 12: Infrastructure Hardening [M — 3 days]

**Dependencies**: Phase 11

| Change | File | Impact |
|--------|------|--------|
| MongoDB cursor pagination | `session_routes.py`, `mongodb.py` | Eliminates multi-MB event loads |
| Redis cluster-ready wrapper | New `redis_cluster_adapter.py` | Ready for cluster migration |
| Dependency-aware health endpoints | New `health_routes.py` with `/health` + `/health/ready` | Cascading failure visibility |
| Sandbox structured logging | `sandbox/requirements.txt` + `sandbox/app/main.py` | JSON logs for Loki |

---

## Summary Matrix

| Phase | Scope | Complexity | New Files | Modified Files | Status |
|-------|-------|-----------|-----------|----------------|--------|
| 1: Tool Registry | Backend | S (3d) | 2 | 4 | ✅ Complete (permanent) |
| 2: Token Budget | Backend | L (7d) | 3 | 5 | ✅ Complete (flag-gated) |
| 3: God Class Decomp | Backend | XL (14d) | 8 | 4 | ✅ Complete (permanent) |
| 4: DDD Enforcement | Backend | L (7d) | 4 | 3 | ⬜ Blocked on P3 |
| 5: Verification Pipeline | Backend | M (5d) | 3 | 3 | ⬜ Blocked on P3+P1 |
| 6: DSPy Runtime | Backend | XL (14d) | 2 | 4 | ⬜ Blocked on P2+P3+P5 |
| 7: Pinia Migration | Frontend | H (3d) | 6 | 6 | ✅ All 5 stores + index |
| 8: ChatPage Decomp | Frontend | H (4d) | 6 | 2 | ⬜ Blocked on P7 |
| 9: Performance | Frontend | M (3d) | 1 | 4 | ⬜ Blocked on P8 |
| 10: Sandbox Enhancement | Infra | M (4d) | 3 | 4 | ⬜ Not started |
| 11: Observability | Full-Stack | M (3d) | 2 | 5 | ⬜ Not started |
| 12: Infra Hardening | Infra | M (3d) | 2 | 4 | ⬜ Blocked on P11 |
| **TOTAL** | | | **42** | **~48** | |

---

## Feature Flag Strategy

Phases are either permanently enabled (no rollback needed) or gated behind feature flags in `config_features.py`. Gated flags allow the old code path to remain active. Rollout: shadow mode → canary → full enablement.

```python
# Phase 1: PERMANENTLY ENABLED (ToolName enum is backward-compatible str subclass)
# Phase 2
feature_token_budget_manager: bool = False  # Gates budget-aware compression path
# Phase 3: PERMANENTLY ENABLED (decomposed classes fully replace inline code)
# Phase 4
feature_ddd_value_objects: bool = False
# Phase 5
feature_verification_pipeline_v2: bool = False
# Phase 6
feature_dspy_runtime_assertions: bool = False
feature_structured_prompting: bool = False
```

---

## Verification

### Backend
```bash
conda activate pythinker && cd backend
ruff check . && ruff format --check .
pytest tests/ -x                           # Full suite, 3820+ tests must pass
pytest tests/domain/services/agents/ -v    # Agent-specific tests
```

### Frontend
```bash
cd frontend
bun install                                # Picks up pinia
bun run lint && bun run type-check
bun run test:run                           # 63+ tests must pass
```

### End-to-End
1. Enable feature flags incrementally in `.env`
2. `./dev.sh watch` — start full stack
3. Submit a research task → verify planning, execution, summarization
4. Verify token budget logging: `docker logs pythinker-main-backend-1 | grep "token_budget"`
5. Verify Pinia DevTools: open Vue DevTools → Pinia tab → inspect store state
6. Disable all feature flags → verify old behavior unchanged

### Rollback
Set all feature flags to `false` in `.env` and restart. Zero code change needed.

---

## Files Created So Far

### Phase 1 (Tool Registry)
- ✅ `backend/app/domain/models/tool_name.py` — `ToolName(str, Enum)` with 43+ tools, classification sets, phase mappings
- ✅ `backend/app/domain/models/tool_capability.py` — `ToolCapability` Pydantic model, `RiskLevel` enum, pre-built registry

### Phase 2 (Token Budget)
- ✅ `backend/app/domain/services/agents/token_budget_manager.py` — `TokenBudgetManager`, `TokenBudget`, `BudgetPhase`, `PhaseAllocation`
- ✅ `backend/app/domain/services/agents/sliding_window_context.py` — `SlidingWindowContextManager`, `MessagePriority`, `PrioritizedMessage`
- ✅ `backend/app/domain/services/agents/context_compression_pipeline.py` — `ContextCompressionPipeline`, three-stage: summarize → truncate → drop

### Phase 3 (God Class Decomposition)
- ✅ `backend/app/domain/services/agents/step_executor.py` — Adaptive model selection, result validation, multimodal tracking
- ✅ `backend/app/domain/services/agents/response_generator.py` — Content cleaning, quality gates, stream coalescing, delivery integrity
- ✅ `backend/app/domain/services/agents/output_verifier.py` — LettuceDetect + CoVe + Critic verification pipelines
- ✅ `backend/app/domain/services/agents/source_tracker.py` — Citation collection, numbered source lists, URL deduplication
- ✅ `backend/app/domain/services/flows/phase_router.py` — Heuristic step classification, dependency checking
- ✅ `backend/app/domain/services/flows/flow_step_executor.py` — Multi-agent dispatch, skip/update heuristics
- ✅ `backend/app/domain/services/flows/error_recovery_handler.py` — Error classification, recovery state machine
- ✅ `backend/app/domain/services/file_sync_manager.py` — Sandbox ↔ storage sync, workspace sweep, attachment handling

### Phase 7 (Pinia)
- ✅ `frontend/src/stores/authStore.ts` — Auth state, login/logout/refresh actions
- ✅ `frontend/src/stores/sessionStore.ts` — Session state, messages, plan, steps, files
- ✅ `frontend/src/stores/toolStore.ts` — Tool timeline, streaming buffer, active tool calls
- ✅ `frontend/src/stores/connectionStore.ts` — Response phase FSM, SSE connection health, event cursor persistence
- ✅ `frontend/src/stores/uiStore.ts` — Left panel, right panel, settings dialog, file preview
- ✅ `frontend/src/stores/index.ts` — Barrel re-exports for all 5 stores
