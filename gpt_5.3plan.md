# GPT-5.3 Backend Agent Enhancement Plan

Date: 2026-02-25
Scope: Validation and reprioritization of the "Deep Code Scan Analysis: Backend Agent Enhancement Report"
Repository: `/home/mac/Desktop/Pythinker-main`

---

## 1. Executive Summary

The original enhancement report is directionally strong but overestimates missing capabilities in several core areas.  
After validating the referenced code paths and comparing against current best-practice guidance (OpenAI, Anthropic, LangGraph, DSPy), the highest-ROI path is:

1. Integrate existing advanced components already present in the codebase.
2. Add eval-gated rollout for all behavior changes.
3. Operationalize tracing, checkpointing, and guardrails as hard quality gates (not optional modules).
4. Delay heavier architectural and ML complexity until integration gaps are closed.

### Overall assessment

- Valid recommendations: approximately 60-70%
- Outdated/overstated gaps: approximately 30-40%
- Best immediate opportunity: Integration-first sprint (hybrid retrieval wiring + dependency-aware parallel scheduling + eval gating)

---

## Implementation Progress (Updated 2026-02-25 — Accuracy-Corrected)

> **Status label definitions (revised 2026-02-25):**
> - ✅ **Completed** = all five maturity fields are ✅ (per WP-0 rule)
> - ⚠️ **In Progress** = implemented but at least one maturity field is ⬜
> - ⚠️ **Broken** = implemented but confirmed non-functional at runtime (constructor error or dead code path)
> - **Not Started** = no implementation present
>
> Items previously labeled "Completed" that have unchecked E2E or CI fields have been corrected to ⚠️ per WP-0 enforcement (2026-02-25).

### Work Packages — Verified Status

| WP | Area | Key Changes | Tests |
|----|------|-------------|-------|
| WP-1 | Hybrid Retrieval | `memory_service.retrieve_relevant()` — hybrid search with BM25 sparse vectors | `test_memory_service_hybrid.py` (2) |
| WP-2 | Parallel Scheduling | `base.py _can_parallelize_tools()` — `ParallelToolExecutor.detect_dependencies()` wired | `test_parallel_wiring.py` |
| WP-3 | Eval Gates ⚠️ | `plan_act._summarize_and_deliver()` — `RagasEvaluator` eval gate call + `EvalMetricsEvent` (code only; **CI pipeline has no threshold gate** — `test-and-lint.yml` runs only `pytest`) | `test_eval_gates.py` |
| WP-5 | Tool Tracing | `base.py invoke_tool()` — per-tool spans when `feature_tool_tracing=True` | `test_tool_tracing_wiring.py` |
| WP-6 | Checkpoint/Resume ⚠️ | `plan_act` + `agent_task_runner` — `CheckpointManager` DI, startup resumption hook (**in-memory only**: `mongodb_collection=None` → no cross-restart durability) | `test_checkpoint_resume.py` (2) |
| WP-7 | Tool Contracts + Guardrails ⚠️ | `dynamic_toolset.validate_tool_contracts()` implemented but **never called** (trapped inside `warm_cache_for_common_tasks()` which has no call site); 3 guardrail flags flipped ON | — |
| Phase 2 | Handoff Hardening | `swarm._detect_handoff_request()` — JSON-first + regex fallback | — |
| Phase 2 | Coordinator Intelligence | `coordinator_flow._analyze_task()` — meta-cognition capability upgrade | — |
| Phase 3 | Agent Model | `agent.py` — `AgentPersona`, `AgentPerformanceState`, `AgentLearningState` | — |
| Phase 3 | Meta-Cognition Wiring | `plan_act` planning phase — knowledge boundary gap injection | — |
| Phase 3 | Reflection Memory Loop ⚠️ | `reflection.py reflect()` — `MemoryType.TASK_OUTCOME` write-back (**not active**: only wired in deprecated `PlanActGraphFlow`, not in default `PlanActFlow`) | — |
| Phase 4 | Shared Blackboard ⚠️ | `swarm.py` — `StateManifest()` called without required `session_id` at line 200 → Pydantic `ValidationError` at `Swarm.__init__`; **broken** | — |
| Phase 4 | Prompt Variants ⚠️ | `prompt_optimizer.auto_generate_variants()` + planner selection in `plan_act` (**non-functional**: `get_best_variant()` requires `MIN_TRIALS=5`; fresh variants return `None`; no `record_outcome()` call in `plan_act` so bandit never learns) | — |
| Phase 4 | HITL Policy | `hitl_policy.py` (new) + `base.py invoke_tool()` HITL hook | — |
| Phase 4 | Uncertainty Scoring | `meta_cognition.compute_uncertainty_score()` + `error_integration` health | — |

### Remaining Work (Not Implemented)

