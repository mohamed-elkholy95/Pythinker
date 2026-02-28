# Chat Session Robustness Enhancement Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate session route hijacking, stale live-view state after completion, and session history status lag while fixing form accessibility warnings in the same flow.

**Architecture:** Introduce a session-scoped restore/resume controller in `ChatPage.vue` that treats route session ID as immutable input, not mutable shared state. Centralize terminal-session UI finalization so all completion paths converge to one behavior contract, then align live-view active-state rendering to connection phase + tool status. Reuse the existing session list SSE pipeline pattern from `LeftPanel.vue` in `SessionHistoryPage.vue` for real-time accuracy.

**Tech Stack:** Vue 3.5, Vue Router 4, Pinia, Vite, TypeScript, SSE/EventSource.

---

## Scope and Current Evidence (Actual Code Base)

### Finding A (High): Explicit `/chat/:sessionId` can be overridden during restore/resume

**Observed runtime evidence:** instrumented tab started at `/chat/36f3404cbf854115`, then emitted `pushState` to `/chat/21f4626b54ab4145` while `[RESTORE] ... running` + `[RESTORE] No stop flag, auto-resuming session` were logged.

**Code hotspots:**
- `restoreSession()` performs async calls and resumes via `await chat()` using shared mutable `sessionId.value`:
  - `frontend/src/pages/ChatPage.vue:3714`
  - `frontend/src/pages/ChatPage.vue:3809`
- `onBeforeRouteUpdate()` triggers `restoreSession()` without awaiting completion:
  - `frontend/src/pages/ChatPage.vue:3823`
  - `frontend/src/pages/ChatPage.vue:3862`

**Codebase-Specific Findings (Enhancement):**
- `onBeforeRouteUpdate` (line 3823) uses the **Vue Router 3 callback API** (`next()` parameter). Vue Router 4's composition API `onBeforeRouteUpdate` uses **return values** (`return false` to cancel, `return '/path'` to redirect). The `next()` callback still works but is deprecated — this is a migration opportunity. See [Vue Router 4 Composition API Guards](https://router.vuejs.org/guide/advanced/composition-api.html).
- `restoreSession()` (line 3714) takes **zero parameters** — it reads directly from shared `sessionId.value`. This is the root cause: any concurrent mutation of `sessionId.value` (by another route update or session create) silently redirects the restore.
- `resetState()` (called at line 3858 before `restoreSession`) cancels the current chat via `cancelCurrentChat.value()` but does **not** abort the in-flight `restoreSession` promise chain — the old restore can continue executing past `await` points.
- The `chat()` function (line ~3604) also reads from `sessionId.value` when building the SSE request, meaning a stale restore that calls `await chat()` will open an SSE stream for whichever session ID happens to be current, not the one the restore was initiated for.

### Finding B (Medium): Live-view can remain stale after session completed

**Observed runtime evidence:** backend status endpoint reported `completed`, composer stop controls were gone, but panel still showed stale tool details and `Waiting for result...`.

**Code hotspots:**
- `handleDoneEvent()` marks session completed but does not normalize in-flight tool state:
  - `frontend/src/pages/ChatPage.vue:3289`
- Tool panel active state is status-driven (`calling/running`) and not fully terminal-phase-gated:
  - `frontend/src/components/ToolPanelContent.vue:809`
  - `frontend/src/components/ToolPanelContent.vue:414`

**Codebase-Specific Findings (Enhancement):**
- `handleDoneEvent()` (line 3289) transitions to `'completing'` which auto-settles to `'settled'` after 300ms (via `useResponsePhase.ts:69-75`). However, during that 300ms window, `isActiveOperation` in `ToolPanelContent.vue:809` still evaluates `toolStatus === 'calling' || 'running'` as true for any tool whose status wasn't explicitly reset — **the 300ms settle timer and the tool status are decoupled**.
- `toolTimeline` (line 748 in ChatPage.vue state) accumulates `ToolContent` entries but `handleDoneEvent` never walks the timeline to finalize incomplete tools. A tool with `status: 'calling'` stays `'calling'` indefinitely.
- `showLiveViewSkeleton` (ToolPanelContent.vue:818) depends on `isActiveOperation` AND `props.live` — but `props.live` is set by the parent based on whether the SSE stream is active, which can persist through the `completing` → `settled` transition.
- The `isSessionComplete` computed in ChatPage.vue checks `sessionStatus.value` but `ToolPanelContent` receives `toolContent.status` from the parent — these are two separate signals with no synchronization contract.

