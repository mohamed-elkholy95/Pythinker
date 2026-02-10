# Design Standardization and Legacy Flow Deprecation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Standardize the app UI/UX (especially research workflows) on a single design system and simplify backend flow orchestration by deprecating and removing Legacy Flow if production usage is effectively zero.

**Architecture:** We will deliver this in three tracks: (1) frontend design-token and component standardization, (2) deep research workflow parity between backend and frontend with phased progress visibility, and (3) controlled Legacy Flow deprecation/removal behind evidence-based decision gates. The default execution engine remains `PlanActFlow`, and all research UX/events are aligned to that path to avoid split behavior.

**Tech Stack:** Vue 3, TypeScript, Tailwind, Vitest, FastAPI, Pydantic v2, asyncio, pytest, ruff.

---

## Current-State Findings (from codebase)

1. `PlanActFlow` is the runtime default and `.env` has `FLOW_MODE=false`.
2. `Legacy Flow PlanActFlow` explicitly states skill support is incomplete (`backend/app/domain/services/legacy-flow/flow.py`).
3. `StreamEvent.phase` exists in domain model but is dropped by SSE schema (`backend/app/interfaces/schemas/event.py`), so frontend phase-aware streaming is partially broken.
4. Deep research endpoints (`approve/skip/status`) use `DeepResearchManager`, but `PlanActFlow` deep research path bypasses that manager and calls wide research directly.
5. Frontend token foundation exists (`frontend/src/assets/theme.css`) but shared tool-view tokens (`--space-*`, `--radius-*`, `--text-*`, `--font-*`) are used without definitions.
6. High-priority UI surfaces still have many hard-coded colors/legacy fallback variables, producing visual inconsistency.

---

## Decision Gates

### Gate A: Legacy Flow Removal Eligibility

Proceed to removal only if all are true:
- No production/staging sessions use `flow_mode=legacy-flow` for 14 days.
- No business-critical feature exists only in Legacy Flow path.
- PlanAct path passes full backend regression suite for chat/research/session streaming.

### Gate B: Design Rollout Safety

Proceed to broad UI token migration only if:
- Frontend lint/type-check pass.
- Visual QA for Chat, Home, Session History, Tool Panel, Deep Research, Wide Research passes on desktop and mobile widths.

---

### Task 0: Baseline Audit and Acceptance Criteria Lock

**Files:**
- Create: `docs/reports/2026-02-10-design-and-flow-baseline.md`
- Modify: `docs/plans/2026-02-10-design-standardization-and-legacy-flow-deprecation-plan.md`

**Step 1: Capture frontend style debt baseline**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
cd frontend
rg -n "#[0-9a-fA-F]{3,8}|rgba\\(|hsl\\(" src/components src/pages src/assets > /tmp/frontend_color_literals.txt
wc -l /tmp/frontend_color_literals.txt
```

**Step 2: Capture Legacy Flow coupling baseline**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
rg -n "legacy-flow|Legacy Flow|legacy_flow_removed|FlowMode\\.LANGGRAPH" backend/app backend/tests backend/requirements.txt > /tmp/legacy_flow_removed_references.txt
wc -l /tmp/legacy_flow_removed_references.txt
```

**Step 3: Record exact acceptance metrics**

- Save count snapshots and target reductions in `docs/reports/2026-02-10-design-and-flow-baseline.md`.

**Step 4: Commit docs-only baseline**

```bash
git add docs/reports/2026-02-10-design-and-flow-baseline.md docs/plans/2026-02-10-design-standardization-and-legacy-flow-deprecation-plan.md
git commit -m "docs: add design and flow baseline for standardization plan"
```

---

### Task 1: Complete Missing Design Tokens (Foundation Fix)

**Files:**
- Modify: `frontend/src/assets/theme.css`
- Create: `frontend/tests/utils/themeTokens.spec.ts`

**Step 1: Write failing token presence test**