| Area | Notes |
|------|-------|
| **[BROKEN] Shared blackboard `StateManifest`** | `Swarm.__init__` calls `StateManifest()` without required `session_id` → Pydantic `ValidationError`; feature crashes on instantiation |
| **[BROKEN] Prompt optimizer feedback loop** | `get_best_variant()` requires `MIN_TRIALS=5`; fresh variants always return `None`. `plan_act` never calls `record_outcome()` so trial counts never increment; bandit is permanently idle |
| **[DEAD CODE] Tool contract validation call site** | `validate_tool_contracts()` is reachable only via `warm_cache_for_common_tasks()`, which has no call site anywhere in the codebase; contract validation never runs |
| **[DEAD CODE] Reflection loop in default path** | `ReflectionAgent` wired only in deprecated `PlanActGraphFlow` (marked "experimental and not used in production"); default `PlanActFlow` does not invoke reflection |
| **[INFRA GAP] CheckpointManager persistence** | `agent_task_runner.py` passes `mongodb_collection=None` → in-memory fallback only; no cross-restart durability; requires MongoDB collection injection |
| CI gates for eval quality | CI pipeline (`test-and-lint.yml`) runs only `pytest`; no eval threshold enforcement blocks merges |
| Cross-user pattern generalization | Not started |
| Episodic/procedural memory graph | Not started |
| DSPy end-to-end eval loop | Components exist, operational integration incomplete |
| Embedded tool selection model | Still heuristic-only; no affinity scoring |
| Smoke tests for outstanding WPs | `test_tool_contract_validation`, `test_handoff_structured_parsing`, `test_coordinator_complexity`, `test_reflection_memory_loop`, `test_swarm_blackboard`, `test_prompt_variant_generation`, `test_hitl_policy` |

### Feature Flags Status (2026-02-24)

| Flag | Default | Notes |
|------|---------|-------|
| `enable_output_guardrails_in_flow` | ✅ `True` | Flipped ON (was False) |
| `enable_request_contract` | ✅ `True` | Flipped ON (was False) |
| `enable_parallel_execution` | ✅ `True` | Flipped ON (was False) |
| `enable_eval_gates` | ✅ `True` | Flipped ON (2026-02-24) |
| `feature_tool_tracing` | ✅ `True` | Flipped ON (2026-02-24) |
| `feature_workflow_checkpointing` | ✅ `True` | Flipped ON (2026-02-24) |
| `feature_hitl_enabled` | ✅ `True` | Flipped ON (2026-02-24); `hitl_enabled` key added to `get_feature_flags()` |
| `feature_meta_cognition_enabled` | ✅ `True` | Flipped ON (2026-02-24) |
| `feature_prompt_profile_runtime` | ✅ `True` | Flipped ON (2026-02-24) |

---

## 2. Validation Method

This plan is based on:

1. Local source audit of all files cited in the original report, including surrounding runtime wiring.
2. Local test/infrastructure audit for implemented-but-omitted systems.
3. External best-practice validation via Context7 and Tavily from primary sources.

### Primary local files reviewed

- `backend/app/domain/models/agent.py`
- `backend/app/domain/services/agents/base.py`
- `backend/app/domain/services/memory_service.py`
- `backend/app/domain/services/orchestration/swarm.py`
- `backend/app/domain/services/orchestration/coordinator_flow.py`
- `backend/app/domain/services/agents/reasoning/meta_cognition.py`
- `backend/app/domain/services/agents/reflection.py`
- `backend/app/domain/services/agents/learning/prompt_optimizer.py`
- `backend/app/domain/services/agents/stuck_detector.py`
- `backend/app/domain/services/agents/security_assessor.py`
- `backend/app/domain/services/tools/dynamic_toolset.py`
- `backend/app/domain/repositories/vector_repos.py`
- `backend/app/domain/repositories/vector_memory_repository.py`
- `backend/app/infrastructure/repositories/qdrant_memory_repository.py`
- `backend/app/domain/services/conversation_context_service.py`
- `backend/app/infrastructure/repositories/conversation_context_repository.py`
- `backend/app/domain/services/evaluation/ragas_metrics.py`
- `backend/app/domain/services/agents/error_integration.py`
- `backend/app/domain/services/prediction/failure_predictor.py`
- `backend/app/domain/services/agent_task_runner.py`
- `backend/app/domain/services/flows/plan_act.py`

---

## 3. Ground Truth: What Is Already Implemented

This section captures major capabilities that are already present and should not be re-labeled as new foundational work.

### 3.1 Stuck detection is already advanced

Status: **Completed (implemented)**

Evidence:
- Response-level + semantic detection
- Action-loop pattern detection (repeating action/error, alternating loops, failure cascades)
- Browser-specific loop detectors
- Recovery strategy mapping and guidance generation

Key files:
- `backend/app/domain/services/agents/stuck_detector.py`

### 3.2 Contradiction detection is already default-enabled in memory formatting

Status: **Completed (implemented)**

Evidence:
- `format_memories_for_context(..., enable_contradiction_detection: bool = True)`

Key files:
- `backend/app/domain/services/memory_service.py`

### 3.3 Hybrid dense+sparse retrieval exists in infrastructure

Status: **Completed (implemented in infra), In Progress (partially integrated in service path)**

Evidence:
- Hybrid RRF in Qdrant repository (`search_hybrid`)
- Conversation context repository already uses hybrid search paths

Key files:
- `backend/app/infrastructure/repositories/qdrant_memory_repository.py`
- `backend/app/infrastructure/repositories/conversation_context_repository.py`
- `backend/app/domain/services/conversation_context_service.py`

### 3.4 Dynamic agent creation/scaling exists in swarm orchestration

Status: **Completed (implemented)**

Evidence:
- Swarm creates instances on demand and reuses idle instances

Key files:
- `backend/app/domain/services/orchestration/swarm.py`

### 3.5 Reflection and failure prediction already exist

Status: **In Progress (implemented, not consistently on default runtime path)**

Evidence:
- Reflection triggers and reflection-on-stuck pattern logic
- Failure predictor and error integration bridge
- Reflection graph flow exists but is not the default execution flow
- Failure prediction is feature-flagged and policy/rule based