### Finding C (Medium): Session History status can lag

**Observed runtime evidence:** `/chat/history` showed stale `Completed` while backend status endpoint returned `running`.

**Code hotspots:**
- Session history does a one-time fetch only (`onMounted -> loadSessions`) and no real-time subscription:
  - `frontend/src/pages/SessionHistoryPage.vue:142`
  - `frontend/src/pages/SessionHistoryPage.vue:210`
- Real-time list behavior already exists in left panel via SSE:
  - `frontend/src/components/LeftPanel.vue:337`

**Codebase-Specific Findings (Enhancement):**
- `SessionHistoryPage.vue:210` calls `loadSessions()` once in `onMounted()` — no SSE subscription, no polling fallback, no `useSessionStatus()` integration.
- `useSessionStatus.ts` already exists as a cross-component event emitter for session status changes. `ChatPage.vue` calls `emitStatusChange()` when sessions complete (line 3306). However, `SessionHistoryPage.vue` **does not subscribe** to this composable — this is a quick win that should be wired before extracting the SSE feed composable.
- `LeftPanel.vue:343` uses `getSessionsSSE()` from `api/agent.ts:57` which wraps `createSSEConnection`. The SSE connection is managed by a `cancelGetSessionsSSE` ref and properly cleaned up. This pattern is ready for extraction.
- `getSessionsSSE` uses `POST /sessions` with SSE transport — the same endpoint as `getSessions()` (`GET /sessions`), so the data shape (`ListSessionResponse`) is identical. The composable can serve both consumers.

### Finding D (Low): Repeated `id/name` form warning

**Observed runtime evidence:** console issue `A form field element should have an id or name attribute`.

**Code hotspots (examples):**
- `frontend/src/components/settings/AgentSettings.vue:27`
- `frontend/src/components/settings/ModelSettings.vue:96`
- `frontend/src/components/connectors/CustomApiForm.vue:5`
- `frontend/src/components/connectors/CustomMcpForm.vue:5`

**Codebase-Specific Findings (Enhancement):**
- Confirmed: `AgentSettings.vue:27-33` uses `<input type="range">` with `v-model.number` but no `id` or `name` attribute. Same pattern repeats across settings sliders and text inputs.
- The `<label>` elements use CSS-class-based visual association (`setting-label` class) but lack `for`/`id` binding — screen readers cannot associate labels with controls.

---

## External Best-Practice Validation (Official Sources — Context7 MCP Verified)

### 1. Vue Router 4 Composition API Guards

**Source:** Context7 `/vuejs/router` (Score: 92.6/100, 569 snippets)

**Key Finding:** Vue Router 4's `onBeforeRouteUpdate` does **not** use the `next()` callback pattern. Instead:
- Return `false` to cancel navigation
- Return a route location to redirect
- Return nothing (or `undefined`) to confirm
- Supports `async` functions natively — the router awaits the returned Promise

```typescript
// Vue Router 4 — CORRECT pattern
onBeforeRouteUpdate(async (to, from) => {
  if (to.params.id !== from.params.id) {
    userData.value = await fetchUser(to.params.id)
  }
})

// Vue Router 3 — DEPRECATED pattern (still works but should migrate)
onBeforeRouteUpdate(async (to, from, next) => {
  // ...
  next()
})
```

**Impact on Workstream 1:** The current `onBeforeRouteUpdate` (line 3823) should be migrated to return-value style. This removes the `next()` callback complexity and makes the guard properly await-able by the router.

### 2. Vue 3.5 Watcher Cleanup (`onWatcherCleanup`)

**Source:** Vue.js docs `vuejs.org/guide/essentials/watchers#side-effect-cleanup`

