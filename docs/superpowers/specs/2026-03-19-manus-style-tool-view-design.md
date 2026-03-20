# Manus-Style Tool View Design

**Date:** 2026-03-19
**Status:** Approved (v2 — post spec-review fixes)
**Scope:** Frontend — ToolPanelContent, TimelineControls, TaskProgressBar, TerminalContentView

## Summary

Adopt the Manus AI agent's "Computer" tool view UX into Pythinker's existing tool panel. The existing codebase is already ~70% there — this spec covers the remaining gaps to reach full Manus parity.

## Reference: Manus Tool View Anatomy

```
┌─────────────────────────────────────────────────────┐
│  Pythinker's Computer                [💬] [⊡] [✕]  │  frame header
│  ✏ Pythinker is using Editor │ Reading file SKI...  │  activity line
├─────────────────────────────────────────────────────┤
│                    SKILL.md                          │  content-title bar
├─────────────────────────────────────────────────────┤
│                                                      │
│              [viewport content]                       │
│                                                      │
│           ┌──────────────────┐                       │
│           │  ▷ Jump to live  │                       │  floating (when not live)
│           └──────────────────┘                       │
├─────────────────────────────────────────────────────┤
│  [|◁ ▷|]  [━━━━━━━●━━━━━━━━━━━━]  ● live           │  compact timeline
├─────────────────────────────────────────────────────┤
│  ✓ Convert report to PDF and ZIP...    6 / 6    ∧   │  task checklist bar
└─────────────────────────────────────────────────────┘
```

## Existing State (What Already Works)

Before listing changes, here's what Pythinker already implements:

| Feature | Current State | File |
|---------|--------------|------|
| "Pythinker is using [Tool]" headline | `activityHeadline` computed (line 1124) | `ToolPanelContent.vue` |
| Tool icon (Lucide component) | `toolDisplay.icon` via `:is` (line 40) | `ToolPanelContent.vue` |
| URL status bar for browser | `url-status-bar` div (line 87) | `ToolPanelContent.vue` |
| Content header label (centered) | `contentHeaderLabel` computed (line 1142) | `ToolPanelContent.vue` |
| Step forward/backward buttons | `SkipBack`, `SkipForward` (lines 12-27) | `TimelineControls.vue` |
| Scrubber track with fill + thumb | `scrubber-track` (lines 31-62) | `TimelineControls.vue` |
| Inline "Jump to live" button | `jump-to-live-btn` (lines 66-73) | `TimelineControls.vue` |
| Live/replay indicator dot | `timeline-live-dot` (lines 76-84) | `TimelineControls.vue` |
| Expandable step list | `task-list` with flip animations (lines 82-141) | `TaskProgressBar.vue` |
| Step counter (N/M) | `progress-pill-lg` (lines 71-75) | `TaskProgressBar.vue` |
| Elapsed timer | `timer-section` (lines 144-155) | `TaskProgressBar.vue` |
| Collapse/expand chevron | `ChevronDown` toggle (line 59, 76) | `TaskProgressBar.vue` |

---

## Changes

### 1. Activity Line — Separator Change (`ToolPanelContent.vue`)

**Current:** `activityHeadline` `·` `activitySubtitle` (middot separator, line 46)

**New:** `activityHeadline` `│` `activitySubtitle` (pipe separator, matching Manus)

**Change:** Replace `&middot;` with `│` in the `panel-activity-separator` span (line 46). Adjust CSS if needed for spacing.

**File:** `ToolPanelContent.vue` line 46.

### 2. Unified Content-Title Bar (`ToolPanelContent.vue`)

**Current:** Two separate elements:
- `url-status-bar` (line 87) — only for browser views, shows URL
- `panel-content-header` (line 93) — for non-browser views, shows `contentHeaderLabel` + view tabs

**New:** Merge into one **unified content-title bar** that always shows a content-relevant title:

| View Type | Content-Title Shows |
|-----------|-------------------|
| Browser (`live_preview`) | Current URL (existing `resolvedBrowserUrl`) |
| Editor | Filename from `toolContent.file_path` (basename only, e.g. `"trending_repos_march_2026.md"`) |
| Terminal | Session name from `toolContent.session_name` or derived (see Section 3) |
| Search | `"Search"` |
| Chart | `"Chart"` |
| Generic / unknown | `contentHeaderLabel` (existing fallback) |

