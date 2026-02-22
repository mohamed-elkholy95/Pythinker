# DSPy + GEPA Prompt Optimization Integration Plan (Pythinker)

Date: 2026-02-22
Owner: Backend / Agent Architecture
Status: Drafted (planning only)
Implementation Status: Not Started

## 1. Objective
Integrate a research-backed, open-source prompt optimization pipeline using **DSPy + GEPA** for Pythinker, with:
- Offline optimization of planner and execution prompt policies.
- Safe runtime rollout via existing feature-flag architecture.
- Reuse of existing eval infrastructure (`backend/tests/evals/*`) and quality gates.
- No disruption to current default behavior until explicit rollout.

## 2. Scope and Non-Goals
### In Scope
- Prompt optimization for these surfaces:
  - Planner prompt generation (`backend/app/domain/services/prompts/planner.py`).
  - Execution prompt generation (`backend/app/domain/services/prompts/execution.py`).
  - Optional system prompt sections (`backend/app/domain/services/prompts/system.py`).
- Offline optimizer orchestration and artifact persistence.
- Runtime prompt profile selection and fallback safety.
- Evaluation dataset and scoring pipeline for optimizer training/validation.

### Out of Scope (for this plan)
- Fine-tuning model weights.
- Replacing current LLM provider stack.
- Frontend UI for optimization management (API-first delivery).

## 3. Current Pythinker Integration Anchors
These are the concrete attachment points in the current codebase:
- System prompt construction: `backend/app/domain/services/prompts/system.py`.
- Planner prompt construction: `backend/app/domain/services/prompts/planner.py`.
- Execution prompt construction: `backend/app/domain/services/prompts/execution.py`.
- Execution-time prompt assembly: `backend/app/domain/services/agents/execution.py`.
- Planner-time prompt assembly: `backend/app/domain/services/agents/planner.py`.
- Flow wiring and feature flags propagation: `backend/app/domain/services/flows/plan_act.py`.
- Feature flag source and mapping: `backend/app/core/config_features.py`, `backend/app/core/config.py`.
- Session/event persistence for dataset extraction: `backend/app/infrastructure/repositories/mongo_session_repository.py`, `backend/app/infrastructure/models/documents.py`, `backend/app/domain/models/event.py`.
- Existing eval framework: `backend/tests/evals/types.py`, `backend/tests/evals/eval_runner.py`, `backend/tests/evals/graders/deterministic.py`, `backend/tests/evals/graders/llm_judge.py`.

## 4. Context7-Validated Requirements (DSPy/GEPA)
Validated against Context7 docs for `/stanfordnlp/dspy`:
- GEPA optimization metric should return rich feedback, commonly as `dspy.Prediction(score=..., feedback=...)`.
- GEPA compile workflow is train/val based (`optimizer.compile(program, trainset=..., valset=...)`).
- Datasets are created as `dspy.Example(...).with_inputs(...)`.
- Optimized programs should be persisted with `.save(...)` and loaded with `.load(...)`.
- MIPROv2 remains a strong baseline and can be run in `auto="light|medium|heavy"` modes.

Implication for Pythinker:
- We must produce train/val splits and feedback-rich metrics, not pass/fail-only signals.
- We should store versioned optimizer artifacts and support deterministic rollback.

## 5. High-Level Architecture
Design principle: keep runtime inference lightweight; keep DSPy/GEPA dependency pressure mostly in the offline optimization path.

### 5.1 Domain Model Additions
Create domain-level optimization contracts and profile models:
- `backend/app/domain/models/prompt_profile.py`
- `backend/app/domain/models/prompt_optimization.py`
- `backend/app/domain/repositories/prompt_profile_repository.py`

Core entities:
- `PromptTarget`: `planner`, `execution`, `system`.
- `PromptProfile`: immutable versioned profile used at runtime.
- `OptimizationRun`: metadata for one optimizer run.
- `OptimizationCase`: normalized training/eval example.

### 5.2 Domain Services
- `backend/app/domain/services/prompt_optimization/dataset_builder.py`
  - Build optimization cases from session events + curated eval datasets.
