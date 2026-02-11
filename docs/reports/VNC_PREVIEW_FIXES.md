# VNC Preview & Timeline Replay Remediation Plan (Context7 Validated)

**Date**: 2026-02-11  
**Status**: 🟡 In Progress (plan revised, implementation not started)  
**Priority**: P0/P1 fixes for session-end UX and replay integrity

---

## Executive Summary

This revised plan corrects multiple technical gaps in the prior draft and aligns fixes with:

- Current repository behavior (frontend replay pipeline, backend screenshot ordering, existing metrics API)
- Context7-validated guidance for Vue Composition API, Prometheus client usage, and async test structure
- Low-regression, testable implementation patterns

Top corrections vs previous draft:

1. Do **not** fetch final screenshot inside `VncMiniPreview.vue`; reuse existing replay pipeline from `useScreenshotReplay`.
2. Do **not** use `limit=1&offset=0` for final screenshot; backend returns screenshots in ascending `sequence_number`, so that returns the **first** frame.
3. Do **not** add Prometheus metrics with incompatible constructor/signature; this codebase uses custom metrics classes with `(name, help_text, labels)` and `.inc({...})`.
4. Keep `computed` pure; move async/side-effect logic to `watch`/composables.
5. Add jitter via a deterministic utility function (testable with injected RNG), not inline randomness that is hard to verify.

---

## Validated Findings (Code-Backed)

## 1) VNC mini preview drops to generic state at session end

**Evidence**: `frontend/src/components/VncMiniPreview.vue:235` gates live VNC on `effectiveToolContent`. After completion, tool context clears, so `shouldShowLiveVnc` returns `false`.

```ts
if (!effectiveToolContent.value) {
  return false;
}
```

**Impact**: Thumbnail regresses to generic "Initializing"/tool fallback instead of final meaningful visual state.

## 2) SESSION_END capture reliability is weakly observable

**Evidence**: `backend/app/domain/services/agent_task_runner.py:1458` captures `SESSION_END`, but failures are only debug-logged in cleanup path.

**Impact**: Real failures can be missed operationally; replay may miss a final frame without clear alerting.

## 3) Periodic screenshots miss tool metadata

**Evidence**: `backend/app/application/services/screenshot_service.py:355` periodic loop calls:

```py
await self.capture(ScreenshotTrigger.PERIODIC)
```

No current tool context is attached unless explicitly passed.

**Impact**: Timeline frames are hard to interpret (poor replay semantics).

## 4) Previous draft’s final screenshot retrieval logic was incorrect

**Evidence**:

- `backend/app/infrastructure/repositories/mongo_screenshot_repository.py` sorts `+sequence_number` (ascending).
- `GET /sessions/{id}/screenshots?limit=1&offset=0` returns earliest screenshot, not final.

## 5) WebSocket reconnect currently uses deterministic exponential backoff only

**Evidence**: `frontend/src/components/SandboxViewer.vue:260`

```ts
const delay = Math.min(1000 * Math.pow(2, connectionAttempts), 10000)
```

**Impact**: synchronized reconnect bursts possible under shared failures.

---

## Context7 Validation Applied

| Area | Context7 Source | Applied Decision |
|---|---|---|
| Vue Composition API (`computed`, `watch`, cleanup) | `/vuejs/docs` (`computed.md`, `watchers.md`, `reactivity-core.md`) | Keep `computed` side-effect free. Use `watch`/composable for async and cleanup logic. |
| Prometheus Python client labels/counters | `/prometheus/client_python` (`instrumenting/labels.md`) | Use stable, low-cardinality labels only; increment counters with label maps/values, avoid per-session/per-tool-call labels. |
| Async test execution model | `/pytest-dev/pytest-asyncio` (`concepts.md`) | Keep async tests explicit (`@pytest.mark.asyncio`), deterministic, and isolated. |

---

## Remediation Plan

## P0-A: Correct session-end thumbnail behavior without duplicate data fetching

**Goal**: At session completion, thumbnail shows replay/final frame (or meaningful fallback), not generic initializing state.

### Design

1. Reuse existing replay state from `ChatPage` (`useScreenshotReplay`) instead of introducing API calls inside `VncMiniPreview`.
2. Pass replay completion/frame props through `TaskProgressBar` to `VncMiniPreview`.
3. Update display precedence in `VncMiniPreview`:
   - Initializing / specialized preview states
   - Active live VNC (during active tool execution)
   - Completed replay frame (session ended + replay frame available)
   - Generic fallback
4. Update initializing-dot logic to not display "Initializing" when session is ended.

### Files

- `frontend/src/pages/ChatPage.vue`
- `frontend/src/components/TaskProgressBar.vue`
- `frontend/src/components/VncMiniPreview.vue`
- `frontend/tests/components/VncMiniPreview.spec.ts`

### Acceptance Criteria

- Completed session with replay data: thumbnail shows screenshot frame, not generic initializing state.
- Active session with active visual tool: live VNC still shown.
- No additional screenshot list API calls are made from `VncMiniPreview`.

---

## P0-B: Harden SESSION_END capture and observability

**Goal**: Final screenshot capture failure is explicit, measurable, and test-covered.

### Design

1. Keep cleanup order deterministic:
   - stop periodic loop
   - attempt `SESSION_END` capture
   - then sandbox destruction
