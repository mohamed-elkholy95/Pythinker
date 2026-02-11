# Streaming Text Standardization Plan (Main VNC + Mini VNC + Tool Views)

**Date**: 2026-02-11  
**Status**: In Progress (implementation and automated verification complete; manual parity validation pending)  
**Priority**: P0 (UI consistency and session-state correctness)

---

## 1) Executive Summary

This plan standardizes how streaming status and streaming text are represented across:

- Main tool panel (`ToolPanelContent`)
- Mini VNC preview (`VncMiniPreview`)
- Progress bar summary line (`TaskProgressBar`)
- Tool views (terminal/editor/search/report)

Current behavior is inconsistent because each surface derives streaming status independently. The fix is to establish one shared streaming presentation model and make all UI surfaces render from it using a single precedence matrix.

---

## 2) Problem Statement

### User-visible issues

1. Different surfaces show different status at the same time (for the same session state).
2. Mini preview may keep showing terminal/editor/search context while main panel is in summary streaming.
3. Fallback labels are hardcoded in one surface and tool-standardized in another.
4. Session-end/replay states and summary states are not always resolved consistently in top labels.

### Root cause

Streaming state is partially centralized in `ChatPage`, but interpretation and rendering are fragmented:

- `ChatPage` accumulates `summaryStreamText` and flags (`isSummaryStreaming`, `isThinkingStreaming`).
- `ToolPanelContent` uses one set of conditions and labels.
- `VncMiniPreview` uses a different ordering and hardcoded text.
- `TaskProgressBar` creates separate preview text/status heuristics.

---

## 3) Investigation Evidence

## 3.1 Frontend state handling and propagation

- Stream processing in `frontend/src/pages/ChatPage.vue:1214`:
  - `phase === "summarizing"` updates `isSummaryStreaming` and `summaryStreamText`.
  - Other phases default to thinking stream handling.
- `TaskProgressBar` receives only summary boolean today (`frontend/src/pages/ChatPage.vue:192`), not summary text.
- `ToolPanel` receives both `summaryStreamText` and `isSummaryStreaming` (`frontend/src/pages/ChatPage.vue:223`).

## 3.2 Divergent rendering precedence

- Main panel summary priority:
  - `StreamingReportView` renders first when summary stream is active or buffered (`frontend/src/components/ToolPanelContent.vue:87`).
- Mini preview summary priority:
  - Summary branch is below terminal/search/editor branches (`frontend/src/components/VncMiniPreview.vue:38`, `frontend/src/components/VncMiniPreview.vue:64`, `frontend/src/components/VncMiniPreview.vue:108`, `frontend/src/components/VncMiniPreview.vue:124`).

## 3.3 Duplicated heuristics

- Mini fallback label logic uses hardcoded mappings (`frontend/src/components/VncMiniPreview.vue:383`).
- Progress bar computes its own content-preview extraction (`frontend/src/components/TaskProgressBar.vue:456`).
- Main panel computes terminal/editor/search content separately (`frontend/src/components/ToolPanelContent.vue:510`).

## 3.4 Runtime evidence

Mongo session inspection shows long summarizing streams after tool calls stop:

- Session `946d54ace1c44d3b`: `STREAM_COUNTS {"summarizing":785}`.
- For recent sessions, summarizing starts after last tool event and no tool events follow summary start.

This validates that UI must prioritize stream phase over stale last-tool context.

---

## 4) Context7 Validation Applied

Validated references:

- **Vue 3 docs** (`/vuejs/docs`):
  - Keep `computed` pure (no side effects).
  - Use `watch`/`watchEffect` for side effects and async work.
  - Centralize reusable reactive logic in composables.
- **VueUse docs** (`/vueuse/vueuse`):
  - `createSharedComposable` reuses existing state and avoids duplicate listeners across component consumers.
  - `useDebounceFn` supports debounced updates with optional `maxWait`.
- **Vitest docs** (`/vitest-dev/vitest`):
  - Deterministic timer/state tests with `vi.useFakeTimers`.
  - Stable module mocks with `vi.mock`.
  - Controlled async update assertions.
- **Pinia docs** (`/vuejs/pinia`):
  - `defineStore` setup stores are valid for complex shared state.
  - Best treated as a scaling path when composable complexity grows.

Plan decisions directly follow these constraints.

---

## 5) Target Standard (Single Source of Truth)

## 5.1 Canonical streaming presentation model

Introduce a single composable state model consumed by all surfaces:

```ts
type StreamPhase = "idle" | "thinking" | "summarizing" | "summary_final";
type StreamingViewType = "vnc" | "terminal" | "editor" | "search" | "generic" | "report";

interface StreamingPresentationState {
  phase: StreamPhase;
  isStreaming: boolean;
  headline: string;         // example: "Pythinker is composing a report"
  subtitle: string;         // example: "Streaming live"
  toolDisplayName: string;  // standardized from getToolDisplay
  toolDescription: string;  // standardized from getToolDisplay
  viewType: StreamingViewType;
  previewText: string;
  showReplayFrame: boolean;
  lastUpdatedAt: number;
  updateCount: number;
  previousPhase: StreamPhase | null;
}
```

## 5.2 Canonical precedence matrix

Every surface must apply this same order:

1. `isInitializing`
2. `phase === "summarizing"` or buffered summary text exists
3. wide-research specialized state
4. active tool state (terminal/editor/search/vnc/generic)
5. session completed with replay frame
6. generic fallback

## 5.2.1 Valid phase transitions

| From | Valid To |
|------|----------|
| `idle` | `thinking`, `summarizing` |
| `thinking` | `summarizing`, `idle` |
| `summarizing` | `summary_final`, `idle` |
| `summary_final` | `idle` |

Invalid transitions are logged and ignored (no state mutation).

## 5.3 Canonical copy and labels

Use one set of strings for all surfaces:

- `thinking`: `Thinking`
- `summarizing_active`: `Composing report...`
- `summarizing_final`: `Report complete`
- `tool`: `Pythinker is using {tool} | {description}`
- `completed`: `Session complete`
- `initializing`: `Initializing`

## 5.3.1 Reactivity discipline

- `computed()`: pure derivation only; no async, no mutations, no DOM access.
- `watchEffect()`: side effects only (analytics, sync, stale-state recovery checks).
- `watch()`: targeted transitions when old/new value access is required.

## 5.4 State-sharing strategy

Primary implementation keeps `ChatPage` as the authoritative source and passes normalized state to child surfaces.  
`createSharedComposable` is optional and only used for zero-argument local shared helpers; it is **not** used to hold session-specific mutable state to avoid cross-session leakage.

## 5.5 High-frequency update strategy

For streaming text, prefer frame-batched or throttled updates to preserve progressive rendering.  
`useDebounceFn` is allowed for non-critical UI metadata updates, but not for core token display paths where debounce may hide intermediate chunks.

---

## 6) Implementation Plan

## Phase P0: Foundation (shared model and constants)

### Changes

1. Add `frontend/src/composables/useStreamingPresentationState.ts`.
2. Add `frontend/src/constants/streamingPresentation.ts`.
3. Add shared preview formatting utility `frontend/src/utils/toolPreviewFormatter.ts`.
4. Add phase transition guard in `useStreamingPresentationState` (`VALID_TRANSITIONS` + guarded `setPhase`).
5. Add safe reset hook for inconsistent state (`resetToSafeState`) and stale-stream guard.
6. Add frame-batched update helper for high-frequency preview text updates.

### Dependencies

- No new dependency required for this phase (`@vueuse/core` already exists in `frontend/package.json`).

### Design rules

- All derived labels/states come from this composable.
- No async side effects in computed getters.
- Pure formatting functions for deterministic tests.
- Session-specific state remains prop-driven from `ChatPage` into child surfaces.

### Acceptance criteria

- One exported typed state model exists and is consumed by UI surfaces.
- No hardcoded fallback stream labels remain in surface components.
- Invalid phase transitions do not mutate state.
- Stale-state recovery path is explicit and test-covered.

---

## Phase P1: Wire model into all UI surfaces

### Changes

1. Update `frontend/src/pages/ChatPage.vue`:
   - Pass both `isSummaryStreaming` and `summaryStreamText` to `TaskProgressBar`.
2. Update `frontend/src/components/TaskProgressBar.vue`:
   - Remove local status heuristics for summary/thinking/tool label composition.
   - Use shared streaming presentation state for collapsed line and mini-preview props.
3. Update `frontend/src/components/VncMiniPreview.vue`:
   - Replace local precedence and `toolLabel` heuristics with shared model.
   - Ensure summary streaming branch has higher priority than stale content-preview branches.
4. Update `frontend/src/components/ToolPanelContent.vue`:
   - Use shared model for activity bar headline/subtitle.
   - Keep existing content view components but align visibility decisions with shared precedence.

### Acceptance criteria

- Main panel top label and mini preview top status always match for same state.
- During summarizing:
  - Main panel shows streaming report.
  - Mini preview reflects composing/report-complete state, not stale terminal/search/editor state.
- Session complete behavior remains replay-first when summary stream is not active.

---

## Phase P2: Cleanup and consistency hardening

### Changes

1. Remove duplicated preview extraction code paths where replaced by shared formatter.
2. Remove dead status strings and redundant computed branches.
3. Ensure all stream labels use centralized constants.

