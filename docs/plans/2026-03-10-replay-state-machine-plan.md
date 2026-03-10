# Replay State Machine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the split screenshot-matching (ChatPage) + blob-loading (composable) architecture with a unified target-driven replay state machine inside `useScreenshotReplay.ts`, fixing infinite loading, stale screenshots, and transition flash bugs.

**Architecture:** A `ReplayVisualState` enum (`idle | resolving | ready | fallback | error`) drives all UI rendering. The composable owns both matching and loading. ChatPage calls `selectTool(tool)` and reads `visualState` — it never mutates internal replay state. A `selectionVersion` counter invalidates stale async operations.

**Tech Stack:** Vue 3 Composition API, TypeScript strict mode, Vitest

**Design doc:** `docs/plans/2026-03-10-replay-state-machine-design.md`

---

### Task 1: Add ReplayVisualState type and selectTool matching logic to composable

**Files:**
- Modify: `frontend/src/composables/useScreenshotReplay.ts`

**Step 1: Add the type, new refs, and `ensureMetadataLoaded()`**

At the top of the file, add the type export and import ToolContent:

```typescript
import type { ToolContent } from '../types/message'
import { toEpochSeconds } from '../utils/time'

export type ReplayVisualState = 'idle' | 'resolving' | 'ready' | 'fallback' | 'error'
```

Inside `useScreenshotReplay()`, add new refs after line 8 (`isLoading`):

```typescript
const visualState = ref<ReplayVisualState>('idle')
const activeTool = ref<ToolContent | null>(null)
let selectionVersion = 0
let metadataLoaded = false
```

**Step 2: Add `ensureMetadataLoaded()`**

This replaces the auto-selecting behavior of `loadScreenshots()`. Add after the existing `loadScreenshots` function (line 175):

```typescript
async function ensureMetadataLoaded(): Promise<void> {
  if (metadataLoaded && screenshots.value.length > 0) return
  if (!sessionId.value) return
  isLoading.value = true
  try {
    const response = await apiClient.get<ApiResponse<ScreenshotListResponse>>(
      `/sessions/${sessionId.value}/screenshots`
    )
    screenshots.value = response.data.data.screenshots.filter(
      (s) => s.trigger !== 'session_end'
    )
    metadataLoaded = true
  } catch {
    screenshots.value = []
  } finally {
    isLoading.value = false
  }
}
```

**Step 3: Add `findScreenshotForTool()` (deterministic matching)**

Add this private function. It implements the 2 matching rules from the design (no global timestamp fallback):

```typescript
function findScreenshotForTool(tool: ToolContent): number {
  const allScreenshots = screenshots.value
  if (allScreenshots.length === 0) return -1

  const toolId = tool.tool_call_id
  const isSynthetic = toolId.startsWith('tool-progress:')
  const parentToolId = isSynthetic
    ? toolId.split(':').slice(1, -1).join(':')
    : toolId

  if (isSynthetic) {
    // Rule 2: synthetic entries — match within parent's screenshots by nearest timestamp
    const toolEpoch = toEpochSeconds(tool.timestamp as number | string)
    if (toolEpoch === null) return -1
    let bestIdx = -1
    let bestDiff = Infinity
    for (let i = 0; i < allScreenshots.length; i++) {
      if (allScreenshots[i].tool_call_id !== parentToolId) continue
      const ssEpoch = toEpochSeconds(allScreenshots[i].timestamp as number | string)
      if (ssEpoch === null) continue
      const diff = Math.abs(ssEpoch - toolEpoch)
      if (diff < bestDiff) {
        bestDiff = diff
        bestIdx = i
      }
    }
    return bestIdx
  }

  // Rule 1: exact tool_call_id match, prefer tool_after > tool_before > periodic
  let bestIdx = -1
  let bestPriority = -1
  const triggerPriority: Record<string, number> = {
    tool_after: 3,
    tool_before: 2,
    periodic: 1,
  }
  for (let i = 0; i < allScreenshots.length; i++) {
    if (allScreenshots[i].tool_call_id !== toolId) continue
    const priority = triggerPriority[allScreenshots[i].trigger] ?? 0
    if (priority > bestPriority) {
      bestPriority = priority
      bestIdx = i
    }
  }
  return bestIdx
}
```

**Step 4: Add `selectTool()` with the critical invariant**