- `backend/app/domain/services/prompt_optimization/scoring.py`
  - Compute scalar score + textual feedback for GEPA.
- `backend/app/domain/services/prompt_optimization/dspy_adapter.py`
  - Wrap DSPy program definitions for planner/execution targets.
- `backend/app/domain/services/prompt_optimization/profile_resolver.py`
  - Resolve active prompt profile at runtime based on flags + canary policy.

### 5.3 Application Service
- `backend/app/application/services/prompt_optimization_service.py`
  - Orchestrate export, optimize, validate, publish, and rollback operations.

### 5.4 Infrastructure
- `backend/app/infrastructure/repositories/mongo_prompt_profile_repository.py`
- `backend/app/infrastructure/repositories/gridfs_prompt_artifact_repository.py`
- `backend/scripts/run_dspy_prompt_optimization.py`
- `backend/scripts/export_prompt_optimization_dataset.py`

### 5.5 Interface/API
- `backend/app/interfaces/api/prompt_optimization_routes.py`
- `backend/app/interfaces/schemas/prompt_optimization.py`
- Router registration in `backend/app/interfaces/api/routes.py`.
- DI wiring in `backend/app/interfaces/dependencies.py`.

## 6. Interface Contracts (Concrete)

```python
# backend/app/domain/models/prompt_profile.py
from pydantic import BaseModel, Field
from datetime import datetime

class PromptTarget(str, Enum):
    PLANNER = "planner"
    EXECUTION = "execution"
    SYSTEM = "system"

class PromptPatch(BaseModel):
    target: PromptTarget
    profile_id: str
    variant_id: str
    patch_text: str
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)

class PromptProfile(BaseModel):
    id: str
    name: str
    version: str
    created_at: datetime
    source_run_id: str
    patches: list[PromptPatch]
    validation_summary: dict[str, float] = Field(default_factory=dict)
    is_active: bool = False
```

```python
# backend/app/domain/repositories/prompt_profile_repository.py
from typing import Protocol

class PromptProfileRepository(Protocol):
    async def save_profile(self, profile: PromptProfile) -> None: ...
    async def get_profile(self, profile_id: str) -> PromptProfile | None: ...
    async def get_active_profile(self) -> PromptProfile | None: ...
    async def activate_profile(self, profile_id: str) -> None: ...
    async def list_profiles(self, limit: int = 20) -> list[PromptProfile]: ...
```

```python
# backend/app/domain/services/prompt_optimization/profile_resolver.py
class PromptProfileResolver:
    async def resolve_for_session(self, session_id: str, user_id: str) -> PromptProfile | None: ...
    def should_use_profile(self, *, session_id: str, canary_percent: int) -> bool: ...
```

```python
# backend/app/domain/services/prompt_optimization/scoring.py
class OptimizationScore(BaseModel):
    score: float
    feedback: str
    components: dict[str, float]

class OptimizationScorer:
    async def score_planner_case(self, case: OptimizationCase, output: dict) -> OptimizationScore: ...
    async def score_execution_case(self, case: OptimizationCase, output: dict) -> OptimizationScore: ...
```

## 7. Eval Dataset Shape (Canonical)
The optimizer dataset should be normalized but map directly to existing eval concepts.

### 7.1 New Normalized Schema
File: `backend/tests/evals/datasets/prompt_optimization_cases.json`

```json
{
  "name": "prompt_optimization_cases",
  "version": "1.0.0",
  "description": "Planner and execution cases for DSPy+GEPA optimization",
  "cases": [
    {
      "id": "exec_0001",
      "target": "execution",
      "input": {
        "user_request": "Research Python 3.13 features and summarize with sources",
        "step_description": "Research latest Python 3.13 features from official sources",
        "available_tools": ["info_search_web", "browser_navigate", "file_write"],
        "attachments": []
      },
      "expected": {
        "must_call_tools": ["info_search_web"],
        "must_contain": ["source", "Python 3.13"],
        "must_not_contain": ["fabricated"],
        "min_citations": 2
      },
      "labels": {
        "quality_score": 0.0,
        "success": null
      },
      "metadata": {
        "source": "curated",
        "difficulty": "medium"
      }
    }
  ]
}
```