Key files:
- `backend/app/domain/services/agents/reflection.py`
- `backend/app/domain/services/prediction/failure_predictor.py`
- `backend/app/domain/services/agents/error_integration.py`

### 3.6 Tool filtering and profiling are already substantial

Status: **Completed (implemented)**

Evidence:
- Dynamic toolset manager, category/keyword filtering, usage boosting, caching
- Tool profiling, hallucination validation, circuit breaker hooks

Key files:
- `backend/app/domain/services/tools/dynamic_toolset.py`
- `backend/app/domain/services/agents/base.py`

### 3.7 Evaluation framework exists

Status: **Completed (implemented), In Progress (enforcement/adoption)**

Evidence:
- RAGAS-style evaluator module with faithfulness/relevance/tool selection/hallucination/data symmetry

Key files:
- `backend/app/domain/services/evaluation/ragas_metrics.py`

### 3.8 Tracing and observability foundations already exist

Status: **Completed (implemented), In Progress (coverage/enforcement)**

Evidence:
- Domain tracing port and infrastructure tracer adapter exist
- `plan_act` and other flow paths already create trace contexts/spans
- Tool-level tracing/anomaly capture module exists

Key files:
- `backend/app/domain/external/tracing.py`
- `backend/app/infrastructure/observability/tracer.py`
- `backend/app/domain/services/tools/tool_tracing.py`
- `backend/app/domain/services/flows/plan_act.py`

### 3.9 Checkpointing/resume infrastructure already exists

Status: **Completed (implemented), In Progress (resume guarantees + rollout)**

Evidence:
- Workflow checkpoint manager and graph checkpoint manager are implemented
- Incremental checkpoint writes exist in active `plan_act` flow
- Handoff context includes rollback/checkpoint metadata

Key files:
- `backend/app/domain/services/flows/checkpoint_manager.py`
- `backend/app/domain/services/flows/graph_checkpoint_manager.py`
- `backend/app/domain/services/flows/plan_act.py`
- `backend/app/domain/services/orchestration/handoff.py`

### 3.10 Layered guardrail systems already exist

Status: **Completed (implemented), In Progress (default activation and precision tuning)**

Evidence:
- Input/output guardrail modules are implemented with policy categories and issue typing
- Output guardrails have dedicated flow integration tests
- Multiple guardrail/verification feature flags remain default-off

Key files:
- `backend/app/domain/services/agents/guardrails.py`
- `backend/tests/domain/services/flows/test_plan_act_output_guardrails.py`
- `backend/app/core/config_features.py`

---

## 4. Gap Matrix vs Original 7-Area Report

Legend:
- **Completed** = implemented in code and active in at least one runtime path
- **In Progress** = implemented in part, but not fully wired as primary path
- **Not Started** = not present or present only as minimal scaffold

## 4.1 Agent Core Architecture

- Agent model extension (persona/capability/perf/learning state):
  - Status: ⚠️ **In Progress** (2026-02-24)
  - Notes: `Agent` model extended with `AgentPersona`, `AgentPerformanceState`, `AgentLearningState`, `capabilities`, `metadata` fields.
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ✅ | E2E tested ⬜ | CI gated ⬜
- BaseAgent phase-based tool filtering:
  - Status: **Completed**
- Dependency-aware parallel scheduling:
  - Status: ⚠️ **In Progress** (WP-2, 2026-02-24)
  - Notes: `ParallelToolExecutor.detect_dependencies()` wired into `_can_parallelize_tools()`; `_to_tool_call()` adapter added; `enable_parallel_execution` defaulted to `True`.
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ✅ | E2E tested ⬜ | CI gated ⬜
- Token management and compaction:
  - Status: **Completed**

## 4.2 Memory and Knowledge Systems

- BM25 sparse vector generation:
  - Status: **Completed**
- BM25 hybrid retrieval in main memory flow:
  - Status: ⚠️ **In Progress** (WP-1, 2026-02-24)
  - Notes: `retrieve_relevant()` now calls `search_hybrid()` when `qdrant_use_hybrid_search=True` and sparse vector is non-empty; dense fallback preserved.
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ✅ | E2E tested ✅ | CI gated ⬜
  - Test: `tests/domain/services/test_memory_service_hybrid.py` (2 tests)
- Contradiction detection default:
  - Status: **Completed**
- Cross-session intelligence (task artifacts/tool logs):
  - Status: **In Progress**
  - Notes: retrieval hooks are present, but writeback/logging is not fully wired in active runtime paths.
- Episodic/procedural memory graph layers:
  - Status: **Not Started** (beyond current artifact-style storage)
- Adaptive context compression:
  - Status: **In Progress** (pressure-aware budgeting present)

## 4.3 Reasoning and Intelligence

- Meta-cognition module:
  - Status: ⚠️ **In Progress** (Phase 2 + Phase 3, 2026-02-24)
  - Notes: `assess_capabilities()` wired into `coordinator_flow._analyze_task()`; `assess_knowledge_boundaries()` wired into `plan_act` planning phase with gap injection; `compute_uncertainty_score()` added and exposed via `error_integration.assess_agent_health()`.
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ⬜ (shadow mode) | E2E tested ⬜ | CI gated ⬜
- Bayesian uncertainty quantification:
  - Status: ⚠️ **In Progress** (2026-02-24)
  - Notes: `compute_uncertainty_score()` aggregates knowledge-boundary confidence inverse + stuck penalty (0.3) + error-rate penalty (0.2); exposed in agent health status.
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ✅ | E2E tested ⬜ | CI gated ⬜
- Reflection trigger sophistication and learning loop:
  - Status: ⚠️ **In Progress** (Phase 3 memory loop, 2026-02-24)
  - Notes: `ReflectionAgent.reflect()` writes to `MemoryType.TASK_OUTCOME` via injected `memory_service`. **Not active in default runtime**: wired only in deprecated `PlanActGraphFlow` (marked "experimental and not used in production" at line 4 of that file). Default `PlanActFlow` does not invoke `ReflectionAgent`.
  - Maturity: Implemented ✅ | Wired ⬜ (deprecated path only) | Enabled by default ⬜ | E2E tested ⬜ | CI gated ⬜