**Implementation:**
- Replace `url-status-bar` and the `context-bar-label` span inside `panel-content-header` with a single computed `contentTitleLabel` that resolves based on `currentViewType`
- Keep view-mode tabs (right side of panel-content-header) as they are — they sit beside the title
- Keep the `v-if` guard that hides the bar when embedded without forced view type
- The bar styling stays the same as existing `url-status-bar` (centered, muted text, subtle border)

**New computed:**
```typescript
const contentTitleLabel = computed(() => {
  if (showReportPresentation.value) return 'Report'
  if (showPlanPresentation.value) return 'Plan'
  if (showUrlStatusBar.value) return resolvedBrowserUrl.value || '/'

  const vt = currentViewType.value
  if (vt === 'editor') {
    const fp = props.toolContent?.file_path
    return fp ? fp.split('/').pop() : contentHeaderLabel.value
  }
  if (vt === 'terminal') {
    return props.toolContent?.session_name
      || deriveSessionName(props.toolContent?.command)
      || 'terminal'
  }
  if (vt === 'search') return 'Search'
  if (vt === 'chart' || vt === 'canvas') return 'Chart'
  return contentHeaderLabel.value || ''
})
```

### 3. Named Terminal Sessions

**Type changes:**

`frontend/src/types/event.ts` — add to `ToolEventData`:
```typescript
session_name?: string;  // Optional terminal session name from backend
```

`frontend/src/types/message.ts` — add to `ToolContent`:
```typescript
session_name?: string;  // Terminal session name (from backend or derived)
```

**Frontend derivation utility** (`frontend/src/utils/sessionName.ts` — new file):

```typescript
export function deriveSessionName(command: string | undefined): string {
  if (!command) return 'terminal'

  // Strip redirections and pipes for analysis
  const base = command.split('|')[0].split('>')[0].trim()
  const parts = base.split(/\s+/)
  const cmd = parts[0]

  // Script execution: python3 script.py → "script_name"
  if (['python3', 'python', 'node', 'bash', 'sh'].includes(cmd)) {
    const script = parts[1]
    if (script) {
      return script.replace(/\.\w+$/, '').replace(/[^a-zA-Z0-9]/g, '_') || 'terminal'
    }
  }

  // Package install
  if (['pip', 'npm', 'bun', 'yarn'].includes(cmd) && parts[1] === 'install') {
    return 'package_install'
  }

  // File creation via heredoc
  if (cmd === 'cat' && command.includes('<<')) return 'file_creation'

  // Known tool commands
  if (cmd.includes('pdf') || cmd.includes('convert')) return 'pdf_conversion'
  if (cmd === 'git') return `git_${parts[1] || 'operation'}`

  // Fallback: command name
  return cmd.replace(/[^a-zA-Z0-9]/g, '_') || 'terminal'
}
```

### 4. Header Control Buttons (`ToolPanelContent.vue`)

**Current:** Takeover (MonitorUp) + Minimize (Minimize2) + Close (X)

**New:** Chat (MessageSquare) + Split (Columns2) + Close (X)

| Button | Icon | Behavior (Desktop) | Behavior (Mobile) |
|--------|------|--------------------|--------------------|
| 💬 Chat | `MessageSquare` (Lucide) | Emit `switchToChat` → parent collapses panel, focuses chat input | Close panel overlay |
| ⊡ Split | `Columns2` (Lucide) | Toggle between 50/50 split and current drag-resized width. State: `isSplitMode` ref in `ToolPanelContent`. When split, set panel width to 50% of container. When un-split, restore previous width. | No-op (hidden on mobile) |
| ✕ Close | `X` (Lucide) | Close panel entirely (existing behavior) | Close panel overlay |

**Takeover button:** Move to a floating position inside the viewport content area (bottom-right corner, small icon) — it's still useful but not a primary window control.

**Emit chain for `switchToChat`:**
- `ToolPanelContent` emits `switchToChat`
- `ToolPanel` re-emits `switchToChat`
- `ChatPage` handles: calls `toolPanelRef.hideToolPanel(true)`, then `nextTick(() => chatInputRef.focus())`

**Split state:**
- State lives in `ToolPanelContent` as `isSplitMode: ref<boolean>(false)`
- On split toggle: emit `requestWidth(containerWidth * 0.5)` or `requestWidth(previousWidth)`
- `ToolPanel` handles `requestWidth` by updating its internal `effectiveWidth`