```typescript
async function selectTool(tool: ToolContent): Promise<void> {
  // Critical invariant: synchronous state clear before any async work
  const version = ++selectionVersion
  currentBlobUrl.value = ''
  visualState.value = 'resolving'
  activeTool.value = tool

  await ensureMetadataLoaded()
  if (version !== selectionVersion) return // superseded

  const matchIdx = findScreenshotForTool(tool)
  if (matchIdx < 0) {
    visualState.value = 'fallback'
    currentIndex.value = -1
    return
  }

  currentIndex.value = matchIdx
  const screenshot = screenshots.value[matchIdx]

  const blobUrl = await getOrFetchBlobUrl(screenshot.id)
  if (version !== selectionVersion) return // superseded

  if (!blobUrl) {
    visualState.value = 'error'
    return
  }

  currentBlobUrl.value = blobUrl
  visualState.value = 'ready'

  // Prefetch adjacent frames for smooth timeline scrubbing
  void prefetchAhead(3)
  void prefetchBehind(2)
}
```

**Step 5: Add `clearSelection()` and `jumpToLatest()`**

```typescript
function clearSelection(): void {
  selectionVersion++
  visualState.value = 'idle'
  activeTool.value = null
  currentBlobUrl.value = ''
  currentIndex.value = -1
}

function jumpToLatest(): void {
  selectionVersion++
  if (screenshots.value.length > 0) {
    currentIndex.value = screenshots.value.length - 1
  }
  visualState.value = 'idle'
  activeTool.value = null
}
```

**Step 6: Update session-change watcher to reset new state**

Modify the existing `watch(sessionId, ...)` (currently line 144):

```typescript
watch(sessionId, (nextSessionId, previousSessionId) => {
  if (nextSessionId !== previousSessionId) {
    selectionVersion++
    renderRequestVersion++
    clearBlobCache()
    screenshots.value = []
    currentIndex.value = -1
    visualState.value = 'idle'
    activeTool.value = null
    metadataLoaded = false
  }
})
```

**Step 7: Modify existing `loadScreenshots()` to NOT auto-select**

Change lines 166-168 (inside `loadScreenshots`) from:

```typescript
if (screenshots.value.length > 0) {
  currentIndex.value = screenshots.value.length - 1
}
```

to:

```typescript
// Do NOT auto-select — callers use selectTool() or jumpToLatest() explicitly
metadataLoaded = true
```

**Step 8: Update return object**

Add new members to the return statement:

```typescript
return {
  screenshots,
  currentIndex,
  isLoading,
  currentScreenshot,
  currentScreenshotUrl,
  progress,
  canStepForward,
  canStepBackward,
  currentTimestamp,
  hasScreenshots,
  loadScreenshots,
  stepForward,
  stepBackward,
  seekByProgress,
  // New target-driven API
  visualState,
  activeTool,
  selectTool,
  clearSelection,
  jumpToLatest,
  ensureMetadataLoaded,
}
```

**Step 9: Verify TypeScript compiles**

Run: `cd frontend && bun run type-check`
Expected: PASS (no type errors)

**Step 10: Commit**

```bash
git add frontend/src/composables/useScreenshotReplay.ts
git commit -m "feat(replay): add target-driven state machine to useScreenshotReplay

Add ReplayVisualState type (idle|resolving|ready|fallback|error),
selectTool() with deterministic matching and stale-request
invalidation, ensureMetadataLoaded() without auto-selection."
```

---

### Task 2: Write tests for the replay state machine

**Files:**
- Create: `frontend/src/composables/__tests__/useScreenshotReplay.test.ts`

**Step 1: Write tests**

The composable uses `apiClient` for HTTP fetches and `onUnmounted` for cleanup. We need to mock the API and provide a reactive `sessionId` ref. Key scenarios:

```typescript
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { ref, nextTick } from 'vue'
import { useScreenshotReplay, type ReplayVisualState } from '../useScreenshotReplay'
import type { ToolContent } from '../../types/message'
import type { ScreenshotMetadata } from '../../types/screenshot'

// Mock apiClient — it's used by the composable for fetching screenshot list and blobs
vi.mock('../../api/client', () => ({
  apiClient: {
    get: vi.fn(),
  },
  // Re-export ApiResponse type stub (not used at runtime, only for generics)
}))

// Mock onUnmounted since we're testing outside a component lifecycle
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onUnmounted: vi.fn(), // no-op outside component
  }
})

import { apiClient } from '../../api/client'

const mockGet = apiClient.get as Mock

// ── Helpers ──────────────────────────────────────────────────────

function makeScreenshot(overrides: Partial<ScreenshotMetadata> & { id: string }): ScreenshotMetadata {
  return {
    session_id: 'session-1',
    sequence_number: 0,
    timestamp: 1710000000,
    trigger: 'tool_after',
    size_bytes: 1024,
    has_thumbnail: false,
    ...overrides,
  }
}

function makeTool(overrides: Partial<ToolContent> & { tool_call_id: string }): ToolContent {
  return {
    id: overrides.tool_call_id,
    event_id: 'evt-1',
    name: 'browser',
    function: 'browser_navigate',
    args: { url: 'https://example.com' },
    status: 'called',
    timestamp: 1710000000,
    ...overrides,
  } as ToolContent
}

function setupMetadataResponse(screenshots: ScreenshotMetadata[]): void {
  mockGet.mockResolvedValueOnce({
    data: { data: { screenshots, total: screenshots.length } },
  })
}

function setupBlobResponse(blobContent = 'fake-png-data'): void {
  mockGet.mockResolvedValueOnce({
    data: new Blob([blobContent], { type: 'image/png' }),
  })
}

function setupBlobFailure(): void {
  mockGet.mockRejectedValueOnce(new Error('Network error'))
}

// ── Tests ────────────────────────────────────────────────────────

describe('useScreenshotReplay', () => {
  let sessionId: ReturnType<typeof ref<string | undefined>>

  beforeEach(() => {
    vi.clearAllMocks()
    sessionId = ref<string | undefined>('session-1')
    // Mock URL.createObjectURL / revokeObjectURL
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn((blob: Blob) => `blob:${blob.size}`),
      revokeObjectURL: vi.fn(),
    })
  })

  it('starts in idle state', () => {
    const replay = useScreenshotReplay(sessionId)
    expect(replay.visualState.value).toBe('idle')
    expect(replay.activeTool.value).toBeNull()
  })

  it('selectTool transitions to ready when screenshot matches', async () => {
    const screenshots = [
      makeScreenshot({ id: 'ss-1', tool_call_id: 'tool-1', trigger: 'tool_after' }),
    ]
    setupMetadataResponse(screenshots)
    setupBlobResponse()

    const replay = useScreenshotReplay(sessionId)
    const tool = makeTool({ tool_call_id: 'tool-1' })

    await replay.selectTool(tool)

    expect(replay.visualState.value).toBe('ready')
    expect(replay.currentScreenshotUrl.value).toBeTruthy()
    expect(replay.activeTool.value).toBe(tool)
  })

  it('selectTool transitions to fallback when no screenshot matches', async () => {
    const screenshots = [
      makeScreenshot({ id: 'ss-1', tool_call_id: 'other-tool' }),
    ]
    setupMetadataResponse(screenshots)

    const replay = useScreenshotReplay(sessionId)
    const tool = makeTool({ tool_call_id: 'tool-no-match' })

    await replay.selectTool(tool)

    expect(replay.visualState.value).toBe('fallback')
    expect(replay.currentScreenshotUrl.value).toBe('')
  })

  it('selectTool transitions to error when blob fetch fails', async () => {
    const screenshots = [
      makeScreenshot({ id: 'ss-1', tool_call_id: 'tool-1' }),
    ]
    setupMetadataResponse(screenshots)
    setupBlobFailure()

    const replay = useScreenshotReplay(sessionId)
    const tool = makeTool({ tool_call_id: 'tool-1' })

    await replay.selectTool(tool)

    expect(replay.visualState.value).toBe('error')
  })

  it('selectTool prefers tool_after over tool_before', async () => {
    const screenshots = [
      makeScreenshot({ id: 'ss-before', tool_call_id: 'tool-1', trigger: 'tool_before', timestamp: 100 }),
      makeScreenshot({ id: 'ss-after', tool_call_id: 'tool-1', trigger: 'tool_after', timestamp: 200 }),
    ]
    setupMetadataResponse(screenshots)
    setupBlobResponse()

    const replay = useScreenshotReplay(sessionId)
    const tool = makeTool({ tool_call_id: 'tool-1' })

    await replay.selectTool(tool)

    expect(replay.visualState.value).toBe('ready')
    // Should have selected ss-after (index 1)
    expect(replay.currentIndex.value).toBe(1)
  })

  it('selectTool handles synthetic tool-progress entries by nearest timestamp within parent', async () => {
    const screenshots = [
      makeScreenshot({ id: 'ss-1', tool_call_id: 'parent-1', timestamp: 100 }),
      makeScreenshot({ id: 'ss-2', tool_call_id: 'parent-1', timestamp: 200 }),
      makeScreenshot({ id: 'ss-3', tool_call_id: 'parent-1', timestamp: 300 }),
    ]
    setupMetadataResponse(screenshots)
    setupBlobResponse()

    const replay = useScreenshotReplay(sessionId)
    // Synthetic ID format: tool-progress:{parent_id}:{index}
    const tool = makeTool({ tool_call_id: 'tool-progress:parent-1:2', timestamp: 210 })

    await replay.selectTool(tool)

    expect(replay.visualState.value).toBe('ready')
    // Nearest to timestamp 210 is ss-2 at timestamp 200 (index 1)
    expect(replay.currentIndex.value).toBe(1)
  })

  it('superseded selectTool does not overwrite newer selection', async () => {
    const screenshots = [
      makeScreenshot({ id: 'ss-1', tool_call_id: 'tool-1' }),
      makeScreenshot({ id: 'ss-2', tool_call_id: 'tool-2' }),
    ]
    setupMetadataResponse(screenshots) // for first call
    setupBlobResponse()                // slow blob for first call
    setupMetadataResponse(screenshots) // will not be called (metadata cached)
    setupBlobResponse()                // blob for second call

    const replay = useScreenshotReplay(sessionId)
    const tool1 = makeTool({ tool_call_id: 'tool-1' })
    const tool2 = makeTool({ tool_call_id: 'tool-2' })

    // Fire both without awaiting — tool2 should win
    const p1 = replay.selectTool(tool1)
    const p2 = replay.selectTool(tool2)
    await Promise.all([p1, p2])

    // tool2 was the last selection — it should own the state
    expect(replay.activeTool.value).toBe(tool2)
  })

  it('clearSelection resets to idle', async () => {
    const screenshots = [
      makeScreenshot({ id: 'ss-1', tool_call_id: 'tool-1' }),
    ]
    setupMetadataResponse(screenshots)
    setupBlobResponse()

    const replay = useScreenshotReplay(sessionId)
    await replay.selectTool(makeTool({ tool_call_id: 'tool-1' }))
    expect(replay.visualState.value).toBe('ready')

    replay.clearSelection()

    expect(replay.visualState.value).toBe('idle')
    expect(replay.activeTool.value).toBeNull()
    expect(replay.currentScreenshotUrl.value).toBe('')
  })

  it('ensureMetadataLoaded is idempotent', async () => {
    setupMetadataResponse([makeScreenshot({ id: 'ss-1' })])

    const replay = useScreenshotReplay(sessionId)
    await replay.ensureMetadataLoaded()
    await replay.ensureMetadataLoaded()

    // apiClient.get should only be called once for metadata
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('ensureMetadataLoaded does not auto-select a frame', async () => {
    setupMetadataResponse([
      makeScreenshot({ id: 'ss-1' }),
      makeScreenshot({ id: 'ss-2' }),
    ])

    const replay = useScreenshotReplay(sessionId)
    await replay.ensureMetadataLoaded()

    // currentIndex should remain -1 (no auto-selection)
    expect(replay.currentIndex.value).toBe(-1)
    expect(replay.visualState.value).toBe('idle')
  })

  it('jumpToLatest selects last frame and resets to idle', async () => {
    setupMetadataResponse([
      makeScreenshot({ id: 'ss-1' }),
      makeScreenshot({ id: 'ss-2' }),
      makeScreenshot({ id: 'ss-3' }),
    ])

    const replay = useScreenshotReplay(sessionId)
    await replay.ensureMetadataLoaded()
    replay.jumpToLatest()

    expect(replay.currentIndex.value).toBe(2) // last index
    expect(replay.visualState.value).toBe('idle')
  })
})
```