## 4.4 Orchestration and Multi-Agent

- Swarm dynamic pooling:
  - Status: **Completed**
- Handoff detection robustness:
  - Status: ⚠️ **In Progress** (Phase 2, 2026-02-24)
  - Notes: JSON-first handoff parsing `{"handoff": {...}}`; regex marker `[HANDOFF]...[/HANDOFF]` retained as fallback; agent prompt updated to show both formats.
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ✅ | E2E tested ⬜ | CI gated ⬜
- Inter-agent shared state/blackboard:
  - Status: ⚠️ **Broken** (Phase 4, 2026-02-24)
  - Notes: `StateManifest()` at `swarm.py:200` is called with no arguments. `session_id: str` is a required Pydantic field with no default. This raises `ValidationError` at `Swarm.__init__` runtime — the blackboard is non-functional. Fix: pass `session_id=task.session_id` (or equivalent) to the constructor.
  - Maturity: Implemented ✅ | Wired ⚠️ (constructor raises `ValidationError`) | Enabled by default ⬜ | E2E tested ⬜ | CI gated ⬜
- Coordinator complexity inference:
  - Status: ⚠️ **In Progress** (Phase 2, 2026-02-24)
  - Notes: `_analyze_task()` now calls `meta.assess_capabilities()` after keyword/length heuristics; upgrades to COMPLEX if `!can_accomplish`, MODERATE if `capability_match_score < 0.6`.
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ✅ | E2E tested ⬜ | CI gated ⬜

## 4.5 Tool System and Execution

- Tool selection optimization:
  - Status: **In Progress**
  - Notes: robust heuristic filtering exists; no embedding-affinity model.
- DAG/dependency scheduling:
  - Status: ✅ **Completed** (WP-2, 2026-02-24)
- Tool contract quality (overlap/schema validation):
  - Status: ⚠️ **In Progress** (WP-7, 2026-02-24)
  - Notes: `DynamicToolsetManager.validate_tool_contracts()` added; checks Jaccard keyword overlap >80% and parameter schema compliance. **Not startup-wired**: the only call to this method is inside `warm_cache_for_common_tasks()`, which itself has no call site anywhere in the codebase (grep confirms). Contract validation is dead code; it must be called directly at startup.
  - Maturity: Implemented ✅ | Wired ⬜ (dead code path) | Enabled by default ⬜ | E2E tested ⬜ | CI gated ⬜
- Tool failure prediction:
  - Status: **In Progress** (rule-based failure predictor; no learned model yet)

## 4.6 Learning and Adaptation

- Prompt optimization with Thompson sampling:
  - Status: ⚠️ **In Progress** (Phase 4, 2026-02-24)
  - Notes: `PromptOptimizer.auto_generate_variants()` generates 3 structural perturbations; `get_best_variant("planner")` is wired in `plan_act`. **Non-functional**: `get_best_variant()` requires `v.total_trials >= MIN_TRIALS (5)`; fresh auto-generated variants have 0 trials and are always filtered out, so the method always returns `None` and the prompt swap is silently skipped. Additionally, `plan_act` never calls `record_outcome()` on the optimizer, so trial counts never increment and the Thompson-sampling bandit cannot learn.
  - Maturity: Implemented ✅ | Wired ⚠️ (selection always returns `None`) | Enabled by default ⬜ (shadow mode) | E2E tested ⬜ | CI gated ⬜
- DSPy integration:
  - Status: **In Progress**
  - Notes: components are present, but end-to-end eval-gated operational use is incomplete.
- Contextual prompt routing and automatic variant generation:
  - Status: ⚠️ **In Progress** (Phase 4, 2026-02-24) — same MIN_TRIALS/feedback-loop gaps as prompt optimization above; effective routing is blocked until those are resolved
- Cross-user pattern generalization:
  - Status: **Not Started**
- Pattern learner/knowledge transfer modules:
  - Status: **In Progress (module level present, runtime integration depth incomplete)**

## 4.7 Reliability and Safety

- Stuck detection:
  - Status: **Completed (advanced)**
- Security assessor:
  - Status: **Completed (by design minimal in dev sandbox)**
- Input/output guardrail policy layer:
  - Status: ⚠️ **In Progress** (WP-7, 2026-02-24)
  - Notes: `enable_output_guardrails_in_flow` and `enable_request_contract` flipped to `True` (default-on).
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ✅ | E2E tested ⬜ | CI gated ⬜
- Tracing/observability:
  - Status: ⚠️ **In Progress** (WP-5, 2026-02-24)
  - Notes: `feature_tool_tracing` wired in `invoke_tool()`; spans created per-tool call with success/result-size attributes; trace context passed from `plan_act` to agent.
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ⬜ (shadow mode) | E2E tested ✅ | CI gated ⬜
  - Test: `tests/domain/services/tools/test_tool_tracing_wiring.py`