```ts
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

describe('theme tokens', () => {
  it('defines shared spacing/radius/typography tokens used by tool views', () => {
    const css = readFileSync('src/assets/theme.css', 'utf-8')
    const required = [
      '--space-1:', '--space-2:', '--space-3:', '--space-4:', '--space-6:', '--space-8:', '--space-12:',
      '--radius-sm:', '--radius-md:', '--radius-lg:',
      '--text-xs:', '--text-sm:', '--text-base:',
      '--font-normal:', '--font-medium:', '--font-semibold:',
    ]
    for (const token of required) expect(css.includes(token)).toBe(true)
  })
})
```

**Step 2: Run test to verify failure**

```bash
cd /Users/panda/Desktop/Projects/Pythinker/frontend
bun run vitest tests/utils/themeTokens.spec.ts
```

Expected: FAIL on missing token declarations.

**Step 3: Add token definitions with light/dark-safe values**

- Add missing `--space-*`, `--radius-*`, `--text-*`, `--font-*` tokens into `:root` and dark-compatible aliases in `frontend/src/assets/theme.css`.
- Add compatibility aliases for legacy names still used in pages (for example `--background-secondary`, `--border-color`, `--text-muted`) mapped to existing canonical tokens.

**Step 4: Re-run token test**

```bash
cd /Users/panda/Desktop/Projects/Pythinker/frontend
bun run vitest tests/utils/themeTokens.spec.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/assets/theme.css frontend/tests/utils/themeTokens.spec.ts
git commit -m "feat(frontend): add missing shared design tokens and legacy aliases"
```

---

### Task 2: Standardize High-Impact UI Surfaces (No Hard-Coded Palette)

**Files:**
- Modify: `frontend/src/pages/SessionHistoryPage.vue`
- Modify: `frontend/src/components/SandboxViewer.vue`
- Modify: `frontend/src/components/SessionReplayPlayer.vue`
- Modify: `frontend/src/components/ReplayTimeline.vue`
- Modify: `frontend/src/components/SessionFileList.vue`
- Create: `frontend/tests/components/DesignSurfaceTokens.spec.ts`

**Step 1: Write failing component-level token usage tests**

- Add test assertions that these components no longer include hard-coded fallback hex values in scoped styles for core surfaces (background, text, border, status).

**Step 2: Run test to verify failure**

```bash
cd /Users/panda/Desktop/Projects/Pythinker/frontend
bun run vitest tests/components/DesignSurfaceTokens.spec.ts
```

**Step 3: Replace hard-coded color values with semantic tokens**

- Use canonical tokens from `theme.css` (`--background-*`, `--text-*`, `--border-*`, `--function-*`).
- Keep status accents (`success/warning/error`) mapped through token variables rather than inline colors.

**Step 4: Re-run tests**

```bash
cd /Users/panda/Desktop/Projects/Pythinker/frontend
bun run vitest tests/components/DesignSurfaceTokens.spec.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/pages/SessionHistoryPage.vue frontend/src/components/SandboxViewer.vue frontend/src/components/SessionReplayPlayer.vue frontend/src/components/ReplayTimeline.vue frontend/src/components/SessionFileList.vue frontend/tests/components/DesignSurfaceTokens.spec.ts
git commit -m "refactor(frontend): standardize priority surfaces on semantic theme tokens"
```

---

### Task 3: Tool-View Standardization Completion

**Files:**
- Modify: `frontend/src/components/toolViews/shared/ContentContainer.vue`
- Modify: `frontend/src/components/toolViews/shared/LoadingState.vue`
- Modify: `frontend/src/components/toolViews/shared/EmptyState.vue`
- Modify: `frontend/src/components/toolViews/shared/ErrorState.vue`
- Modify: `frontend/src/components/toolViews/GenericContentView.vue`
- Modify: `frontend/src/components/ToolPanelContent.vue`
- Create: `frontend/tests/components/ToolViewStandardization.spec.ts`

**Step 1: Write failing tests for consistent loading/empty/error patterns**

- Ensure each tool view routes through shared states and consistent spacing/typography tokens.

**Step 2: Run targeted tests**