**Step 2: Run tests**

Run: `cd frontend && bun run test:run -- --reporter=verbose src/composables/__tests__/useScreenshotReplay.test.ts`
Expected: All 9 tests PASS

**Step 3: Commit**

```bash
git add frontend/src/composables/__tests__/useScreenshotReplay.test.ts
git commit -m "test(replay): add state machine tests for useScreenshotReplay

Cover selectTool transitions (ready, fallback, error), synthetic
entries, stale-request invalidation, ensureMetadataLoaded idempotency,
clearSelection, and jumpToLatest."
```

---

### Task 3: Update ChatPage.vue — delete syncReplayToTool, use new API

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`

**Step 1: Delete `syncReplayToTool` (lines 4299-4362)**

Remove the entire `syncReplayToTool` function.

**Step 2: Rewrite `showToolFromTimeline` (lines 4364-4380)**

Replace with:

```typescript
const showToolFromTimeline = async (index: number) => {
  if (toolTimeline.value.length === 0) return;
  if (!canOpenLiveViewPanel.value) return;
  const clampedIndex = Math.max(0, Math.min(index, toolTimeline.value.length - 1));
  const tool = toolTimeline.value[clampedIndex];
  if (!tool) return;
  realTime.value = false;
  if (showToolPanelIfAllowed(tool, false)) {
    panelToolId.value = tool.tool_call_id;
    await replay.selectTool(tool);
  }
}
```

Note: `replay.selectTool()` internally calls `ensureMetadataLoaded()`, so the explicit `loadScreenshots()` / `hasScreenshots` check is no longer needed.

**Step 3: Rewrite `handleToolClick` (lines 4399-4408)**

Replace with:

```typescript
const handleToolClick = (tool: ToolContent) => {
  realTime.value = false;
  if (!canOpenLiveViewPanel.value) return;
  if (sessionId.value) {
    if (showToolPanelIfAllowed(tool, false)) {
      panelToolId.value = tool.tool_call_id;
      void replay.selectTool(tool);
    }
  }
}
```

**Step 4: Update `jumpToRealTime` (lines 4410-4418)**

Add `replay.clearSelection()` to reset replay state when jumping back to live:

```typescript
const jumpToRealTime = () => {
  realTime.value = true;
  replay.clearSelection();
  if (!canOpenLiveViewPanel.value) return;
  if (lastNoMessageTool.value) {
    if (showToolPanelIfAllowed(lastNoMessageTool.value, isLiveTool(lastNoMessageTool.value))) {
      panelToolId.value = lastNoMessageTool.value.tool_call_id;
    }
  }
}
```

**Step 5: Update the session-done handler (line 3530)**

Change `replay.loadScreenshots()` to `replay.ensureMetadataLoaded()` since we no longer want auto-selection:

```typescript
replay.ensureMetadataLoaded();
```

Note: `loadScreenshots()` is still exported for backward compat (timeline scrubber etc.). The new `ensureMetadataLoaded()` is the preferred entry point.

**Step 6: Pass `replayVisualState` prop down to ToolPanel**

Find where `ToolPanel` is used in the template (around line 420-520). Add the new prop alongside existing replay props. There are typically two `ToolPanel` usages — the main one and a share-mode one.

Add to both ToolPanel instances:
```html
:replayVisualState="replay.visualState.value"
```

**Step 7: Verify TypeScript compiles**

Run: `cd frontend && bun run type-check`
Expected: Will fail until ToolPanel and ToolPanelContent accept the new prop (Task 4).

**Step 8: Commit (after Task 4 completes)**

Commit together with Task 4.

---

### Task 4: Update ToolPanel and ToolPanelContent — visual-state-driven rendering

**Files:**
- Modify: `frontend/src/components/ToolPanel.vue`
- Modify: `frontend/src/components/ToolPanelContent.vue`

**Step 1: Add prop to ToolPanel.vue**

In the `defineProps` interface (line 106-132), add:

```typescript
replayVisualState?: 'idle' | 'resolving' | 'ready' | 'fallback' | 'error'
```

In the template `<ToolPanelContent>` usage (line 11-46), add the pass-through prop:

```html
:replayVisualState="panelProps.replayVisualState"
```

Import the type at the top of the script:

```typescript
import type { ReplayVisualState } from '../composables/useScreenshotReplay'
```

And update the prop type to use it:

```typescript
replayVisualState?: ReplayVisualState
```

**Step 2: Add prop to ToolPanelContent.vue**

In the `defineProps` interface (line 576-609), add:

```typescript
replayVisualState?: 'idle' | 'resolving' | 'ready' | 'fallback' | 'error'
```

Import the type:

```typescript
import type { ReplayVisualState } from '@/composables/useScreenshotReplay'
```

And use:

```typescript
replayVisualState?: ReplayVisualState
```

**Step 3: Replace the replay v-if branches (lines 300-326)**

Replace the existing user-navigated replay branches:

```html
<!-- OLD: lines 300-326 (two branches) -->
```

With the visual-state-driven branches:

```html
          <!-- Replay: screenshot ready (user-navigated) -->
          <div
            v-else-if="isReplayMode && !realTime && replayVisualState === 'ready' && !!replayScreenshotUrl && (presentationViewType === 'live_preview' || !presentationViewType)"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <ScreenshotReplayViewer
              :src="replayScreenshotUrl || ''"
              :metadata="replayMetadata || null"
            />
          </div>

          <!-- Replay: resolving (user-navigated, blob loading) -->
          <div
            v-else-if="isReplayMode && !realTime && replayVisualState === 'resolving' && (presentationViewType === 'live_preview' || !presentationViewType)"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <LoadingState
              label="Loading replay"
              :is-active="true"
              animation="globe"
            />
          </div>

          <!-- Replay: fallback or error (user-navigated, no screenshot for this tool) -->
          <div
            v-else-if="isReplayMode && !realTime && (replayVisualState === 'fallback' || replayVisualState === 'error') && (presentationViewType === 'live_preview' || !presentationViewType)"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <GenericContentView
              :tool-name="toolContent?.name"
              :function-name="toolContent?.function"
              :args="toolContent?.args"
              :status="toolStatus"
              :result="toolContent?.content?.result"
              :content="toolContent?.content"
              :is-executing="false"
            />
          </div>