### Acceptance criteria

- No duplicate status-mapping logic across `ToolPanelContent`, `TaskProgressBar`, `VncMiniPreview`.
- Status text/copy is fully centralized.

---

## Phase P3: Test coverage and verification

### New/updated tests

1. `frontend/tests/composables/useStreamingPresentationState.spec.ts` (new)
   - Precedence matrix tests.
   - Label selection tests.
   - Transition guard tests (valid/invalid).
   - Stale recovery tests with fake timers.
   - Frame-batched update behavior tests.
2. `frontend/tests/components/VncMiniPreview.spec.ts` (update)
   - Summary priority over terminal/editor/search previews.
   - Session complete replay rendering.
3. `frontend/tests/components/TaskProgressBar.spec.ts` (update)
   - Collapsed status text parity with shared state.
4. `frontend/tests/components/ToolPanelContent.spec.ts` (new)
   - Activity bar parity with mini state.
   - Summary streaming branch correctness.

### Acceptance criteria

- Tests enforce parity across surfaces.
- Streaming precedence regressions are caught automatically.
- Timer-based behaviors are deterministic via `vi.useFakeTimers()`.

---

## 7) File-Level Change Plan

## New files

- `frontend/src/composables/useStreamingPresentationState.ts`
- `frontend/src/constants/streamingPresentation.ts`
- `frontend/src/utils/toolPreviewFormatter.ts`
- `frontend/tests/composables/useStreamingPresentationState.spec.ts`
- `frontend/tests/components/ToolPanelContent.spec.ts`

## Modified files

- `frontend/src/pages/ChatPage.vue`
- `frontend/src/components/TaskProgressBar.vue`
- `frontend/src/components/VncMiniPreview.vue`
- `frontend/src/components/ToolPanelContent.vue`
- `frontend/tests/components/VncMiniPreview.spec.ts`
- `frontend/tests/components/TaskProgressBar.spec.ts`

---

## 8) Verification Plan

Run in order:

1. `cd frontend && bun run lint`
2. `cd frontend && bun run type-check`
3. `cd frontend && bun run test`

Manual validation scenarios:

1. Active browser tool -> main + mini show same tool/action label.
2. Active terminal tool with no output -> both surfaces stay synchronized.
3. Summary streaming in progress -> both surfaces show composing status; main content is stream view.
4. Summary final chunk before report event -> both surfaces show report-complete state.
5. Session complete replay -> both surfaces settle to completion/replay behavior consistently.

---

## 9) Risks and Mitigations

1. **Risk**: Breaking existing mini preview specialized visuals.
   - **Mitigation**: Preserve specialized render components; only unify status and precedence.
2. **Risk**: Regressions from moving duplicated logic into shared composable.
   - **Mitigation**: Add composable-level tests first, then adopt incrementally.
3. **Risk**: Replay and summary state overlap bugs.
   - **Mitigation**: Explicit precedence matrix tests for edge transitions.
4. **Risk**: False-positive stale reset during long but valid generation pauses.
   - **Mitigation**: Gate stale reset by stream phase + connection/session status and verify with timeout tests.

---

## 10) Rollback Strategy

1. Revert `VncMiniPreview` to previous branch order if critical preview regression occurs.
2. Keep shared constants/composable in place (safe) and selectively rewire components back one by one.
3. Maintain test additions; use failing tests to guide controlled re-introduction.

---

## 11) Completion Checklist (Current Status)

- [x] P0 foundation created
- [x] P1 wiring completed in all surfaces
- [x] P2 duplication cleanup completed
- [x] P3 tests implemented and passing
- [x] lint/type-check/tests green (frontend)
- [ ] manual parity validation completed

---

## 12) Suggestion Review Outcome

| Suggestion | Decision | Notes |
|-----------|----------|-------|
| `createSharedComposable` for shared state | **Modified** | Use only for zero-arg helper sharing. Keep session stream state prop-driven from `ChatPage` to avoid global cross-session coupling. |
| Explicit computed/watch/watchEffect rules | **Accepted** | Added reactivity-discipline section and enforcement rules. |
| Transition guards | **Accepted** | Added valid transition matrix + guard requirement. |
| Debouncing rapid updates | **Modified** | Use frame-batched/throttled path for core streaming text; debounce allowed for non-critical metadata only. |
| Concrete fake-timer tests | **Accepted** | Added deterministic timer-based tests in Phase P3. |
| Pinia as alternative | **Deferred** | Keep composable approach now; note Pinia as scale-up option if state complexity grows. |
| Inconsistent-state recovery | **Accepted (guarded)** | Added safe reset + stale-state detection with explicit false-positive mitigation. |