### 5. "Jump to Live" Floating Button (`ToolPanelContent.vue`)

**Current:** Inline button inside `TimelineControls` (line 66-73) — small, at the right of the scrubber.

**New:** ALSO add a floating overlay version centered over the viewport content area.

**Implementation:**
- Add a `<Transition>` block inside `ToolPanelContent`, positioned absolute over the content container (the `relative flex flex-col overflow-hidden` div at line 78)
- `v-if="showTimeline && !isTimelineLive"` — only when timeline exists and not at live position
- `isTimelineLive` derived from: `props.realTime` or `timelineProgress >= 99.5`
- Dark semi-transparent pill: `background: rgba(0, 0, 0, 0.75)`, `backdrop-filter: blur(8px)`
- White text + Play icon: `▷ Jump to live`
- Rounded pill shape, padding `8px 20px`, font 14px
- Centered horizontally, positioned `bottom: 24px` above the timeline
- `z-index: 5` (inside the `isolate` stacking context at line 80)
- Fade-in transition (150ms)
- On click: emit `jumpToRealTime` (existing emit, line 490)

**Keep the inline button in TimelineControls** — the floating one is for discoverability, the inline one is for precision when interacting with the scrubber.

### 6. Timeline Simplification (`TimelineControls.vue`)

**Current:** Already has the right structure. Minor cleanup needed.

**Changes:**
- Remove the tooltip/hover label (`scrubber-tooltip`, lines 42-49) — Manus doesn't show tooltips on hover
- Remove `toolTimeline` prop and related marker logic — clean minimal scrubber only
- Remove `currentStep` and `totalSteps` props — step counting is in TaskProgressBar
- Keep emit names as-is: `seekByProgress` (0-100 range), `stepForward`, `stepBackward`, `jumpToLive`

**No new component needed.** `TimelineControls.vue` is the right component — just trim it.

### 7. Terminal Edge-to-Edge (`TerminalContentView.vue`)

**Current:** Wraps in `<ContentContainer :scrollable="false" padding="none">` — padding is already "none".

**Changes:**
- Remove the `ContentContainer` wrapper entirely — terminal renders directly in the viewport
- Add CSS: `scrollbar-width: none` on `.terminal-shell` + `::-webkit-scrollbar { display: none }`
- The xterm.js container fills the full viewport area edge-to-edge

### 8. TaskProgressBar Styling (`TaskProgressBar.vue`)

**Current:** Already close to Manus. Has expand/collapse, step list, step counting, timer.

**Changes (styling only, no structural changes):**
- Collapsed bar: Ensure it matches Manus layout: `[icon] [task description]  [N / M]  [∧]`
  - Currently shows a more complex layout with thumbnail and multiple sections
  - Simplify collapsed view: hide `LiveMiniPreview` when tool panel is open (the panel already shows the viewport)
  - Left-align: status icon (checkmark/spinner/circle) + current step description
  - Right-align: `N / M` counter + chevron
- Step description: Uses `step.description` (from `StepEventData.description`) — correct, no mapping needed
- Step statuses: `StepEventData` has `"pending" | "started" | "running" | "completed" | "failed" | "blocked" | "skipped"`. Map for display:
  - `completed` → green checkmark ✓
  - `running` / `started` → spinner
  - `failed` → red ✕
  - `pending` / `blocked` / `skipped` → numbered circle

---

## Files Modified

| File | Changes |
|------|---------|
| `ToolPanelContent.vue` | Separator `·` → `│`, unified `contentTitleLabel` computed, new Chat/Split buttons replacing Takeover/Minimize, floating JumpToLive overlay, `switchToChat` + `requestWidth` emits |
| `ToolPanel.vue` | Re-emit `switchToChat`, handle `requestWidth` to update panel width |
| `TimelineControls.vue` | Remove tooltip, toolTimeline prop, currentStep/totalSteps props |
| `TerminalContentView.vue` | Remove ContentContainer wrapper, hidden scrollbar CSS |
| `TaskProgressBar.vue` | Simplify collapsed layout (hide thumbnail when panel is open, left-align icon+text, right-align counter+chevron) |
| `ChatPage.vue` | Handle `switchToChat` (collapse panel + focus chat input) |