### 7.2 Mapping to Existing Eval Types
- Input signal maps to `EvalCase.input` + `EvalCase.input_context` in `backend/tests/evals/types.py`.
- Expected constraints map to deterministic and LLM judge graders.
- Runtime-generated cases can be exported from session events with:
  - User `MessageEvent`.
  - `StepEvent` success/failure outcome.
  - `ToolEvent` sequence and counts.
  - Final `MessageEvent`/`ReportEvent` content.

### 7.3 DSPy Conversion
Each normalized case is transformed to:
- `dspy.Example(...).with_inputs("request_payload")` for planner/execution programs.
- Split policy:
  - `train`: 70%
  - `val`: 20%
  - `test`: 10%
- Deterministic stratification by `target` + `difficulty`.

## 8. Scoring Strategy for GEPA (Scalar + Feedback)
GEPA requires scalar optimization signal plus explanatory feedback.

### 8.1 Planner Score
`planner_score = 0.45 * deterministic_structure + 0.35 * llm_plan_quality + 0.20 * tool_feasibility`

Feedback text combines:
- Missing/overlong steps.
- Tool mismatch against available tools.
- Feasibility/coherence comments from LLMJudge.

### 8.2 Execution Score
`execution_score = 0.30 * deterministic_constraints + 0.30 * llm_response_quality + 0.20 * hallucination_check + 0.10 * latency_score + 0.10 * token_efficiency`

Feedback text combines:
- Missing required content/citations.
- Hallucination flags.
- Redundant tool call warnings.

### 8.3 GEPA Metric Return Contract
Metric function returns:
- `dspy.Prediction(score=<0..1>, feedback="...")`

This satisfies the Context7-documented GEPA feedback workflow.

## 9. Prompt Application Strategy at Runtime
Do not replace existing prompt builders. Layer profile patches on top.

### 9.1 Integration Points
- `build_create_plan_prompt(...)` in `backend/app/domain/services/prompts/planner.py`.
- `build_execution_prompt_from_context(...)` in `backend/app/domain/services/prompts/execution.py`.
- `build_system_prompt(...)` in `backend/app/domain/services/prompts/system.py`.

### 9.2 Runtime Behavior
- Default: baseline prompts only.
- If profile feature enabled and resolver returns active profile:
  - Inject target-specific patch block (deterministic, versioned).
  - Attach metadata marker: `profile_id`, `variant_id`, `target`.
- On any patch load/parse error:
  - Fallback to baseline immediately.
  - Emit fallback metric and warning log.

## 10. Feature Flags and Config
Add these to `backend/app/core/config_features.py` and map through `backend/app/core/config.py`:
- `feature_prompt_optimization_pipeline: bool = False`
- `feature_prompt_profile_runtime: bool = False`
- `feature_prompt_profile_shadow: bool = True`
- `prompt_profile_canary_percent: int = 0`
- `prompt_profile_active_id: str | None = None`
- `prompt_optimization_min_cases: int = 100`

Rationale:
- `pipeline`: allows running optimization jobs.
- `runtime`: allows prompt patch application.
- `shadow`: compute deltas without affecting output.
- `canary_percent`: deterministic session-level rollout.

## 11. PR Plan (Concrete, Sequential)
All PR statuses below are currently **Not Started**.

### PR-1: Domain Foundation
Status: Not Started

Files to add:
- `backend/app/domain/models/prompt_profile.py`
- `backend/app/domain/models/prompt_optimization.py`
- `backend/app/domain/repositories/prompt_profile_repository.py`
- `backend/tests/domain/models/test_prompt_profile.py`

Files to modify:
- `backend/app/domain/services/agents/learning/prompt_optimizer.py` (add compatibility hooks to consume offline variants)