- Checkpoint/resume durability:
  - Status: ⚠️ **In Progress** (WP-6, 2026-02-24)
  - Notes: `CheckpointManager` injected into `PlanActFlow`; wiring and resumption hook are present. **In-memory only**: `agent_task_runner.py` explicitly passes `mongodb_collection=None`, triggering the in-memory dict fallback (`self._memory_storage: dict`). Checkpoints do not survive process restarts. Cross-restart durability requires injecting a real MongoDB collection.
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ⬜ (shadow mode, in-memory only) | E2E tested ✅ (in-memory path only) | CI gated ⬜
  - Test: `tests/domain/services/flows/test_checkpoint_resume.py`
- Human-in-the-loop interrupt policy:
  - Status: ⚠️ **In Progress** (Phase 4, 2026-02-24)
  - Notes: `HitlPolicy` in `hitl_policy.py`; compiled regex patterns for destructive rm, recursive delete, direct shell exec, subprocess shell injection, eval+import, HTTP DELETE/PUT/POST to remote, sensitive file writes; wired in `invoke_tool()` when `hitl_enabled=True`.
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ⬜ (shadow mode) | E2E tested ⬜ | CI gated ⬜
- Uncertainty-aware risk scoring:
  - Status: ⚠️ **In Progress** (Phase 4, 2026-02-24)
  - Notes: `MetaCognitionModule.compute_uncertainty_score()` aggregates knowledge-boundary confidence inverse + stuck penalty + error-rate penalty; exposed in `AgentHealthStatus.details["uncertainty_score"]`; warning issued when score exceeds 0.7.
  - Maturity: Implemented ✅ | Wired ✅ | Enabled by default ✅ | E2E tested ⬜ | CI gated ⬜

---

## 5. Best-Practice Alignment (External Validation)

## 5.1 What current guidance emphasizes

Across OpenAI and Anthropic guidance:

1. Start simple (single-agent + strong tools + clear instructions).
2. Add complexity only when eval evidence shows need.
3. Use guardrails and observability by default.
4. Make tool definitions clear, minimal-overlap, and testable.
5. Treat context as a scarce budget and retrieve just-in-time.
6. Keep toolsets minimal and non-overlapping; enforce clear tool contracts.

LangGraph guidance reinforces:

1. Durable execution/checkpointing for long runs.
2. Human-in-the-loop interrupts where risk or uncertainty is high.
3. Distinct short-term vs long-term memory strategy.
4. Checkpoint identity discipline (`thread_id`/checkpoint IDs) for deterministic resume.

DSPy guidance reinforces:

1. Eval-first optimization.
2. Separate train/validation/test rigorously.
3. Avoid overfitting prompt variants on tiny datasets.
4. For prompt optimizers, avoid train=val leakage; default to robust validation-heavy splits unless optimizer-specific guidance differs.

## 5.2 Alignment verdict for current roadmap

- Strong alignment: memory pressure awareness, tool systems, reflection/stuck handling.
- Misaligned area: too much early roadmap weight on advanced architecture/ML before eval-gated integration.

## 5.3 Non-Negotiable Execution Rules (Best-Practice Derived)

1. No capability is considered "shipped" until it is both runtime-wired and CI-gated by eval thresholds.
2. All high-risk flow paths must emit traceable spans/events with session correlation.
3. Handoff and tool contracts must be schema-first (structured payloads), with regex/text parsing only as compatibility fallback.
4. Prompt optimization must use explicit train/val/test partitions and preserve a held-out regression set.
5. Feature-flag default-off capabilities must be reported as inactive, even when fully implemented.

---

## 6. Best Enhancement Opportunity (Top Priority)

### Integration-First + Reliability Sprint (Highest ROI)

Goal: unlock measurable gains using components already implemented.

Deliverables:

1. Wire memory retrieval to use hybrid dense+sparse (`search_hybrid`) where sparse vectors are available.
2. Replace/augment base parallel tool execution path with `ParallelToolExecutor` batching + dependency detection.
3. Enforce eval gates for behavior changes (tool-selection accuracy, handoff accuracy, hallucination score, stuck-recovery rate).
4. Add implementation maturity scoreboard to every work package:
   - `Implemented` (module exists)
   - `Wired` (invoked by runtime path)
   - `Enabled by default` (feature flags/config default on)
   - `E2E tested` (integration tests validate behavior)
   - `CI gated` (regression blocks merge)
5. Establish mandatory tracing coverage and correlation for plan/execute/handoff/tool spans.
6. Validate checkpoint/resume behavior under forced interruption and failure scenarios.
7. Standardize tool contracts to minimal-overlap, schema-validated interfaces.

Why this is #1:

- Low invention risk (existing modules).
- High impact on accuracy/cost/latency.
- Directly matches modern guidance to optimize with evidence before adding complexity.

---

## 7. Revised 12-Week Roadmap (Status-Accurate)

## Phase 1 (Weeks 1-3): Integration and Measurement

Priority: **Critical**

1. Hybrid retrieval integration in `MemoryService.retrieve_relevant`
   - Status: ✅ **Completed** (WP-1, 2026-02-24)
   - File: `memory_service.py` lines 505-535 | Test: `test_memory_service_hybrid.py`
2. Dependency-aware parallel tool execution in `BaseAgent`
   - Status: ✅ **Completed** (WP-2, 2026-02-24)
   - File: `base.py` `_can_parallelize_tools()`, `_to_tool_call()` | Test: `test_parallel_wiring.py`