**Key Finding:** Vue 3.5+ provides `onWatcherCleanup()` for cancelling stale async operations. Must be called **synchronously** (before any `await`). The `onCleanup` third argument (pre-3.5 compat) is also available.

```typescript
watch(id, (newId) => {
  const controller = new AbortController()
  fetch(`/api/${newId}`, { signal: controller.signal }).then(/* ... */)
  onWatcherCleanup(() => controller.abort())
})
```

**Impact on Workstream 1:** The `AbortController` + `onWatcherCleanup` pattern is more idiomatic than a manual epoch counter for the restore guard. However, `restoreSession` is called from `onBeforeRouteUpdate` (not a watcher), so we need a **hybrid approach**: epoch token for the guard, AbortController for cancelling in-flight fetch calls within `restoreSession`.

### 3. Composable Best Practices

**Source:** Vue.js docs `vuejs.org/guide/reusability/composables`

**Key Conventions:**
- Naming: `useX` prefix (already followed in codebase)
- Return plain objects with `ref()` values (not `reactive()`) — enables destructuring
- Clean up side effects in `onUnmounted()` — **critical for SSE connections**
- Composables must be called synchronously in `<script setup>` or `setup()` — no conditional calls
- Accept `Ref | Getter | Raw` via `toValue()` for flexible input

**Impact on Workstream 3:** The `useSessionListFeed` composable must:
- Call `onUnmounted` to close SSE connections (prevent memory leaks)
- Return `ref`-based state (not reactive objects)
- Accept optional configuration via refs/getters

### 4. SSE/EventSource Reconnect Semantics

**Source:** WHATWG HTML Spec §9.2 (Server-sent events)

**Key Conventions:**
- Include `id:` field so browsers can resume via `Last-Event-ID` header
- Include `retry:` field to control reconnection interval
- 30s heartbeat prevents proxy timeouts (already implemented in codebase per CLAUDE.md)
- EventSource auto-reconnects on network errors but **not** on HTTP errors (4xx/5xx)

