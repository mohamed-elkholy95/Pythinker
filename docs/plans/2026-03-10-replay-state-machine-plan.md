# Replay State Machine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the split screenshot-matching (ChatPage) + blob-loading (composable) architecture with a unified target-driven replay state machine inside `useScreenshotReplay.ts`, fixing infinite loading, stale screenshots, and transition flash bugs.

**Architecture:** A `ReplayVisualState` enum (`idle | resolving | ready | fallback | error`) drives all UI rendering. The composable owns both matching and blob loading through a single `watch(targetScreenshotId)` watcher with Vue `onCleanup` for stale-request cancellation. ChatPage calls `selectTool(tool)` and reads `visualState` — it never mutates internal replay state. `selectTool()` does matching only; setting `targetScreenshotId` triggers the watcher to load the blob.

**Tech Stack:** Vue 3 Composition API, TypeScript strict mode, Vitest

**Design doc:** `docs/plans/2026-03-10-replay-state-machine-design.md`

**Review findings applied:** Single blob-loading owner (watcher only), `metadataPromise` deduplication, session-complete path preserved via async `jumpToLatest()`, `withSetup` test pattern per Vue testing guide.

---

### Task 1: Rewrite useScreenshotReplay composable with target-driven state machine

**Files:**
- Modify: `frontend/src/composables/useScreenshotReplay.ts`

The complete rewrite replaces the file. Key architectural decisions:
- **One blob-loading path**: `watch(targetScreenshotId, ..., { onCleanup })` is the ONLY code that fetches blobs. The old `watch(currentScreenshot)` watcher is removed.
- **`selectTool()` does matching only**: it finds the screenshot index, sets `targetScreenshotId`, and the watcher handles the rest.
- **`metadataPromise`** deduplicates concurrent `ensureMetadataLoaded()` calls and caches the "loaded but empty" case.
- **All index-changing operations** (`stepForward`, `stepBackward`, `seekByProgress`, `jumpToLatest`) set `targetScreenshotId` to trigger blob loading through the watcher.

**Step 1: Write the complete composable**