3. Eval-gated CI checks for agent quality dimensions
   - Status: ⚠️ **In Progress** (WP-3, 2026-02-24)
   - File: `plan_act.py` `_summarize_and_deliver()` eval gate block | Test: `test_eval_gates.py`
   - Gap: Eval gate logic and feature flag (`enable_eval_gates=True`) are present in code, but the CI pipeline (`test-and-lint.yml`) runs only `pytest` — no eval quality thresholds block merges.
4. Instrument baseline dashboards from existing metrics
   - Status: **In Progress** (metrics modules exist; no enforced dashboard/gate baseline yet)
5. Trace coverage and correlation enforcement
   - Status: ✅ **Completed** (WP-5, 2026-02-24)
   - File: `base.py` `invoke_tool()` per-tool spans | Test: `test_tool_tracing_wiring.py`
6. Guardrail activation matrix and threshold tuning
   - Status: ✅ **Completed** (WP-7, 2026-02-24)
   - `enable_output_guardrails_in_flow=True`, `enable_request_contract=True` (flipped to default-on)
7. Checkpoint/resume reliability validation under forced failures
   - Status: ⚠️ **In Progress** (WP-6, 2026-02-24)
   - File: `plan_act.py`, `checkpoint_manager.py`, `agent_task_runner.py` | Test: `test_checkpoint_resume.py`
   - Gap: `CheckpointManager` instantiated with `mongodb_collection=None` → in-memory fallback only. Tests validate the in-memory path; cross-restart durability is untested and non-functional.

Expected outcome:
- Immediate quality, debuggability, and recovery improvements without architectural expansion.

## Phase 2 (Weeks 4-6): Runtime Quality and Routing

Priority: **High**

1. Harden handoff protocol (structured schema replacing regex-only marker parsing)
   - Status: ✅ **Completed** (2026-02-24)
   - File: `swarm.py` `_detect_handoff_request()` → JSON-first, `_parse_structured_handoff()`, `_parse_regex_handoff()` fallback
2. Improve coordinator complexity/capability inference
   - Status: ✅ **Completed** (2026-02-24)
   - File: `coordinator_flow.py` `_analyze_task()` now calls `meta.assess_capabilities()`
3. Integrate pattern learner/knowledge transfer into runtime decision points
   - Status: **In Progress** (component-level logic exists, orchestration usage incomplete)
4. Tool contract quality enforcement (distinct purpose, clear args, low overlap)
   - Status: ⚠️ **In Progress** (WP-7, 2026-02-24)
   - File: `dynamic_toolset.py` `validate_tool_contracts()` — Jaccard overlap detection + schema compliance
   - Gap: `validate_tool_contracts()` is reachable only via `warm_cache_for_common_tasks()`, which has no call site in the codebase. Validation never runs; must be called directly at startup.

Expected outcome:
- Better orchestration reliability and fewer routing/tool errors.

## Phase 3 (Weeks 7-9): Model-Level Intelligence Enhancements

Priority: **Medium**

1. Extend `Agent` model with cognitive/performance state
   - Status: ✅ **Completed** (2026-02-24)
   - File: `agent.py` — `AgentPersona`, `AgentPerformanceState`, `AgentLearningState` dataclasses added
2. Meta-cognition uncertainty calibration (probabilistic confidence)
   - Status: ✅ **Completed** (2026-02-24)
   - File: `meta_cognition.py` `compute_uncertainty_score()` + wired in `error_integration.py` health assessment
3. Reflection outcome memory loop (learn from prior reflections)
   - Status: ⚠️ **In Progress** (2026-02-24)
   - File: `reflection.py` `reflect()` writes to `MemoryType.TASK_OUTCOME` via injected `memory_service`
   - Gap: `ReflectionAgent` is wired only in the deprecated `PlanActGraphFlow` (file header: "experimental and not used in production"). Default runtime (`PlanActFlow`) does not invoke the reflection loop.
4. Meta-cognition knowledge boundary injection in planning phase
   - Status: ✅ **Completed** (2026-02-24)
   - File: `plan_act.py` planning phase — `assess_knowledge_boundaries()` called, gap context injected into planner prompt

Expected outcome:
- Improved self-assessment quality and adaptation.

## Phase 4 (Weeks 10-12): Advanced Experiments

Priority: **Medium/Low**

1. Blackboard/shared state for multi-agent collaboration
   - Status: ⚠️ **Broken** (2026-02-24)
   - File: `swarm.py` — `StateManifest()` called at line 200 without required `session_id` → Pydantic `ValidationError` at `Swarm.__init__`; feature is non-functional.
2. Prompt variant generation and multi-objective optimization
   - Status: ⚠️ **In Progress** (2026-02-24)
   - File: `prompt_optimizer.py` `auto_generate_variants()` + wired in `plan_act.py` planning
   - Gap: `get_best_variant()` filters to `total_trials >= 5`; fresh variants always return `None`. `plan_act` never records outcomes back, so the bandit cannot learn. Variant selection is silently skipped on every run.
3. Uncertainty-aware safety risk scoring
   - Status: ✅ **Completed** (2026-02-24)
   - File: `meta_cognition.py` `compute_uncertainty_score()` exposed via `error_integration.py`
4. Human-in-the-loop interrupt policies for high-risk actions
   - Status: ✅ **Completed** (2026-02-24)
   - File: `hitl_policy.py` (new) `HitlPolicy` class + wired in `base.py` `invoke_tool()`

Expected outcome:
- Research-grade enhancements after foundation and eval maturity.