```

**Step 4: Replace the auto-settled replay branches (lines 437-460)**

Replace with visual-state-aware versions. These branches fire for sessions that ended and no dedicated view matched above:

```html
          <!-- Replay mode (auto-settled): screenshot ready for non-overlay tools -->
          <div
            v-else-if="isReplayMode && !!replayScreenshotUrl && (replayVisualState === 'ready' || replayVisualState === 'idle')"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <ScreenshotReplayViewer
              :src="replayScreenshotUrl || ''"
              :metadata="replayMetadata || null"
            />
          </div>

          <!-- Replay mode (auto-settled): no screenshot — show tool content or fallback -->
          <div
            v-else-if="isReplayMode && (replayVisualState === 'fallback' || replayVisualState === 'error' || (!replayScreenshotUrl && replayVisualState !== 'resolving'))"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <GenericContentView
              :tool-name="toolContent?.name"
              :function-name="toolContent?.function"
              :args="toolContent?.args"
              :status="toolStatus"
              :result="toolContent?.content?.result"
              :content="toolContent?.content"
              :is-executing="false"
            />
          </div>

          <!-- Replay mode (auto-settled): resolving -->
          <div
            v-else-if="isReplayMode && replayVisualState === 'resolving'"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <LoadingState
              label="Loading replay"
              :is-active="true"
              animation="globe"
            />
          </div>