```typescript
import { ref, computed, watch, onUnmounted, type Ref, type ComputedRef } from 'vue'
import type { ScreenshotMetadata, ScreenshotListResponse } from '../types/screenshot'
import type { ToolContent } from '../types/message'
import { apiClient, type ApiResponse } from '../api/client'
import { toEpochSeconds } from '../utils/time'

export type ReplayVisualState = 'idle' | 'resolving' | 'ready' | 'fallback' | 'error'

export function useScreenshotReplay(sessionId: Ref<string | undefined>) {
  const screenshots = ref<ScreenshotMetadata[]>([])
  const currentIndex = ref<number>(-1)
  const isLoading = ref(false)

  // ── Target-driven state machine ──
  const visualState = ref<ReplayVisualState>('idle')
  const activeTool = ref<ToolContent | null>(null)
  const targetScreenshotId = ref<string | null>(null)
  let selectionVersion = 0

  // ── Metadata deduplication ──
  let metadataPromise: Promise<void> | null = null
  let metadataStatus: 'idle' | 'loading' | 'loaded' | 'error' = 'idle'

  // ── Blob URL management ──
  const currentBlobUrl = ref<string>('')
  const blobUrlCache = new Map<string, string>()

  // ── Computed properties (unchanged from original) ──

  const currentScreenshot: ComputedRef<ScreenshotMetadata | null> = computed(() => {
    if (currentIndex.value < 0 || currentIndex.value >= screenshots.value.length) return null
    return screenshots.value[currentIndex.value]
  })

  const currentScreenshotUrl: ComputedRef<string> = computed(() => {
    return currentBlobUrl.value
  })

  const progress: ComputedRef<number> = computed(() => {
    const total = screenshots.value.length
    if (total <= 1 || currentIndex.value < 0) return 0
    return (currentIndex.value / (total - 1)) * 100
  })

  const canStepForward: ComputedRef<boolean> = computed(() => {
    return currentIndex.value >= 0 && currentIndex.value < screenshots.value.length - 1
  })

  const canStepBackward: ComputedRef<boolean> = computed(() => {
    return currentIndex.value > 0
  })

  const currentTimestamp: ComputedRef<number | undefined> = computed(() => {
    return currentScreenshot.value?.timestamp
  })

  const hasScreenshots: ComputedRef<boolean> = computed(() => {
    return screenshots.value.length > 0
  })

  // ── Blob fetching internals ──

  async function fetchScreenshotBlob(screenshotId: string): Promise<string> {
    if (!sessionId.value) return ''
    try {
      const response = await apiClient.get(
        `/sessions/${sessionId.value}/screenshots/${screenshotId}`,
        { responseType: 'blob' }
      )
      return URL.createObjectURL(response.data as Blob)
    } catch {
      return ''
    }
  }

  function clearBlobCache(): void {
    for (const url of blobUrlCache.values()) {
      URL.revokeObjectURL(url)
    }
    blobUrlCache.clear()
    currentBlobUrl.value = ''
  }

  async function getOrFetchBlobUrl(screenshotId: string): Promise<string> {
    const cachedUrl = blobUrlCache.get(screenshotId)
    if (cachedUrl) return cachedUrl

    const blobUrl = await fetchScreenshotBlob(screenshotId)
    if (blobUrl) blobUrlCache.set(screenshotId, blobUrl)
    return blobUrl
  }

  const MAX_CACHE_SIZE = 20

  function evictOldFrames(): void {
    if (blobUrlCache.size <= MAX_CACHE_SIZE) return
    const current = currentIndex.value
    const keepIds = new Set<string>()
    for (let i = Math.max(0, current - 5); i <= Math.min(screenshots.value.length - 1, current + 5); i++) {
      keepIds.add(screenshots.value[i].id)
    }
    for (const [id, url] of blobUrlCache.entries()) {
      if (!keepIds.has(id)) {
        URL.revokeObjectURL(url)
        blobUrlCache.delete(id)
      }
      if (blobUrlCache.size <= MAX_CACHE_SIZE) break
    }
  }

  async function prefetchAhead(count = 3): Promise<void> {
    const fetches: Promise<void>[] = []
    for (let offset = 1; offset <= count; offset++) {
      const idx = currentIndex.value + offset
      if (idx < 0 || idx >= screenshots.value.length) break
      const s = screenshots.value[idx]
      if (!s || blobUrlCache.has(s.id)) continue
      fetches.push(
        fetchScreenshotBlob(s.id).then((url) => {
          if (url) blobUrlCache.set(s.id, url)
        })
      )
    }
    await Promise.all(fetches)
    evictOldFrames()
  }

  async function prefetchBehind(count = 2): Promise<void> {
    const fetches: Promise<void>[] = []
    for (let offset = 1; offset <= count; offset++) {
      const idx = currentIndex.value - offset
      if (idx < 0) break
      const s = screenshots.value[idx]
      if (!s || blobUrlCache.has(s.id)) continue
      fetches.push(
        fetchScreenshotBlob(s.id).then((url) => {
          if (url) blobUrlCache.set(s.id, url)
        })
      )
    }
    await Promise.all(fetches)
  }

  // ── Single blob-loading watcher ──
  // This is the ONLY path that fetches blobs for display.
  // All operations that change the displayed frame do so by setting
  // targetScreenshotId, which triggers this watcher.

  watch(targetScreenshotId, async (id, _oldId, onCleanup) => {
    if (!id) {
      currentBlobUrl.value = ''
      return
    }

    let cancelled = false
    onCleanup(() => { cancelled = true })

    const blobUrl = await getOrFetchBlobUrl(id)
    if (cancelled) return

    if (!blobUrl) {
      currentBlobUrl.value = ''
      if (visualState.value === 'resolving') visualState.value = 'error'
      return
    }

    currentBlobUrl.value = blobUrl
    if (visualState.value === 'resolving') visualState.value = 'ready'

    void prefetchAhead(3)
    void prefetchBehind(2)
  })

  // ── Metadata loading (deduplicated, caches empty results) ──

  async function ensureMetadataLoaded(): Promise<void> {
    if (metadataStatus === 'loaded') return
    if (metadataPromise) return metadataPromise

    metadataPromise = (async () => {
      if (!sessionId.value) return
      isLoading.value = true
      try {
        const response = await apiClient.get<ApiResponse<ScreenshotListResponse>>(
          `/sessions/${sessionId.value}/screenshots`
        )
        screenshots.value = response.data.data.screenshots.filter(
          (s) => s.trigger !== 'session_end'
        )
        metadataStatus = 'loaded' // cached even if empty
      } catch {
        screenshots.value = []
        metadataStatus = 'error'
      } finally {
        isLoading.value = false
        metadataPromise = null
      }
    })()

    return metadataPromise
  }

  // ── Deterministic screenshot matching ──

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

    // Rule 1: exact tool_call_id, prefer tool_after > tool_before > periodic
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

  // ── Public API: tool selection ──

  async function selectTool(tool: ToolContent): Promise<void> {
    // Critical invariant: synchronous state clear before any async work
    const version = ++selectionVersion
    currentBlobUrl.value = ''
    visualState.value = 'resolving'
    activeTool.value = tool
    targetScreenshotId.value = null // cancel any in-flight blob load

    await ensureMetadataLoaded()
    if (version !== selectionVersion) return // superseded

    const matchIdx = findScreenshotForTool(tool)
    if (matchIdx < 0) {
      visualState.value = 'fallback'
      currentIndex.value = -1
      return
    }

    currentIndex.value = matchIdx
    // Setting targetScreenshotId triggers the watcher to load the blob.
    // The watcher transitions resolving → ready (or → error).
    targetScreenshotId.value = screenshots.value[matchIdx].id
  }

  function clearSelection(): void {
    selectionVersion++
    visualState.value = 'idle'
    activeTool.value = null
    currentBlobUrl.value = ''
    currentIndex.value = -1
    targetScreenshotId.value = null
  }

  async function jumpToLatest(): Promise<void> {
    selectionVersion++
    activeTool.value = null
    await ensureMetadataLoaded()
    if (screenshots.value.length > 0) {
      currentIndex.value = screenshots.value.length - 1
      visualState.value = 'resolving'
      targetScreenshotId.value = screenshots.value[currentIndex.value].id
    } else {
      visualState.value = 'idle'
      currentIndex.value = -1
    }
  }

  // ── Backward-compatible loadScreenshots ──
  // Kept for existing callers. Delegates to ensureMetadataLoaded + jumpToLatest.

  async function loadScreenshots(): Promise<void> {
    metadataStatus = 'idle' // force reload
    metadataPromise = null
    clearBlobCache()
    await ensureMetadataLoaded()
    if (screenshots.value.length > 0) {
      currentIndex.value = screenshots.value.length - 1
      targetScreenshotId.value = screenshots.value[currentIndex.value].id
    }
  }

  // ── Timeline stepping (all set targetScreenshotId for blob loading) ──

  function stepForward(): void {
    if (canStepForward.value) {
      currentIndex.value++
      targetScreenshotId.value = currentScreenshot.value?.id ?? null
    }
  }

  function stepBackward(): void {
    if (canStepBackward.value) {
      currentIndex.value--
      targetScreenshotId.value = currentScreenshot.value?.id ?? null
    }
  }

  function seekByProgress(percent: number): void {
    const total = screenshots.value.length
    if (total === 0) return
    const maxIndex = total - 1
    currentIndex.value = Math.round((percent / 100) * maxIndex)
    targetScreenshotId.value = currentScreenshot.value?.id ?? null
  }

  // ── Session change resets everything ──

  watch(sessionId, (nextSessionId, previousSessionId) => {
    if (nextSessionId !== previousSessionId) {
      selectionVersion++
      clearBlobCache()
      screenshots.value = []
      currentIndex.value = -1
      visualState.value = 'idle'
      activeTool.value = null
      targetScreenshotId.value = null
      metadataStatus = 'idle'
      metadataPromise = null
    }
  })

  // ── Cleanup ──

  onUnmounted(() => {
    selectionVersion++
    targetScreenshotId.value = null
    clearBlobCache()
  })

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
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && bun run type-check`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/composables/useScreenshotReplay.ts
git commit -m "feat(replay): rewrite useScreenshotReplay as target-driven state machine