## Files Created

| File | Purpose |
|------|---------|
| `frontend/src/utils/sessionName.ts` | `deriveSessionName(command?)` utility for terminal session naming |

## Types Modified

| File | Changes |
|------|---------|
| `frontend/src/types/event.ts` | Add `session_name?: string` to `ToolEventData` |
| `frontend/src/types/message.ts` | Add `session_name?: string` to `ToolContent` |

## Components NOT Changed (Removed from scope)

| Component | Reason |
|-----------|--------|
| `ReplayTimeline.vue` | Not used in live code — `TimelineControls.vue` is the actual component |
| `AgentActivityBar.vue` | Not used in `ToolPanelContent` — `TaskProgressBar.vue` is the actual component |
| `LiveViewer.vue` | View routing unchanged |
| `SandboxViewer.vue` | CDP streaming unchanged |
| `KonvaLiveStage.vue` | Canvas layers unchanged |
| `EditorContentView.vue` | Monaco editor unchanged |
| `SearchContentView.vue` | Search results unchanged |

## Edge Cases

| Case | Handling |
|------|---------|
| No steps / empty plan | `TaskProgressBar` already guards: `v-if="plan && plan.steps.length > 0"` (line 500 of ToolPanelContent) |
| Terminal with no command | `deriveSessionName(undefined)` returns `'terminal'` (guard at top of function) |
| Unknown tool type in activity line | `activityHeadline` returns `''` when no `toolDisplay` (line 1128) — fallback already exists |
| Unknown view type in content-title | Falls through to `contentHeaderLabel` which uses existing logic |
| `isLive` at session start (progress=0) | Timeline is hidden via `v-if="showTimeline"` — no timeline shown until tool events arrive |
| All steps completed | Collapsed bar shows last step (array index `steps.length - 1`) with green checkmark |
| Split button on mobile | Hidden via `v-if` — no-op, mobile always shows panel as full overlay |
| `session_name` not provided by backend | Frontend `deriveSessionName()` fallback handles all cases |

## Emit Chain Summary

```
ToolPanelContent
  ├── emit('switchToChat')     → ToolPanel → ChatPage (collapse panel, focus input)
  ├── emit('requestWidth', n)  → ToolPanel (update effectiveWidth for split toggle)
  ├── emit('jumpToRealTime')   → ToolPanel → ChatPage (existing, seek to live)
  ├── emit('hide')             → ToolPanel (existing, close panel)
  └── emit('seekByProgress', n) → ToolPanel → ChatPage (existing, 0-100 range)

TimelineControls
  ├── emit('jumpToLive')       → ToolPanelContent (existing)
  ├── emit('stepForward')      → ToolPanelContent (existing)
  ├── emit('stepBackward')     → ToolPanelContent (existing)
  └── emit('seekByProgress', n) → ToolPanelContent (existing, 0-100 range)
```

## Implementation Notes (Residual Review Fixes)

### R1 — New emits must be registered in `defineEmits`

`ToolPanelContent.vue` line ~1923 `defineEmits` block must add:
```typescript
(e: 'switchToChat'): void,
(e: 'requestWidth', width: number): void,
```

`ToolPanel.vue` `defineEmits` block must add:
```typescript
(e: 'switchToChat'): void,
```

### R2 — Unified content-title bar `v-if` condition

The current `panel-content-header` has `v-if` condition (line 94):
```
v-if="(contentConfig || showReportPresentation || showPlanPresentation) && (!embedded || forceViewType) && !showUrlStatusBar"
```

After merging into a unified bar, the `!showUrlStatusBar` exclusion must be **removed** since the unified bar now handles browser URLs too. New condition:
```
v-if="contentTitleLabel && (!embedded || forceViewType)"
```

This shows the bar whenever there's a title to display (browser URL, filename, session name, "Search", etc.) and the panel is not in compact embedded mode.

### R3 — Remove parent bindings when TimelineControls props are removed

When removing `toolTimeline`, `currentStep`, and `totalSteps` props from `TimelineControls.vue`, also remove the corresponding bindings in `ToolPanelContent.vue` at lines 487-489:
```html
<!-- REMOVE these three lines -->
:tool-timeline="toolTimeline"
:current-step="timelineCurrentStep"
:total-steps="timelineTotalSteps"
```