```

**Step 5: Verify TypeScript compiles**

Run: `cd frontend && bun run type-check`
Expected: PASS

**Step 6: Verify ESLint**

Run: `cd frontend && bun run lint`
Expected: Only the pre-existing `PartialResults` unused import warning (not our code)

**Step 7: Run all frontend tests**

Run: `cd frontend && bun run test:run`
Expected: All tests PASS, including `livePreviewSelection.test.ts` (7 tests) and `useScreenshotReplay.test.ts` (9 tests)

**Step 8: Commit Task 3 + Task 4 together**

```bash
git add frontend/src/composables/useScreenshotReplay.ts \
       frontend/src/pages/ChatPage.vue \
       frontend/src/components/ToolPanel.vue \
       frontend/src/components/ToolPanelContent.vue
git commit -m "feat(replay): target-driven state machine for screenshot replay

Move screenshot matching from ChatPage into useScreenshotReplay
composable. selectTool() owns matching + blob loading with
selectionVersion invalidation. ChatPage no longer mutates
replay.currentIndex directly.

Rendering branches in ToolPanelContent now key off
ReplayVisualState (ready|resolving|fallback|error) instead of
the raw replayScreenshotUrl string, fixing:
- infinite loading spinner when no screenshot exists
- stale screenshot reuse from previous tool selection
- transition flash from loadScreenshots auto-selection"
```

---

### Task 5: Integration verification

**Step 1: Run full frontend test suite**

Run: `cd frontend && bun run test:run -- --reporter=verbose`
Expected: All tests PASS

**Step 2: Run TypeScript check**

Run: `cd frontend && bun run type-check`
Expected: PASS (exit 0)

**Step 3: Run ESLint**

Run: `cd frontend && bun run lint`
Expected: Only the pre-existing `PartialResults` unused import error (not our code)

**Step 4: Run backend tests (sanity check — no backend changes in this plan)**

Run: `cd backend && conda run -n pythinker pytest tests/domain/services/test_file_sync_manager.py -v --no-header -p no:cov -o addopts=`
Expected: 7/7 PASS

**Step 5: Verify final git state**

Run: `git log --oneline -5`
Expected: See the replay state machine commits in order