**Impact on Workstream 3:** The `useSessionListFeed` composable should implement:
- Fallback polling when SSE disconnects (EventSource's built-in reconnect may not cover all cases)
- `Last-Event-ID` forwarding if the backend supports it (the existing `getSessionsSSE` uses POST, so this needs custom header handling)

### 5. Form Accessibility (WCAG 2.0 H44, MDN)

**Source:** W3C WCAG Techniques H44, MDN `<input>` reference

**Key Requirements:**
- Every `<input>`, `<textarea>`, `<select>` must have a programmatically associated label
- `<label for="fieldId">` + `<input id="fieldId">` is the primary technique
- `name` attribute is required for form submission semantics
- For dynamically generated fields (v-for loops), use deterministic IDs (e.g., `${prefix}-${index}`)

---

## Implementation Workstreams

### Workstream 1: Route-Scoped Restore/Resume Hardening (Priority: P0)

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`
- Test: `frontend/src/composables/__tests__/useSessionStreamController.test.ts` (extend), add `frontend/src/composables/__tests__/chatRestoreGuards.test.ts` (new extraction target)

**Design:**

**1a. Migrate `onBeforeRouteUpdate` to Vue Router 4 return-value API:**
```typescript
// BEFORE (line 3823 — Vue Router 3 pattern):
onBeforeRouteUpdate(async (to, from, next) => {
  // ... logic ...
  next()
})

// AFTER (Vue Router 4 pattern):
onBeforeRouteUpdate(async (to, from) => {
  // ... logic ...
  // return false to cancel, return undefined to confirm
})
```
This removes the `next()` callback and makes the guard properly async. The router will await the returned Promise before confirming navigation.

**1b. Parameterize `restoreSession` with immutable target:**
```typescript
// BEFORE:
const restoreSession = async () => {
  if (!sessionId.value) { ... }          // reads shared mutable ref
  const session = await agentApi.getSession(sessionId.value) // could be stale
  // ... 100 lines of async work reading sessionId.value ...
  await chat()                            // chat() reads sessionId.value too
}

// AFTER:
const restoreSession = async (
  targetSessionId: string,
  context: 'mount' | 'route_update' | 'session_create'
) => {
  // All subsequent reads use targetSessionId, not sessionId.value
  const session = await agentApi.getSession(targetSessionId)
  // ...
}
```

**1c. Introduce restore epoch (generation token):**
```typescript
let restoreEpoch = 0

const restoreSession = async (targetSessionId: string, context: string) => {
  const epoch = ++restoreEpoch  // Atomically increment

  const session = await agentApi.getSession(targetSessionId)
  if (epoch !== restoreEpoch) return  // Stale — newer restore started

  // ... more async work ...
  const freshStatus = await agentApi.getSessionStatus(targetSessionId)
  if (epoch !== restoreEpoch) return  // Re-check after every await

  // Only auto-resume if this is still the active restore AND route matches
  if (epoch === restoreEpoch && targetSessionId === sessionId.value) {
    await chat('', [], { skipOptimistic: true })
  }
}
```

**1d. Guard the route update to prevent fire-and-forget:**
```typescript
onBeforeRouteUpdate(async (to, from) => {
  const nextSessionId = to.params.sessionId as string | undefined
  const prevSessionId = from.params.sessionId as string | undefined

  if (prevSessionId === nextSessionId) return  // Same session, no-op

  // Cancel any in-flight restore by bumping the epoch
  restoreEpoch++

  // Stop previous session if running
  if (prevSessionId && shouldStopSessionOnExit(sessionStatus.value)) {
    try {
      await agentApi.stopSession(prevSessionId)
      emitStatusChange(prevSessionId, SessionStatus.COMPLETED)
    } catch { /* non-critical */ }
  }

  // Reset UI state
  toolPanel.value?.clearContent()
  hideFilePanel()
  resetState()

  if (nextSessionId) {
    messages.value = []
    sessionId.value = nextSessionId
    // Await restore — router waits for this Promise
    await restoreSession(nextSessionId, 'route_update')
  }
  // Return undefined → confirm navigation
})
```

**1e. Apply same pattern to `onMounted`:**
```typescript
onMounted(async () => {
  // ... existing setup ...
  if (routeParams.sessionId && routeParams.sessionId !== 'new') {
    sessionId.value = String(routeParams.sessionId)
    await restoreSession(sessionId.value, 'mount')
  }
})
```

**Acceptance Criteria:**
- Reloading `/chat/<completed-id>` never navigates to another session automatically, even when another session is running.
- Route remains stable under rapid tab switches and repeated reloads.
- All epoch guards have corresponding `console.log('[RESTORE] Stale epoch detected, aborting')` for debuggability.

---

### Workstream 2: Terminal UI Finalization Contract (Priority: P0)

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`
- Modify: `frontend/src/components/ToolPanelContent.vue`
- Optional helper extraction: `frontend/src/utils/sessionFinalization.ts` (new)

**Design:**

**2a. Add centralized `finalizeSession()` function in ChatPage.vue:**
```typescript
/**
 * Single convergence point for all session completion paths.
 * Called by: handleDoneEvent, manual stop, status reconciliation, visibility reconciliation.
 */
const finalizeSession = (reason: 'done' | 'stop' | 'reconcile' | 'visibility') => {
  console.log('[FINALIZE]', reason, 'sessionId:', sessionId.value)

  // 1. Normalize tool timeline: finalize any tools still in transient states
  for (const tool of toolTimeline.value) {
    if (tool.status === 'calling' || tool.status === 'running') {
      tool.status = 'interrupted'  // New terminal status, not 'completed' (we don't have the result)
    }
  }

  // 2. Clear all transient UI state
  activeReasoningState.value = 'completed'
  follow.value = false
  planningProgress.value = null
  stopPlanningMessageCycle()
  isWaitingForReply.value = false
  clearTakeoverCta()
  dismissConnectionBanner()

  // 3. Phase transition
  transitionTo('completing')  // auto-settles to 'settled' after 300ms

  // 4. Status and cleanup
  if (sessionId.value) {
    emitStatusChange(sessionId.value, SessionStatus.COMPLETED)
    cleanupSessionStorage(sessionId.value)
  }
  sessionStatus.value = SessionStatus.COMPLETED
  receivedDoneEvent.value = true

  // 5. Load replay data
  replay.loadScreenshots()
}
```

**2b. Replace duplicated completion logic:**
- `handleDoneEvent()` → calls `finalizeSession('done')` + `ensureCompletionSuggestions()` + `markShortAssistantCompletion()`
- Manual stop handler → calls `finalizeSession('stop')`
- Visibility reconciliation (`watch(documentVisibility)`) → calls `finalizeSession('visibility')` when backend reports terminal status
- Status re-check in `restoreSession` → calls `finalizeSession('reconcile')`

**2c. Gate `ToolPanelContent` active indicators on session phase:**
```typescript
// ToolPanelContent.vue — ENHANCED isActiveOperation
const isActiveOperation = computed(() => {
  // Must be in a non-terminal tool status AND session must be actively streaming
  const isToolActive = toolStatus.value === 'calling' || toolStatus.value === 'running'
  // Gate on session-level phase via the `live` prop (which tracks SSE connection)
  return isToolActive && props.live
})
```

**2d. Add explicit terminal fallback for interrupted tools:**
```html
<!-- ToolPanelContent.vue — after existing result display -->
<div v-if="toolStatus === 'interrupted' && !toolContent?.content?.result"
     class="text-sm text-[var(--text-tertiary)] italic p-4">
  {{ $t('Tool execution was interrupted') }}
</div>
```

**2e. Add `'interrupted'` to ToolContent status type:**
```typescript
// types/message.ts or wherever ToolContent.status is defined
status?: 'calling' | 'running' | 'completed' | 'error' | 'interrupted'
```

**Acceptance Criteria:**
- No `Waiting for result...` panel after backend reports terminal status.
- No spinner/running labels after task completion unless a new run starts.
- `toolTimeline` entries with `status: 'interrupted'` show a clear "interrupted" indicator.

---

### Workstream 3: Session History Live Accuracy (Priority: P1)

**Files:**
- Add: `frontend/src/composables/useSessionListFeed.ts` (shared SSE list feed)
- Modify: `frontend/src/pages/SessionHistoryPage.vue`
- Modify: `frontend/src/components/LeftPanel.vue` (migrate to shared feed)

**Design:**

**3a. Extract `useSessionListFeed` composable:**
```typescript
// frontend/src/composables/useSessionListFeed.ts
import { ref, onMounted, onUnmounted } from 'vue'
import { getSessions, getSessionsSSE } from '@/api/agent'
import { useSessionStatus } from './useSessionStatus'
import type { SessionItem } from '@/types/response'

export function useSessionListFeed() {
  const sessions = ref<SessionItem[]>([])
  const isLoading = ref(false)
  const isConnected = ref(false)
  let cancelSSE: (() => void) | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null

  const { onStatusChange } = useSessionStatus()

  // Immediate status updates from ChatPage emitStatusChange()
  const unsubStatus = onStatusChange((sessionId, status) => {
    const session = sessions.value.find(s => s.session_id === sessionId)
    if (session) {
      session.status = status
    }
  })

  const fetchOnce = async () => { /* ... */ }

  const connectSSE = async () => {
    if (cancelSSE) { cancelSSE(); cancelSSE = null }
    try {
      cancelSSE = await getSessionsSSE({
        onOpen: () => { isConnected.value = true },
        onMessage: (event) => { sessions.value = event.data.sessions },
        onError: () => { isConnected.value = false; startFallbackPolling() },
        onClose: () => { isConnected.value = false },
      })
    } catch {
      await fetchOnce()  // Fallback to one-time fetch
    }
  }

  const startFallbackPolling = () => { /* 10s interval polling */ }
  const stopFallbackPolling = () => { /* clear interval */ }

  onMounted(() => { connectSSE() })
  onUnmounted(() => {
    if (cancelSSE) { cancelSSE(); cancelSSE = null }
    stopFallbackPolling()
    unsubStatus()  // Clean up status listener
  })

  return { sessions, isLoading, isConnected }
}
```

**Lifecycle compliance (per Vue composable best practices):**
- SSE connection opened in `onMounted`, closed in `onUnmounted`
- Returns `ref`-based state (not `reactive`) for safe destructuring
- Integrates `useSessionStatus()` for immediate cross-component updates
- Fallback polling prevents stale data when SSE is disconnected

**3b. Migrate `LeftPanel.vue` to shared composable:**
Replace the inline SSE management (lines 337-358) with:
```typescript
const { sessions, isConnected } = useSessionListFeed()
```
Preserve `mergeWithOptimisticSession()` as a local transform on top of the shared feed.

**3c. Wire `SessionHistoryPage.vue`:**
Replace `loadSessions()` (line 142) with:
```typescript
const { sessions: liveSessions, isLoading } = useSessionListFeed()

// Apply local filters on top of live data
const filteredSessions = computed(() => {
  let result = liveSessions.value
  if (searchQuery.value) { /* filter */ }
  if (statusFilter.value) { /* filter */ }
  return result
})
```

**3d. Integrate `useSessionStatus` for immediate updates (quick win):**
Even before the full SSE composable extraction, wire `SessionHistoryPage.vue` to subscribe to `useSessionStatus().onStatusChange()` so that status transitions from `ChatPage.vue` immediately reflect.

**Acceptance Criteria:**
- Status transitions in history update without manual refresh.
- History and sidebar agree with backend status within one SSE update window.
- `LeftPanel.vue` behavior is unchanged (regression test via snapshot comparison).

---

### Workstream 4: Form Accessibility Remediation + Guardrail (Priority: P2)

**Files:**
- Modify: `frontend/src/components/settings/AgentSettings.vue`
- Modify: `frontend/src/components/settings/ModelSettings.vue`
- Modify: `frontend/src/components/connectors/CustomApiForm.vue`
- Modify: `frontend/src/components/connectors/CustomMcpForm.vue`
- Add: `frontend/scripts/check-form-controls.sh`
- Modify: `frontend/package.json` (script hook)

**Design:**
- Ensure all `<input>`, `<textarea>`, `<select>` include stable `id` and `name`.
- Connect labels via `for`/`id`.
- For repeated key/value rows, generate deterministic ids (index-based).
- Add lightweight CI script that fails on missing `id|name` in targeted settings/connectors paths.

**Example fix pattern:**
```html
<!-- BEFORE (AgentSettings.vue:27) -->
<input type="range" :min="5" :max="100" :step="5"
       v-model.number="localSettings.browser_agent_max_steps"
       @change="saveSettings" class="settings-slider" />

<!-- AFTER -->
<input type="range" :min="5" :max="100" :step="5"
       id="agent-browser-max-steps"
       name="browser_agent_max_steps"
       v-model.number="localSettings.browser_agent_max_steps"
       @change="saveSettings" class="settings-slider" />
```

And in the label:
```html
<label for="agent-browser-max-steps" class="setting-label">{{ t('Browser Max Steps') }}</label>
```

**Acceptance Criteria:**
- Browser console no longer emits missing id/name warning in tested settings/connectors flows.
- Guard script prevents regression in modified paths.

---

## Detailed Task Sequence (Execution Order)

### Phase 1: Core Safety (P0 — Workstreams 1 & 2)

1. **Migrate `onBeforeRouteUpdate` to Vue Router 4 return-value API** — remove `next()` callback, use `async` return pattern.
2. **Parameterize `restoreSession(targetSessionId, context)`** and update all callsites (`onMounted:3913`, `onBeforeRouteUpdate:3862`, session-create flow).
3. **Add `restoreEpoch` generation token** with guard checks after each `await` in `restoreSession`.
4. **Await `restoreSession` in `onBeforeRouteUpdate`** so the router blocks navigation until restore completes (prevents race).
5. **Add `'interrupted'` tool status** to `ToolContent` type definition.
6. **Implement `finalizeSession()` convergence function** in ChatPage.vue.
7. **Replace duplicated completion-state mutations** in `handleDoneEvent`, stop handler, visibility reconciliation, and status re-check with `finalizeSession()`.
8. **Update `ToolPanelContent` `isActiveOperation` computed** to gate on `props.live` (session streaming state) in addition to tool status.
9. **Add interrupted-tool fallback UI** in `ToolPanelContent`.

### Phase 2: Live Data (P1 — Workstream 3)

10. **Quick win: Wire `SessionHistoryPage` to `useSessionStatus().onStatusChange()`** for immediate cross-component status updates (before full SSE extraction).
11. **Extract `useSessionListFeed` composable** from `LeftPanel.vue` SSE handling.
12. **Migrate `LeftPanel.vue` to `useSessionListFeed`** — preserve `mergeWithOptimisticSession` as local transform.
13. **Wire `SessionHistoryPage` to `useSessionListFeed`** — replace `loadSessions()` with live feed + local filters.
14. **Add fallback polling** in `useSessionListFeed` when SSE disconnects.

### Phase 3: Polish (P2 — Workstream 4)

15. Add `id`/`name` + `<label for>` fixes in settings/connectors forms.
16. Add form guard script and npm script entry.

### Phase 4: Verification

17. Add/extend unit tests for restore guard behavior and terminal-panel behavior.
18. Run lint/type-check/tests and execute manual validation matrix.

---

## Verification Plan

### Automated

Run:
- `cd frontend && bun run lint`
- `cd frontend && bun run type-check`
- `cd frontend && bun run test:run`

Expected:
- All pass.
- New restore/finalization tests pass and fail without the fix.

### Manual (Chrome DevTools MCP)

1. Start a long-running session in tab A (`/chat/<running>`).
2. Open completed session in tab B (`/chat/<completed>`) and reload repeatedly.
3. Confirm tab B URL never changes from explicit session.
4. Stop session in tab A and confirm:
   - composer is enabled,
   - tool panel shows terminal state (no stale waiting/running).
5. Open `/chat/history` in tab C and confirm status transitions without manual reload.
6. Open settings/connectors forms and verify no missing id/name console issues.

---

## Risks and Mitigations

1. **Risk:** Over-guarding could suppress legitimate resume behavior.
- Mitigation: route/session equality checks only block stale async continuations; add debug logs keyed by restore epoch. The epoch check is `epoch !== restoreEpoch` (not `targetSessionId !== sessionId.value`), so it only fires when a *newer* restore was initiated, not when the session ID is the same.

2. **Risk:** Vue Router 4 `next()` removal could break other guards in the chain.
- Mitigation: Audit all `onBeforeRouteUpdate`/`onBeforeRouteLeave` calls in the codebase. The `next()` callback is supported for backward compatibility in Vue Router 4 but mixing return-value and callback styles in the same guard is undefined behavior — ensure full migration.

3. **Risk:** Shared session feed extraction could regress sidebar behavior.
- Mitigation: Migrate `LeftPanel` first behind identical composable API and snapshot-compare payload mapping. The `mergeWithOptimisticSession` logic remains in `LeftPanel` as a local transform — the composable only provides the raw feed.

4. **Risk:** `finalizeSession()` called multiple times for the same session (e.g., done event + visibility reconciliation).
- Mitigation: Add idempotency guard: `if (receivedDoneEvent.value && sessionStatus.value === SessionStatus.COMPLETED) return` at the top of `finalizeSession()`.

5. **Risk:** Form-id guard script false positives on multiline templates.
- Mitigation: Scope to targeted directories and validate against current templates before enforcing in CI.

6. **Risk:** `'interrupted'` tool status breaks existing type checks.
- Mitigation: Add `'interrupted'` to the union type in `types/message.ts`. Audit all `switch/case` and conditional checks on `ToolContent.status` to handle the new variant (or treat it as a terminal state alongside `'completed'` and `'error'`).

---

## Status

- Workstream 1: Not Started
- Workstream 2: Not Started
- Workstream 3: Not Started
- Workstream 4: Not Started
- Automated verification: Not Started
- Manual verification: In Progress (root-cause reproductions completed; post-fix validation pending)