Single blob-loading owner via watch(targetScreenshotId) with onCleanup.
selectTool() does deterministic matching only; watcher loads blobs.
ensureMetadataLoaded() deduplicates via metadataPromise and caches
empty results. jumpToLatest() is async and preserves session-complete
default frame behavior."
```

---

### Task 2: Write tests using Vue withSetup pattern

**Files:**
- Create: `frontend/src/composables/__tests__/useScreenshotReplay.test.ts`

**Step 1: Write tests**

Uses Vue's `withSetup` pattern (from Vue testing guide) instead of mocking `vue` core exports:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest'
import { createApp, ref } from 'vue'
import { useScreenshotReplay, type ReplayVisualState } from '../useScreenshotReplay'
import type { ToolContent } from '../../types/message'
import type { ScreenshotMetadata } from '../../types/screenshot'

// Mock apiClient
vi.mock('../../api/client', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

import { apiClient } from '../../api/client'

const mockGet = apiClient.get as Mock

// ── withSetup helper (Vue testing guide pattern) ──

function withSetup<T>(composable: () => T): { result: T; unmount: () => void } {
  let result!: T
  const app = createApp({
    setup() {
      result = composable()
      return () => null
    },
  })
  app.mount(document.createElement('div'))
  return { result, unmount: () => app.unmount() }
}

// ── Helpers ──

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

function setupMetadataResponse(items: ScreenshotMetadata[]): void {
  mockGet.mockResolvedValueOnce({
    data: { data: { screenshots: items, total: items.length } },
  })
}

function setupBlobResponse(content = 'fake-png'): void {
  mockGet.mockResolvedValueOnce({
    data: new Blob([content], { type: 'image/png' }),
  })
}

function setupBlobFailure(): void {
  mockGet.mockRejectedValueOnce(new Error('Network error'))
}

// ── Tests ──

describe('useScreenshotReplay', () => {
  let sessionId: ReturnType<typeof ref<string | undefined>>
  let unmount: () => void

  beforeEach(() => {
    vi.clearAllMocks()
    sessionId = ref<string | undefined>('session-1')
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn((blob: Blob) => `blob:${blob.size}`),
      revokeObjectURL: vi.fn(),
    })
  })

  afterEach(() => {
    if (unmount) unmount()
  })

  function setup() {
    const { result, unmount: u } = withSetup(() => useScreenshotReplay(sessionId))
    unmount = u
    return result
  }

  it('starts in idle state', () => {
    const replay = setup()
    expect(replay.visualState.value).toBe('idle')
    expect(replay.activeTool.value).toBeNull()
  })

  it('selectTool transitions to ready when screenshot matches', async () => {
    setupMetadataResponse([
      makeScreenshot({ id: 'ss-1', tool_call_id: 'tool-1', trigger: 'tool_after' }),
    ])
    setupBlobResponse()

    const replay = setup()
    const tool = makeTool({ tool_call_id: 'tool-1' })

    await replay.selectTool(tool)

    expect(replay.visualState.value).toBe('ready')
    expect(replay.currentScreenshotUrl.value).toBeTruthy()
    expect(replay.activeTool.value).toBe(tool)
  })

  it('selectTool transitions to fallback when no screenshot matches', async () => {
    setupMetadataResponse([
      makeScreenshot({ id: 'ss-1', tool_call_id: 'other-tool' }),
    ])

    const replay = setup()
    await replay.selectTool(makeTool({ tool_call_id: 'tool-no-match' }))

    expect(replay.visualState.value).toBe('fallback')
    expect(replay.currentScreenshotUrl.value).toBe('')
  })

  it('selectTool transitions to error when blob fetch fails', async () => {
    setupMetadataResponse([
      makeScreenshot({ id: 'ss-1', tool_call_id: 'tool-1' }),
    ])
    setupBlobFailure()

    const replay = setup()
    await replay.selectTool(makeTool({ tool_call_id: 'tool-1' }))

    expect(replay.visualState.value).toBe('error')
  })

  it('selectTool prefers tool_after over tool_before', async () => {
    setupMetadataResponse([
      makeScreenshot({ id: 'ss-before', tool_call_id: 'tool-1', trigger: 'tool_before', timestamp: 100 }),
      makeScreenshot({ id: 'ss-after', tool_call_id: 'tool-1', trigger: 'tool_after', timestamp: 200 }),
    ])
    setupBlobResponse()

    const replay = setup()
    await replay.selectTool(makeTool({ tool_call_id: 'tool-1' }))

    expect(replay.visualState.value).toBe('ready')
    expect(replay.currentIndex.value).toBe(1) // ss-after
  })

  it('selectTool handles synthetic tool-progress entries by nearest timestamp within parent', async () => {
    setupMetadataResponse([
      makeScreenshot({ id: 'ss-1', tool_call_id: 'parent-1', timestamp: 100 }),
      makeScreenshot({ id: 'ss-2', tool_call_id: 'parent-1', timestamp: 200 }),
      makeScreenshot({ id: 'ss-3', tool_call_id: 'parent-1', timestamp: 300 }),
    ])
    setupBlobResponse()

    const replay = setup()
    // Synthetic ID: tool-progress:{parent}:{index}
    await replay.selectTool(makeTool({ tool_call_id: 'tool-progress:parent-1:2', timestamp: 210 }))

    expect(replay.visualState.value).toBe('ready')
    expect(replay.currentIndex.value).toBe(1) // nearest to 210 is ss-2 at 200
  })

  it('superseded selectTool does not overwrite newer selection', async () => {
    setupMetadataResponse([
      makeScreenshot({ id: 'ss-1', tool_call_id: 'tool-1' }),
      makeScreenshot({ id: 'ss-2', tool_call_id: 'tool-2' }),
    ])
    setupBlobResponse() // for first call
    setupBlobResponse() // for second call

    const replay = setup()
    const tool1 = makeTool({ tool_call_id: 'tool-1' })
    const tool2 = makeTool({ tool_call_id: 'tool-2' })

    // Fire both — tool2 should win (supersedes tool1)
    const p1 = replay.selectTool(tool1)
    const p2 = replay.selectTool(tool2)
    await Promise.all([p1, p2])

    expect(replay.activeTool.value).toBe(tool2)
  })

  it('clearSelection resets to idle', async () => {
    setupMetadataResponse([
      makeScreenshot({ id: 'ss-1', tool_call_id: 'tool-1' }),
    ])
    setupBlobResponse()

    const replay = setup()
    await replay.selectTool(makeTool({ tool_call_id: 'tool-1' }))
    expect(replay.visualState.value).toBe('ready')

    replay.clearSelection()

    expect(replay.visualState.value).toBe('idle')
    expect(replay.activeTool.value).toBeNull()
    expect(replay.currentScreenshotUrl.value).toBe('')
  })

  it('ensureMetadataLoaded is idempotent and deduplicates concurrent calls', async () => {
    setupMetadataResponse([makeScreenshot({ id: 'ss-1' })])

    const replay = setup()
    // Call three times concurrently
    await Promise.all([
      replay.ensureMetadataLoaded(),
      replay.ensureMetadataLoaded(),
      replay.ensureMetadataLoaded(),
    ])

    // Only one HTTP request should have been made
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('ensureMetadataLoaded caches empty results and does not refetch', async () => {
    setupMetadataResponse([]) // zero screenshots

    const replay = setup()
    await replay.ensureMetadataLoaded()
    await replay.ensureMetadataLoaded()

    // Only one HTTP request — empty result is cached
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(replay.screenshots.value).toHaveLength(0)
  })

  it('ensureMetadataLoaded does not auto-select a frame', async () => {
    setupMetadataResponse([
      makeScreenshot({ id: 'ss-1' }),
      makeScreenshot({ id: 'ss-2' }),
    ])

    const replay = setup()
    await replay.ensureMetadataLoaded()

    expect(replay.currentIndex.value).toBe(-1)
    expect(replay.visualState.value).toBe('idle')
  })

  it('jumpToLatest selects last frame and transitions to resolving', async () => {
    setupMetadataResponse([
      makeScreenshot({ id: 'ss-1' }),
      makeScreenshot({ id: 'ss-2' }),
      makeScreenshot({ id: 'ss-3' }),
    ])
    setupBlobResponse()

    const replay = setup()
    await replay.jumpToLatest()

    expect(replay.currentIndex.value).toBe(2)
    // After blob loads via watcher: ready
    expect(replay.visualState.value).toBe('ready')
  })

  it('jumpToLatest with zero screenshots stays idle', async () => {
    setupMetadataResponse([])

    const replay = setup()
    await replay.jumpToLatest()

    expect(replay.currentIndex.value).toBe(-1)
    expect(replay.visualState.value).toBe('idle')
  })
})
```