```bash
cd /Users/panda/Desktop/Projects/Pythinker/frontend
bun run vitest tests/components/ToolViewStandardization.spec.ts tests/components/ToolPanel.spec.ts tests/components/ToolUse.spec.ts
```

**Step 3: Standardize props/state usage and remove local stylistic divergence**

- Ensure consistent container sizing (`height`, `overflow`, `padding`) and standardized status rendering.

**Step 4: Re-run tests**

```bash
cd /Users/panda/Desktop/Projects/Pythinker/frontend
bun run vitest tests/components/ToolViewStandardization.spec.ts tests/components/ToolPanel.spec.ts tests/components/ToolUse.spec.ts
```

**Step 5: Commit**

```bash
git add frontend/src/components/toolViews/shared/ContentContainer.vue frontend/src/components/toolViews/shared/LoadingState.vue frontend/src/components/toolViews/shared/EmptyState.vue frontend/src/components/toolViews/shared/ErrorState.vue frontend/src/components/toolViews/GenericContentView.vue frontend/src/components/ToolPanelContent.vue frontend/tests/components/ToolViewStandardization.spec.ts
git commit -m "refactor(frontend): complete shared tool-view standardization"
```

---

### Task 4: Research UX Unification (Deep + Wide + Phase-Aware)

**Files:**
- Create: `frontend/src/components/research/ResearchPhaseIndicator.vue`
- Create: `frontend/src/composables/useResearchWorkflow.ts`
- Modify: `frontend/src/pages/ChatPage.vue`
- Modify: `frontend/src/components/WideResearchOverlay.vue`
- Modify: `frontend/src/components/DeepResearchCard.vue`
- Modify: `frontend/src/types/event.ts`
- Create: `frontend/tests/composables/useResearchWorkflow.spec.ts`

**Step 1: Write failing tests for research event state transitions**

- Cover `phase_transition`, `checkpoint_saved`, and reflection stream updates.

**Step 2: Run tests to verify failure**

```bash
cd /Users/panda/Desktop/Projects/Pythinker/frontend
bun run vitest tests/composables/useResearchWorkflow.spec.ts
```

**Step 3: Implement unified composable + indicator**

- Move research progress state out of split logic (`useWideResearch` + card-local) into a single state model.
- Keep existing visual language but standardize typography/colors with tokens.

**Step 4: Wire ChatPage event handlers**

- Add typed handling for phased research events.
- Preserve backward compatibility for existing `wide_research` and `deep_research` events.

**Step 5: Re-run tests**

```bash
cd /Users/panda/Desktop/Projects/Pythinker/frontend
bun run vitest tests/composables/useResearchWorkflow.spec.ts tests/components/ChatMessage.spec.ts
```

**Step 6: Commit**

```bash
git add frontend/src/components/research/ResearchPhaseIndicator.vue frontend/src/composables/useResearchWorkflow.ts frontend/src/pages/ChatPage.vue frontend/src/components/WideResearchOverlay.vue frontend/src/components/DeepResearchCard.vue frontend/src/types/event.ts frontend/tests/composables/useResearchWorkflow.spec.ts
git commit -m "feat(frontend): unify deep and wide research UX with phase-aware workflow state"
```

---

### Task 5: Fix Stream Event Schema Parity (Backend -> Frontend)

**Files:**
- Modify: `backend/app/interfaces/schemas/event.py`
- Modify: `backend/tests/interfaces/api/test_sse_streaming.py`

**Step 1: Write failing backend test for stream phase passthrough**

- Assert SSE `stream` payload includes `phase` when emitted by domain `StreamEvent`.

**Step 2: Run targeted test**

```bash
conda activate pythinker && cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_sse_streaming.py -q
```

Expected: FAIL due to missing `phase` field in schema.

**Step 3: Implement schema fix**

- Add `phase: str | None = None` (and optionally `phase_metadata`) to `StreamEventData`.

**Step 4: Re-run test**

```bash
conda activate pythinker && cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_sse_streaming.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/interfaces/schemas/event.py backend/tests/interfaces/api/test_sse_streaming.py
git commit -m "fix(backend): preserve stream phase metadata in SSE schema"
```