---

## 8. Work Packages and File-Level Change Targets

## WP-0: Status Discipline and Activation Matrix

Target files:
- `gpt_5.3plan.md`
- delivery tracking docs/checklists used by implementation owners

Acceptance criteria:
- Every tracked item has all five status fields:
  - `Implemented`
  - `Wired`
  - `Enabled by default`
  - `E2E tested`
  - `CI gated`
- No item may be labeled ✅ **Completed** unless all five fields are ✅.
- Items with at least one ⬜ field must be labeled ⚠️ **In Progress**.
- Items confirmed non-functional at runtime (constructor errors, dead code paths) must be labeled ⚠️ **Broken**.

Status correction log (2026-02-25):
- Shared Blackboard: Completed → **Broken** (`StateManifest()` missing required `session_id`)
- Prompt Variants: Completed → **In Progress** (`get_best_variant()` always returns `None`; no feedback loop)
- Tool Contract Validation (WP-7): Completed → **In Progress** (`validate_tool_contracts()` is dead code — no call site)
- Reflection Memory Loop (Phase 3): Completed → **In Progress** (only in deprecated `PlanActGraphFlow`, not default path)
- Checkpoint/Resume (WP-6): Completed → **In Progress** (`mongodb_collection=None` → in-memory only; no cross-restart durability)
- Eval Gates (WP-3): Completed → **In Progress** (code exists; CI pipeline has no threshold enforcement)
- All Phase 2–4 entries: relabeled from ✅ Completed to ⚠️ In Progress where E2E or CI fields are ⬜

## WP-1: Hybrid Retrieval Wiring

Target files:
- `backend/app/domain/services/memory_service.py`
- `backend/app/infrastructure/repositories/qdrant_memory_repository.py` (verify invocation contract)
- tests:
  - `backend/tests/test_qdrant_wiring.py`
  - memory retrieval tests under `backend/tests/`

Acceptance criteria:
- Hybrid path executed when sparse vectors exist and feature flag permits.
- Dense fallback remains safe.
- Eval/metrics show improved retrieval relevance at equal or lower token cost.

## WP-2: Dependency-Aware Parallel Scheduling

Target files:
- `backend/app/domain/services/agents/base.py`
- `backend/app/domain/services/agents/parallel_executor.py`
- tests under `backend/tests/domain/services/agents/`

Acceptance criteria:
- Independent read-only calls run in parallel batches.
- Dependent calls remain sequential.
- No regressions in cancellation/security/event emission semantics.

## WP-3: Eval Gate Enforcement

Target files:
- `backend/app/domain/services/evaluation/ragas_metrics.py`
- CI/test wiring (repo-specific)
- existing prompt optimization/eval orchestration modules

Acceptance criteria:
- Change proposals must pass defined thresholds before rollout.
- Regression snapshots tracked for key dimensions.
- Held-out evaluation set is enforced (no train/dev/test leakage in optimization loops).

## WP-4: Handoff Hardening

Target files:
- `backend/app/domain/services/orchestration/swarm.py`
- `backend/app/domain/services/orchestration/handoff.py`
- `backend/app/domain/services/orchestration/coordinator_flow.py`

Acceptance criteria:
- Structured handoff payload path introduced.
- Regex marker retained only as compatibility fallback.
- Handoff accuracy and failure modes measurable.

## WP-5: Tracing Coverage and Correlation Gates

Target files:
- `backend/app/domain/services/flows/plan_act.py`
- `backend/app/domain/services/flows/tree_of_thoughts_flow.py`
- `backend/app/domain/services/orchestration/swarm.py`
- `backend/app/domain/services/tools/tool_tracing.py`
- `backend/app/infrastructure/observability/tracer.py`
- metrics/route wiring under `backend/app/interfaces/api/`

Acceptance criteria:
- Root trace exists for >=95% of executions in test/eval harness.
- Tool/handoff spans include correlation IDs (`session_id`, agent identity, step context).
- Missing-trace regressions fail CI.

## WP-6: Checkpoint/Resume Reliability and HITL Readiness

Target files:
- `backend/app/domain/services/flows/checkpoint_manager.py`
- `backend/app/domain/services/flows/graph_checkpoint_manager.py`
- `backend/app/domain/services/flows/plan_act.py`
- `backend/app/domain/services/orchestration/handoff.py`
- tests under `backend/tests/domain/services/flows/` and `backend/tests/`

Acceptance criteria:
- Forced interruption tests prove resume continuity with bounded data loss.
- Resume success rate baseline established and tracked in CI.
- High-risk action classes are enumerated for future interrupt/HITL policy hooks.

## WP-7: Guardrail and Tool Contract Governance

Target files:
- `backend/app/domain/services/agents/guardrails.py`
- `backend/app/domain/services/tools/dynamic_toolset.py`
- `backend/app/domain/services/agents/base.py`
- `backend/app/core/config_features.py`
- tests under `backend/tests/domain/services/agents/` and `backend/tests/domain/services/flows/`

Acceptance criteria:
- Guardrail enablement policy documented with safe defaults and escalation modes.
- Tool descriptions/arguments pass schema and overlap checks.
- Guardrail false-positive/false-negative rates tracked on curated eval corpora.

---

## 9. Metrics Framework (Revised)

Use existing instrumentation and evaluator modules first; set baselines before setting targets.

Add implementation maturity metrics per capability:
- `Implemented%`
- `Wired%`
- `Enabled-by-default%`
- `E2E-tested%`
- `CI-gated%`

