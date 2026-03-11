# Replay State Machine Design

**Date**: 2026-03-10
**Status**: Approved
**Scope**: Frontend replay system — `useScreenshotReplay.ts`, `ChatPage.vue`, `ToolPanelContent.vue`

## Problem

Three bugs in the replay system share a single root cause: screenshot matching lives in `ChatPage.vue` while blob lifecycle lives in `useScreenshotReplay.ts`. This split creates:

1. **Infinite loading spinner** — when no screenshot exists for a browser tool, `replayScreenshotUrl` stays empty and the "Loading replay" branch fires forever.
2. **Stale screenshot reuse** — when `syncReplayToTool` finds no match, it silently keeps the previous `currentIndex`, showing the WRONG screenshot for a different tool.
3. **Transition flash** — `loadScreenshots()` auto-selects the latest frame, briefly flashing the last screenshot before `syncReplayToTool` corrects the index.

## Design

### State Model

A `ReplayVisualState` discriminated union replaces scattered boolean checks:

```typescript
type ReplayVisualState = 'idle' | 'resolving' | 'ready' | 'fallback' | 'error'
```

| State | Meaning | UI Rendering |
|-------|---------|--------------|
| `idle` | No replay tool selected | Default behavior |
| `resolving` | Tool selected, matching + blob loading in progress | Brief loading spinner |
| `ready` | Matched screenshot blob is loaded and ready | `ScreenshotReplayViewer` |
| `fallback` | No screenshot exists for this tool | `GenericContentView` (tool args + result) |
| `error` | Screenshot existed but blob fetch failed | `GenericContentView` + error badge |

### API Surface

`useScreenshotReplay` gains a target-driven API:

```typescript
// Lifecycle
ensureMetadataLoaded(): Promise<void>   // Idempotent; loads screenshot list if not loaded
clearSelection(): void                   // Reset to idle
jumpToLatest(): void                     // Select last screenshot (live mode)

// Selection (the core operation)
selectTool(tool: ToolContent): Promise<void>
  // 1. Immediately: set visualState='resolving', clear currentBlobUrl, bump selectionVersion
  // 2. Match: find screenshot by deterministic rules (see below)
  // 3. If no match: set visualState='fallback', return
  // 4. If match: fetch blob
  // 5. If fetch fails: set visualState='error'
  // 6. If fetch succeeds AND selectionVersion still current: set visualState='ready', set currentBlobUrl

// Exposed state
visualState: Ref<ReplayVisualState>
activeTool: Ref<ToolContent | null>
currentBlobUrl: Ref<string>
currentScreenshot: ComputedRef<ScreenshotMetadata | null>
screenshots: Ref<ScreenshotMetadata[]>
// Timeline navigation (unchanged)
progress, canStepForward, canStepBackward, currentTimestamp, hasScreenshots
stepForward, stepBackward, seekByProgress
```

### Matching Rules (Deterministic Only)

1. **Exact `tool_call_id` match**, preferring `trigger === 'tool_after'` over `'tool_before'` over `'periodic'`
2. **Synthetic entries** (`tool-progress:{parentId}:{index}`): extract parent `tool_call_id`, filter screenshots to that parent only, pick by nearest timestamp within that set
3. **No global nearest-timestamp fallback** — this is what made wrong screenshots appear truthful

### Critical Invariant

When `selectTool(tool)` is called:
1. `selectionVersion++` (invalidates any in-flight fetch)
2. `currentBlobUrl = ''` (prevents stale frame from showing)
3. `visualState = 'resolving'`

These three happen synchronously before any async work.

### Metadata Loading vs Selection Separation

`ensureMetadataLoaded()` loads the screenshot list but does NOT auto-select a frame. The current `loadScreenshots()` sets `currentIndex = screenshots.length - 1` — this causes the flash. Instead:
- `ensureMetadataLoaded()` populates `screenshots[]` only
- `selectTool()` or `jumpToLatest()` set `currentIndex`

### Rendering Changes (ToolPanelContent.vue)

The v-if chain for browser/`live_preview` tools in replay mode becomes:

```
<!-- Replay: screenshot ready -->
v-else-if="isReplayMode && !realTime && replayVisualState === 'ready' && replayScreenshotUrl
           && (presentationViewType === 'live_preview' || !presentationViewType)"
  → ScreenshotReplayViewer

<!-- Replay: resolving (loading) -->
v-else-if="isReplayMode && !realTime && replayVisualState === 'resolving'
           && (presentationViewType === 'live_preview' || !presentationViewType)"
  → LoadingState (brief spinner)

<!-- Replay: fallback or error (no screenshot) -->
v-else-if="isReplayMode && !realTime
           && (replayVisualState === 'fallback' || replayVisualState === 'error')
           && (presentationViewType === 'live_preview' || !presentationViewType)"
  → GenericContentView (tool args + result)
```

The catch-all replay branches at lines 441-460 (auto-settled) follow the same pattern.

### ChatPage.vue Simplification

`syncReplayToTool` is deleted. `showToolFromTimeline` becomes:

```typescript
const showToolFromTimeline = async (index: number) => {
  const tool = toolTimeline[index]
  realTime.value = false
  await replay.ensureMetadataLoaded()
  await replay.selectTool(tool)
  showToolPanelIfAllowed(tool, false)
}
```

ChatPage no longer mutates `replay.currentIndex` directly.

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/composables/useScreenshotReplay.ts` | Add `visualState`, `selectTool()`, `ensureMetadataLoaded()`, matching logic. Refactor `loadScreenshots()` to not auto-select. |
| `frontend/src/pages/ChatPage.vue` | Delete `syncReplayToTool`. Simplify `showToolFromTimeline` to call `replay.selectTool()`. |
| `frontend/src/components/ToolPanelContent.vue` | Replace `replayScreenshotUrl`-based v-if branches with `replayVisualState`-based branches. Add `replayVisualState` prop. |
| `frontend/src/components/ToolPanel.vue` | Pass `replayVisualState` prop through. |
| `frontend/src/utils/__tests__/useScreenshotReplay.test.ts` | New: test state transitions for selectTool (matched, fallback, error, stale version). |

## What This Does NOT Change

- Backend screenshot storage/retrieval (unchanged)
- `useScreenshotReplay` timeline navigation (`stepForward`/`stepBackward`/`seekByProgress` — these still work via `currentIndex` for timeline scrubbing)
- `ScreenshotReplayViewer` component (unchanged)
- `GenericContentView` component (unchanged — already handles tool data display)
- Other tool type rendering (terminal, search, editor, chart — all unchanged)