**Step 2: Run tests**

Run: `cd frontend && bun run test:run -- --reporter=verbose src/composables/__tests__/useScreenshotReplay.test.ts`
Expected: All 12 tests PASS

**Step 3: Commit**

```bash
git add frontend/src/composables/__tests__/useScreenshotReplay.test.ts
git commit -m "test(replay): add state machine tests for useScreenshotReplay

Uses Vue withSetup pattern per testing guide. Covers selectTool
transitions (ready, fallback, error), synthetic entries, stale-request
invalidation, ensureMetadataLoaded deduplication and empty-cache,
clearSelection, and jumpToLatest with/without screenshots."
```

---

### Task 3: Update ChatPage.vue — delete syncReplayToTool, use new API

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`

**Step 1: Delete `syncReplayToTool` (lines 4299-4362)**

Remove the entire function.

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

Add `replay.clearSelection()`:

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

**Step 5: Update session-done handler (line 3530)**

Change `replay.loadScreenshots()` to `void replay.jumpToLatest()`:

```typescript
void replay.jumpToLatest();
```

This preserves the "show latest screenshot on session complete" behavior. `jumpToLatest()` internally calls `ensureMetadataLoaded()` and selects the last frame.

**Step 6: Pass `replayVisualState` prop to ToolPanel**

Add to both ToolPanel instances in the template:

```html
:replayVisualState="replay.visualState.value"
```

**Step 7: Remove `toEpochSeconds` import if no longer used by ChatPage**

Check if `toEpochSeconds` is still used elsewhere in ChatPage. If the only usage was in `syncReplayToTool` (now deleted), remove the import.

---

### Task 4: Update ToolPanel and ToolPanelContent — visual-state-driven rendering

**Files:**
- Modify: `frontend/src/components/ToolPanel.vue`
- Modify: `frontend/src/components/ToolPanelContent.vue`

**Step 1: Add prop to ToolPanel.vue**

Import type and add to props interface:

```typescript
import type { ReplayVisualState } from '../composables/useScreenshotReplay'