Acceptance:
- Domain contracts compile and validate.
- Unit tests pass for models and repository protocol typing.

### PR-2: Persistence Layer
Status: Not Started

Files to add:
- `backend/app/infrastructure/repositories/mongo_prompt_profile_repository.py`
- `backend/app/infrastructure/repositories/gridfs_prompt_artifact_repository.py`
- `backend/tests/infrastructure/repositories/test_mongo_prompt_profile_repository.py`

Files to modify:
- `backend/app/core/lifespan.py` (initialize repository wiring if required)
- `backend/app/interfaces/dependencies.py` (dependency providers)

Acceptance:
- Save/list/activate/get profile flows validated.
- Artifact upload/download tested with GridFS.

### PR-3: Dataset Export and Normalization
Status: Not Started

Files to add:
- `backend/app/domain/services/prompt_optimization/dataset_builder.py`
- `backend/scripts/export_prompt_optimization_dataset.py`
- `backend/tests/domain/services/prompt_optimization/test_dataset_builder.py`
- `backend/tests/evals/datasets/prompt_optimization_cases.json`

Files to modify:
- `backend/tests/evals/types.py` (only if additional metadata fields are necessary)

Acceptance:
- Dataset export from session events and curated cases produces valid schema.
- Split reproducibility guaranteed by seed.

### PR-4: DSPy Adapter + GEPA/MIPRO Orchestrator
Status: Not Started

Files to add:
- `backend/app/domain/services/prompt_optimization/dspy_adapter.py`
- `backend/app/domain/services/prompt_optimization/scoring.py`
- `backend/app/domain/services/prompt_optimization/optimizer_orchestrator.py`
- `backend/scripts/run_dspy_prompt_optimization.py`
- `backend/tests/domain/services/prompt_optimization/test_scoring.py`
- `backend/tests/domain/services/prompt_optimization/test_optimizer_orchestrator.py`

Files to modify:
- `backend/requirements-dev.txt` (or new `backend/requirements-optimization.txt`) to include DSPy optimization dependencies.

Acceptance:
- Can run baseline MIPROv2 and GEPA runs offline.
- Produces persisted optimized artifact and summary metrics.

### PR-5: Runtime Prompt Profile Resolver
Status: Not Started

Files to add:
- `backend/app/domain/services/prompt_optimization/profile_resolver.py`
- `backend/tests/domain/services/prompt_optimization/test_profile_resolver.py`

Files to modify:
- `backend/app/domain/services/prompts/system.py`
- `backend/app/domain/services/prompts/planner.py`
- `backend/app/domain/services/prompts/execution.py`
- `backend/app/domain/services/agents/planner.py`
- `backend/app/domain/services/agents/execution.py`

Acceptance:
- Baseline behavior unchanged when flags are off.
- Profile patches are deterministic and reversible.
- Fallback path tested.

### PR-6: API and Operational Controls
Status: Not Started

Files to add:
- `backend/app/application/services/prompt_optimization_service.py`
- `backend/app/interfaces/schemas/prompt_optimization.py`
- `backend/app/interfaces/api/prompt_optimization_routes.py`
- `backend/tests/interfaces/api/test_prompt_optimization_routes.py`

Files to modify:
- `backend/app/interfaces/api/routes.py`
- `backend/app/interfaces/dependencies.py`

API endpoints:
- `POST /api/v1/prompt-optimization/runs` (start run)
- `GET /api/v1/prompt-optimization/runs/{run_id}` (status)
- `GET /api/v1/prompt-optimization/profiles` (list)
- `POST /api/v1/prompt-optimization/profiles/{profile_id}/activate` (activate)
- `POST /api/v1/prompt-optimization/profiles/{profile_id}/rollback` (rollback)

Acceptance:
- Admin-gated operational control works end-to-end.
- Run metadata and artifacts are queryable.

### PR-7: Rollout, Metrics, and Guardrails
Status: Not Started

Files to modify:
- `backend/app/core/config_features.py`
- `backend/app/core/config.py`
- `backend/app/core/prometheus_metrics.py`
- `backend/app/domain/services/flows/plan_act.py` (shadow vs active profile path)

