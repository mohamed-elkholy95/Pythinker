# Search → Browse Auto-Transition Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Auto-transition from search results to live CDP browser view after 5 seconds, so the user sees the agent browsing top results in real-time.

**Architecture:** Add a watcher + timer in ToolPanelContent.vue that detects search completion, waits 5s, then sets the existing `forceBrowserView = true` ref to reveal the persistent CDP browser already streaming underneath.

**Tech Stack:** Vue 3 Composition API, existing `forceBrowserView` ref, existing `isSearching` computed

---

### Task 1: Add search→browse auto-transition timer

**Files:**
- Modify: `frontend/src/components/ToolPanelContent.vue:617` (near `forceBrowserView` declaration)
- Modify: `frontend/src/components/ToolPanelContent.vue:1301-1304` (existing `forceBrowserView` reset watcher)
- Modify: `frontend/src/components/ToolPanelContent.vue:1321-1323` (onUnmounted cleanup)

**Step 1: Add timer ref and auto-transition watcher after line 617**

After `const forceBrowserView = ref(false);` (line 617), add:

```typescript
// Auto-transition: search results → live browser after 5s
let searchBrowseTimer: ReturnType<typeof setTimeout> | null = null;

function clearSearchBrowseTimer() {
  if (searchBrowseTimer) {
    clearTimeout(searchBrowseTimer);
    searchBrowseTimer = null;
  }
}

// When search completes (isSearching goes true→false while viewing search), start 5s timer
watch(isSearching, (searching, wasSearching) => {
  if (wasSearching && !searching && currentViewType.value === 'search') {
    clearSearchBrowseTimer();
    searchBrowseTimer = setTimeout(() => {
      // Only transition if still on search view (user hasn't navigated away)
      if (currentViewType.value === 'search' && !forceBrowserView.value) {
        forceBrowserView.value = true;
      }
      searchBrowseTimer = null;
    }, 5000);
  }
});
```

**Step 2: Cancel timer when tool changes (modify existing watcher at line 1301-1304)**

Replace:
```typescript
// Reset forceBrowserView when tool changes (new tool selected)
watch(() => props.toolContent?.tool_call_id, () => {
  forceBrowserView.value = false;
});
```

With:
```typescript
// Reset forceBrowserView and cancel auto-transition when tool changes
watch(() => props.toolContent?.tool_call_id, () => {
  forceBrowserView.value = false;
  clearSearchBrowseTimer();
});
```

**Step 3: Cancel timer in handleBrowseUrl (line 1649)**

Add `clearSearchBrowseTimer();` as the first line inside `handleBrowseUrl`:

```typescript
const handleBrowseUrl = async (url: string) => {
  if (!props.sessionId || !url) return;
  clearSearchBrowseTimer(); // User clicked manually, cancel auto-transition

  try {
    // ... rest unchanged
```

**Step 4: Clean up on unmount (modify onUnmounted at line 1321-1323)**

Replace:
```typescript
onUnmounted(() => {
  stopAutoRefresh();
});
```

With:
```typescript
onUnmounted(() => {
  stopAutoRefresh();
  clearSearchBrowseTimer();
});
```

**Step 5: Verify**

Run: `cd frontend && bun run type-check`
Expected: PASS — no type errors

**Step 6: Verify lint**

Run: `cd frontend && bun run lint`
Expected: PASS — no lint errors

**Step 7: Commit**

```bash
git add frontend/src/components/ToolPanelContent.vue
git commit -m "feat(ui): auto-transition from search results to live browser after 5s"
```