// In defineProps:
replayVisualState?: ReplayVisualState
```

Pass through in template:

```html
:replayVisualState="panelProps.replayVisualState"
```

**Step 2: Add prop to ToolPanelContent.vue**

Import type and add to props interface:

```typescript
import type { ReplayVisualState } from '@/composables/useScreenshotReplay'

// In defineProps:
replayVisualState?: ReplayVisualState
```

**Step 3: Replace user-navigated replay branches (lines 300-326)**

Replace with:

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

**Step 4: Replace auto-settled replay branches (lines 437-460)**

Replace with:

```html
          <!-- Replay (auto-settled): screenshot ready -->
          <div
            v-else-if="isReplayMode && !!replayScreenshotUrl && replayVisualState === 'ready'"
            class="absolute inset-0 bg-[var(--background-white-main)] overflow-hidden"
          >
            <ScreenshotReplayViewer
              :src="replayScreenshotUrl || ''"
              :metadata="replayMetadata || null"
            />
          </div>

          <!-- Replay (auto-settled): fallback or error -->
          <div
            v-else-if="isReplayMode && (replayVisualState === 'fallback' || replayVisualState === 'error')"
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

          <!-- Replay (auto-settled): resolving -->
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
Expected: PASS (or only pre-existing issues unrelated to our changes)

**Step 7: Run all frontend tests**

Run: `cd frontend && bun run test:run`
Expected: All tests PASS

**Step 8: Commit Task 3 + Task 4 together**

```bash
git add frontend/src/composables/useScreenshotReplay.ts \
       frontend/src/pages/ChatPage.vue \
       frontend/src/components/ToolPanel.vue \
       frontend/src/components/ToolPanelContent.vue
git commit -m "feat(replay): integrate state machine into ChatPage and ToolPanelContent

Delete syncReplayToTool from ChatPage — replaced by
replay.selectTool(). Session-done handler uses jumpToLatest()
to preserve default final screenshot. Rendering branches key off
ReplayVisualState instead of raw replayScreenshotUrl string."
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
Expected: PASS (or only pre-existing issues unrelated to our changes)

**Step 4: Verify final git state**

Run: `git log --oneline -5`
Expected: See the replay state machine commits in order