New metrics:
- `pythinker_prompt_profile_selection_total{profile_id,target,mode}`
- `pythinker_prompt_profile_fallback_total{reason}`
- `pythinker_prompt_optimization_run_duration_seconds{optimizer}`
- `pythinker_prompt_optimization_score{profile_id,target}`
- `pythinker_prompt_shadow_delta{metric}`

Acceptance:
- Shadow mode emits deltas without behavior change.
- Canary gating works with deterministic session hashing.

## 12. Rollout Strategy
### Phase 0: Offline Only
- Keep all runtime flags OFF.
- Generate baseline and optimized profiles from curated + historical datasets.
- Compare against held-out test split.

Exit criteria:
- No regression on deterministic constraints.
- +X% improvement on weighted quality score (target set per run).

### Phase 1: Shadow Mode
- Enable `feature_prompt_profile_shadow=true`.
- Compute profile candidate score in parallel, do not apply patch to user-visible behavior.

Exit criteria:
- Stable positive shadow deltas for 3 consecutive evaluation windows.
- No latency/cost spike beyond threshold.

### Phase 2: Canary
- Enable runtime + `prompt_profile_canary_percent=5`.
- Session-hash assignment for deterministic traffic split.

Exit criteria:
- Error and fallback rates within threshold.
- Quality deltas remain positive.

### Phase 3: Progressive Ramp
- Ramp 5% -> 25% -> 50% -> 100%.
- Keep one-click rollback via active profile pointer.

Rollback triggers:
- Increased hallucination/quality gate failures.
- Sustained latency or token-cost regression.
- Elevated fallback rate.

## 13. Validation and Test Plan
### Unit
- Profile models and repository behavior.
- Dataset normalization and split determinism.
- Scoring function correctness and feedback generation.
- Resolver canary determinism and fallback behavior.

### Integration
- Run orchestration -> artifact persistence -> profile activation.
- Prompt builders apply patches only when flags and profile are active.

### Regression
- Existing prompt tests must stay green:
  - `backend/tests/domain/services/prompts/test_execution_prompt_from_context.py`
- Existing eval runner remains compatible:
  - `backend/tests/evals/eval_runner.py`

### Required checks
- `cd frontend && bun run lint && bun run type-check`
- `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`

## 14. Risks and Mitigations
- Risk: Overfitting prompts to synthetic or narrow cases.
  - Mitigation: Mix curated + historical session-derived cases and maintain held-out test set.
- Risk: Runtime prompt drift hurting cache efficiency.
  - Mitigation: Stable profile IDs, deterministic patches, and cache metrics monitoring.
- Risk: Optimization score hacking.
  - Mitigation: Composite score with deterministic and judge-based components plus constraints.
- Risk: Operational complexity.
  - Mitigation: API controls, profile immutability, and explicit rollback path.

## 15. Deliverables Checklist
- [ ] Domain contracts for profiles and optimization runs.
- [ ] Dataset builder and exporter scripts.
- [ ] DSPy+GEPA optimization runner with MIPRO baseline.
- [ ] Runtime profile resolver and prompt patching integration.
- [ ] Admin API for runs/profiles.
- [ ] Feature flags + Prometheus instrumentation.
- [ ] Test coverage for unit/integration/regression.

## 16. Source Validation References
Primary references used in this plan:
- Context7 DSPy docs (`/stanfordnlp/dspy`) for GEPA feedback metric, compile workflow, dataset format, and save/load behavior.
- Pythinker code paths listed in Sections 3 and 11.

External canonical docs:
- DSPy repository: `https://github.com/stanfordnlp/dspy`
- GEPA optimizer docs in DSPy:
  - `https://github.com/stanfordnlp/dspy/blob/main/docs/docs/api/optimizers/GEPA/overview.md`
- MIPROv2 docs in DSPy:
  - `https://github.com/stanfordnlp/dspy/blob/main/docs/docs/api/optimizers/MIPROv2.md`