---

### Task 6: Route Deep Research Through a Single Orchestrator

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Modify: `backend/app/core/deep_research_manager.py`
- Modify: `backend/app/interfaces/api/session_routes.py`
- Modify: `backend/tests/test_deep_research.py`
- Modify: `backend/tests/test_wide_research_fix.py`
- Create: `backend/tests/domain/services/research/test_phased_research_flow.py`

**Step 1: Write failing integration tests**

- Validate that deep research started from chat can be controlled via `/deep-research/approve` and `/deep-research/skip`.
- Validate status endpoint reflects actual runtime session.

**Step 2: Run failing tests**

```bash
conda activate pythinker && cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest -p no:cov -o addopts= tests/test_deep_research.py tests/test_wide_research_fix.py -q
```

**Step 3: Implement single-path orchestration**

- Replace direct wide-research bypass path in `PlanActFlow` with manager-registered flow execution.
- Keep fallback compatibility for existing event consumers.

**Step 4: Re-run tests**

```bash
conda activate pythinker && cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest -p no:cov -o addopts= tests/test_deep_research.py tests/test_wide_research_fix.py tests/domain/services/research/test_phased_research_flow.py -q
```

**Step 5: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py backend/app/core/deep_research_manager.py backend/app/interfaces/api/session_routes.py backend/tests/test_deep_research.py backend/tests/test_wide_research_fix.py backend/tests/domain/services/research/test_phased_research_flow.py
git commit -m "refactor(backend): unify deep research execution and manager control path"
```

---

### Task 7: Implement Phased Research Workflow (Based on Research Plan)

**Files:**
- Create: `backend/app/domain/models/research_phase.py`
- Create: `backend/app/domain/services/research/checkpoint_manager.py`
- Create: `backend/app/domain/services/agents/reflective_executor.py`
- Create: `backend/app/domain/services/flows/phased_research.py`
- Modify: `backend/app/domain/services/flows/__init__.py`
- Create: `backend/tests/domain/services/research/test_checkpoint_manager.py`
- Create: `backend/tests/domain/services/research/test_reflective_executor.py`

**Step 1: Write failing unit tests for checkpoints/reflection**

**Step 2: Run tests and confirm failure**

```bash
conda activate pythinker && cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest -p no:cov -o addopts= tests/domain/services/research/test_checkpoint_manager.py tests/domain/services/research/test_reflective_executor.py -q
```

**Step 3: Implement minimal domain services**

- Keep business logic in domain services.
- Ensure Pydantic validators follow v2 classmethod requirements.

**Step 4: Integrate phased flow into deep research path behind feature flag**

- Add `feature_phased_research` in `backend/app/core/config.py`.

**Step 5: Re-run research tests**

```bash
conda activate pythinker && cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest -p no:cov -o addopts= tests/domain/services/research/test_checkpoint_manager.py tests/domain/services/research/test_reflective_executor.py tests/domain/services/research/test_phased_research_flow.py -q
```

**Step 6: Commit**

```bash
git add backend/app/domain/models/research_phase.py backend/app/domain/services/research/checkpoint_manager.py backend/app/domain/services/agents/reflective_executor.py backend/app/domain/services/flows/phased_research.py backend/app/domain/services/flows/__init__.py backend/app/core/config.py backend/tests/domain/services/research/test_checkpoint_manager.py backend/tests/domain/services/research/test_reflective_executor.py
git commit -m "feat(backend): add phased reflective research workflow with checkpoints"
```

---

### Task 8: Legacy Flow Soft Deprecation (No Runtime Breakage)

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `backend/app/domain/services/flows/__init__.py`
- Modify: `backend/app/domain/models/event.py`
- Modify: `backend/docs/SKILL_SYSTEM_ARCHITECTURE.md`
- Create: `backend/tests/test_flow_mode_selection.py`

**Step 1: Write failing tests for flow mode behavior**

- Assert invalid/legacy Legacy Flow selection falls back to `PLAN_ACT` with warning.

**Step 2: Run tests**

```bash
conda activate pythinker && cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest -p no:cov -o addopts= tests/test_flow_mode_selection.py -q
```

**Step 3: Implement deprecation behavior**

- Mark `FlowMode.LEGACY_FLOW_REMOVED` and `legacy_flow_removed` as deprecated.
- Emit explicit runtime warning and `FlowSelectionEvent` reason when fallback occurs.

**Step 4: Re-run tests**

```bash
conda activate pythinker && cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest -p no:cov -o addopts= tests/test_flow_mode_selection.py -q
```

**Step 5: Commit**

```bash
git add backend/app/core/config.py backend/app/domain/services/agent_task_runner.py backend/app/domain/services/flows/__init__.py backend/app/domain/models/event.py backend/docs/SKILL_SYSTEM_ARCHITECTURE.md backend/tests/test_flow_mode_selection.py
git commit -m "refactor(backend): soft-deprecate legacy-flow flow selection in favor of plan_act"
```

---

### Task 9: Legacy Flow Hard Removal (Execute Only After Gate A Passes)

**Files:**
- Delete: `backend/app/domain/services/legacy-flow/` (entire directory)
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `backend/app/domain/services/flows/__init__.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/tests/conftest.py`
- Delete: `backend/tests/domain/services/lg_workflow/` (and related `lg_workflow_*`, `test_legacy-flow_*`)

**Step 1: Write/update tests for no-legacy-flow runtime path**

- Ensure all flow selection tests now cover only `plan_act` and `coordinator`.

**Step 2: Remove dependency and code references**

- Remove `legacy-flow` and `legacy-flow-checkpoint` from requirements.
- Remove import shadowing preload hack in `backend/tests/conftest.py`.

**Step 3: Run targeted backend regression**

```bash
conda activate pythinker && cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_session_routes.py tests/interfaces/api/test_sse_streaming.py tests/integration/test_plan_execute_flow.py tests/test_flow_state.py -q
```

**Step 4: Run full backend checks**

```bash
conda activate pythinker && cd /Users/panda/Desktop/Projects/Pythinker/backend && ruff check . && ruff format --check . && pytest tests/
```

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(backend): remove legacy-flow flow implementation and dependencies"
```