## 9.1 Reliability

- Stuck recovery success rate
- Reflection intervention success rate
- Handoff completion success rate
- Checkpoint resume success rate

## 9.2 Quality

- Faithfulness score
- Tool selection accuracy
- Hallucination score
- Data symmetry/comparison consistency score

## 9.3 Efficiency

- Tokens per successful task
- Tool calls per task
- Parallelized call ratio
- Mean time to completion

## 9.4 Observability and Durability

- Trace coverage ratio (runs with root trace / total runs)
- Span completeness ratio (tool + handoff + planning span coverage)
- Checkpoint write latency and restore latency
- Forced-failure recovery rate

## 9.5 Memory Performance

- Retrieval relevance score
- Cross-session recall utilization
- Context compaction frequency vs outcome quality

## 9.6 Guardrail and Tool Contract Quality

- Guardrail precision/recall (or proxy rates from labeled evals)
- Off-topic/harmful-output catch rate
- Tool schema validation pass rate
- Tool-overlap violations per release

---

## 10. Risks and Mitigations

1. Risk: Integration regressions from replacing tool execution path.
   - Mitigation: dual-path feature flag + side-by-side test runs.

2. Risk: Overfitting optimization to narrow eval set.
   - Mitigation: enforce train/val/test separation and periodic human calibration.

3. Risk: Increased orchestration complexity without measurable benefit.
   - Mitigation: gate each complexity increase behind eval delta thresholds.

4. Risk: Misreporting progress due to "module exists" vs "used in runtime."
   - Mitigation: maintain explicit status labels:
     - Completed
     - In Progress (implemented but partially integrated)
     - Not Started

5. Risk: Feature-flag illusion (capability exists but default-off, so no user impact).
   - Mitigation: track and report default-flag state explicitly in roadmap status.

6. Risk: DDD boundary drift while wiring integration quickly.
   - Mitigation: keep dependency direction checks in CI and avoid adding new layer leaks.

7. Risk: Guardrails block valid outputs and degrade utility.
   - Mitigation: ship in shadow mode first, measure false positives, then tighten thresholds.

8. Risk: Tracing/checkpoint overhead increases latency and cost.
   - Mitigation: benchmark overhead and apply sampling/verbosity controls with explicit budgets.

---

## 11. Final Prioritized Recommendations

1. Execute Integration-First Sprint before any major new architecture.
2. Treat eval, tracing, and checkpoint reliability as hard gates, not optional observability.
3. Reclassify roadmap items using `Implemented/Wired/Enabled/E2E/CI` status fields.
4. Standardize schema-first handoff/tool contracts before adding new orchestration complexity.
5. Delay heavy model-complexity work until integration gains plateau.
6. Keep coordinator/multi-agent expansion conditional on measured need.

---

## 12. Source References

### External references

- OpenAI practical guide to agents:
  - https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
- OpenAI building agents track:
  - https://developers.openai.com/tracks/building-agents/
- OpenAI evaluation best practices:
  - https://developers.openai.com/api/docs/guides/evaluation-best-practices/
- OpenAI Agents SDK (Context7 doc source):
  - https://github.com/openai/openai-agents-python
- OpenAI Agents SDK quickstart (guardrails/handoffs patterns):
  - https://github.com/openai/openai-agents-python/blob/main/docs/quickstart.md
- OpenAI Agents SDK tracing docs:
  - https://github.com/openai/openai-agents-python/blob/main/docs/tracing.md
- OpenAI Agents SDK guardrails docs:
  - https://github.com/openai/openai-agents-python/blob/main/docs/guardrails.md
- Anthropic building effective agents:
  - https://www.anthropic.com/research/building-effective-agents
- Anthropic effective context engineering:
  - https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic writing effective tools for agents:
  - https://www.anthropic.com/engineering/writing-tools-for-agents
- LangGraph README (durability/HITL/memory):
  - https://github.com/langchain-ai/langgraph/blob/main/README.md
- LangGraph checkpointing configuration:
  - https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint/README.md
- LangGraph persistence/how-to examples:
  - https://langchain-ai.github.io/langgraph/how-tos/persistence-functional/
- DSPy optimization overview:
  - https://dspy.ai/learn/optimization/overview/index
- DSPy optimizer guidance:
  - https://dspy.ai/learn/optimization/optimizers/

### Internal evidence references

- `backend/app/domain/services/agents/base.py`
- `backend/app/domain/services/agents/stuck_detector.py`
- `backend/app/domain/services/memory_service.py`
- `backend/app/infrastructure/repositories/qdrant_memory_repository.py`
- `backend/app/domain/services/conversation_context_service.py`
- `backend/app/infrastructure/repositories/conversation_context_repository.py`
- `backend/app/domain/services/orchestration/swarm.py`
- `backend/app/domain/services/orchestration/coordinator_flow.py`
- `backend/app/domain/services/orchestration/handoff.py`
- `backend/app/domain/services/evaluation/ragas_metrics.py`
- `backend/app/domain/services/agents/error_integration.py`
- `backend/app/domain/services/prediction/failure_predictor.py`
- `backend/app/domain/services/agents/guardrails.py`
- `backend/app/domain/external/tracing.py`
- `backend/app/infrastructure/observability/tracer.py`
- `backend/app/domain/services/tools/tool_tracing.py`
- `backend/app/domain/services/flows/checkpoint_manager.py`
- `backend/app/domain/services/flows/graph_checkpoint_manager.py`
- `backend/app/core/config_features.py`