2. Upgrade failure logging at capture callsite to `warning` with structured context + stack trace.
3. Treat `capture(...) == None` as failure signal (not just exceptions).
4. Use existing metric family already emitted by `record_screenshot_capture`:
   - `pythinker_screenshot_captures_total{trigger="session_end",status="success|error"}`
   No redundant custom metric unless a genuine gap remains.

### Files

- `backend/app/domain/services/agent_task_runner.py`
- `backend/tests/domain/services/test_agent_task_runner_cleanup.py`
- `backend/tests/application/services/test_screenshot_service_metrics.py`

### Acceptance Criteria

- Cleanup path logs warning on any SESSION_END failure/None result.
- Session-end success/error visible in existing metrics.
- Tests assert capture attempted during destroy and warning behavior on failure.

---

## P1-A: Add tool context enrichment for periodic screenshots (race-safe)

**Goal**: Periodic screenshots carry meaningful tool metadata when a visual tool is active.

### Design

1. Add explicit context tracking in screenshot service:
   - `set_tool_context(...)`
   - `clear_tool_context(tool_call_id)` (clear only matching active context)
2. In runner tool lifecycle:
   - set context on `CALLING` for visual tools
   - clear context on `CALLED`/finalization for that same tool call id
3. For periodic captures, merge current context snapshot when present.
4. Keep metric labels low-cardinality; if context coverage metric is added, use boolean labels only.

### Files

- `backend/app/application/services/screenshot_service.py`
- `backend/app/domain/services/agent_task_runner.py`
- `backend/tests/application/services/test_screenshot_service_metrics.py`

### Acceptance Criteria

- Periodic screenshots captured during active visual tool include `tool_name`/`function_name`.
- Context is cleared correctly after tool completion.
- No high-cardinality metric labels introduced.

---

## P2-A: Add jittered reconnect backoff with deterministic tests

**Goal**: Reduce synchronized reconnect spikes while keeping behavior testable.

### Design

1. Extract reconnect delay logic into utility, e.g. `frontend/src/utils/reconnectBackoff.ts`.
2. Use capped exponential + jitter (recommend full jitter).
3. Inject RNG (`rng: () => number`) for deterministic unit tests.
4. Keep non-retryable close code/reason checks unchanged.

### Files

- `frontend/src/components/SandboxViewer.vue`
- `frontend/src/utils/reconnectBackoff.ts` (new)
- `frontend/tests/utils/reconnectBackoff.spec.ts` (new)

### Acceptance Criteria

- Delay remains bounded `[min_delay, max_delay]`.
- Delay distribution varies for same attempt index.
- Unit tests deterministic via mocked RNG.

---

## Implementation Order

1. P0-A (thumbnail/replay wiring)
2. P0-B (SESSION_END reliability/observability)
3. P1-A (periodic context enrichment)
4. P2-A (reconnect jitter utility)

---

## Verification Checklist

## Frontend

- [ ] `frontend/tests/components/VncMiniPreview.spec.ts` updated for completion/replay behavior
- [ ] jitter/backoff utility tests added and passing
- [ ] `cd frontend && bun run lint && bun run type-check`

## Backend

- [ ] cleanup tests cover session-end capture success/failure paths
- [ ] periodic context enrichment tests pass
- [ ] `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`

---

## Observability Queries (Post-Implementation)

```promql
# SESSION_END success ratio
sum(rate(pythinker_screenshot_captures_total{trigger="session_end",status="success"}[5m]))
/
clamp_min(sum(rate(pythinker_screenshot_captures_total{trigger="session_end"}[5m])), 1)

# Periodic capture success ratio
sum(rate(pythinker_screenshot_captures_total{trigger="periodic",status="success"}[5m]))
/
clamp_min(sum(rate(pythinker_screenshot_captures_total{trigger="periodic"}[5m])), 1)
```

If a new context-coverage metric is added (optional), track:

```promql
sum(rate(pythinker_screenshot_periodic_context_total{has_context="true"}[5m]))
/
clamp_min(sum(rate(pythinker_screenshot_periodic_context_total[5m])), 1)
```

---

## Rollback Strategy

1. Revert reconnect utility adoption in `SandboxViewer.vue` only (isolated change).
2. Revert periodic tool-context enrichment if metadata regression appears.
3. Keep SESSION_END warning/metrics changes unless they cause log noise issues.
4. Revert thumbnail replay wiring if it causes unexpected panel interactions.

---

## Status Tracking

| Workstream | Status |
|---|---|
| Plan review and correction | **Completed** |
| Context7 validation pass | **Completed** |
| Code implementation | **Not Started** |
| Automated verification run | **Not Started** |

---

## References

- Vue Watchers / Reactivity Core (watch cleanup, side effects): https://vuejs.org/guide/essentials/watchers.html
- Vue Computed (derived state): https://vuejs.org/guide/essentials/computed.html
- Prometheus Python client labels/counters: https://github.com/prometheus/client_python/blob/master/docs/content/instrumenting/labels.md
- pytest-asyncio concepts: https://pytest-asyncio.readthedocs.io/en/latest/concepts.html

---

## Document History

| Date | Author | Changes |
|---|---|---|
| 2026-02-11 | Agent Analysis | Initial issue identification and fix plan |
| 2026-02-11 | Codex Review | Context7-validated rewrite with corrected architecture, metrics, and verification gates |