---

### Task 10: End-to-End Verification and Rollout

**Files:**
- Create: `docs/reports/2026-02-10-design-standardization-rollout-report.md`
- Modify: `frontend/README.md`
- Modify: `backend/README.md`

**Step 1: Frontend verification**

```bash
cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run lint && bun run type-check
```

**Step 2: Backend verification**

```bash
conda activate pythinker && cd /Users/panda/Desktop/Projects/Pythinker/backend && ruff check . && ruff format --check . && pytest tests/
```

**Step 3: Manual UX checklist**

- Desktop + mobile:
  - Home page theme consistency
  - Chat planning/streaming indicator
  - Tool panel states
  - Deep/wide/phased research transitions
  - Session history/replay visuals

**Step 4: Rollout report**

- Record before/after metrics:
  - hard-coded color literal count
  - token coverage
  - research flow completion rate
  - Legacy Flow usage count (should be 0 before removal)

**Step 5: Commit docs**

```bash
git add docs/reports/2026-02-10-design-standardization-rollout-report.md frontend/README.md backend/README.md
git commit -m "docs: publish design standardization and flow simplification rollout report"
```

---

## Recommended Execution Order

1. Task 0
2. Task 1
3. Task 2
4. Task 3
5. Task 5
6. Task 6
7. Task 7
8. Task 4
9. Task 8
10. Task 9 (only after Gate A)
11. Task 10

---

## “Next” Recommendation

If you want the fastest value with lowest risk, execute this subset first:
1. Task 1 (token foundation fix)
2. Task 2 (priority surface standardization)
3. Task 5 (stream phase schema fix)
4. Task 6 (deep research orchestration unification)

Then decide on Legacy Flow removal after one week of flow telemetry.

---

**Plan complete and saved to `docs/plans/2026-02-10-design-standardization-and-legacy-flow-deprecation-plan.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration.

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints.

**Which approach?**
