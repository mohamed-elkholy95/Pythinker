# Manus-Style Tool View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt Manus AI's "Computer" tool view UX into Pythinker's existing tool panel.

**Architecture:** Modify 7 existing Vue components + 1 new utility file. No new components needed — existing `TimelineControls`, `TaskProgressBar`, and `ToolPanelContent` already implement ~70% of the Manus UX. Changes are: separator restyle, unified content-title bar, header button swap, floating jump-to-live overlay, terminal edge-to-edge CSS, and timeline/task-bar cleanup.

**Tech Stack:** Vue 3 Composition API, TypeScript, Lucide icons, xterm.js

**Spec:** `docs/superpowers/specs/2026-03-19-manus-style-tool-view-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `frontend/src/utils/sessionName.ts` | **Create** | `deriveSessionName()` utility for terminal session naming |
| `frontend/src/types/event.ts` | Modify (line 150) | Add `session_name?: string` to `ToolEventData` |
| `frontend/src/types/message.ts` | Modify (line 78) | Add `session_name?: string` to `ToolContent` |
| `frontend/src/components/ToolPanelContent.vue` | Modify | Separator, unified content-title bar, header buttons, floating jump-to-live, emit registration |
| `frontend/src/components/ToolPanel.vue` | Modify | Re-emit `switchToChat` |
| `frontend/src/pages/ChatPage.vue` | Modify | Handle `switchToChat` (collapse panel + focus chat), handle split width |
| `frontend/src/components/timeline/TimelineControls.vue` | Modify | Remove tooltip, unused props |
| `frontend/src/components/toolViews/TerminalContentView.vue` | Modify | Remove ContentContainer wrapper, hidden scrollbar CSS |
| `frontend/src/components/TaskProgressBar.vue` | Modify | Hide thumbnail when tool panel is open |

---

### Task 1: Types + Session Name Utility

**Files:**
- Create: `frontend/src/utils/sessionName.ts`
- Modify: `frontend/src/types/event.ts:150`
- Modify: `frontend/src/types/message.ts:78`

- [ ] **Step 1: Add `session_name` to `ToolEventData`**

In `frontend/src/types/event.ts`, after line 149 (`confirmation_state?: string;`), add:

```typescript
  // Terminal session name (optional, from backend agent)
  session_name?: string;
```

- [ ] **Step 2: Add `session_name` to `ToolContent`**

In `frontend/src/types/message.ts`, after line 78 (`confirmation_state?: string;`), add:

```typescript
  // Terminal session name (from backend or derived by frontend)
  session_name?: string;
```

- [ ] **Step 3: Create `deriveSessionName` utility**

Create `frontend/src/utils/sessionName.ts`:

```typescript
/**
 * Derive a human-readable terminal session name from a shell command.
 * Used as fallback when backend doesn't provide session_name.
 */
export function deriveSessionName(command: string | undefined): string {
  if (!command) return 'terminal'

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

  return cmd.replace(/[^a-zA-Z0-9]/g, '_') || 'terminal'
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check`
Expected: No new errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add frontend/src/utils/sessionName.ts frontend/src/types/event.ts frontend/src/types/message.ts
git commit -m "feat(types): add session_name field and deriveSessionName utility"
```

---

### Task 2: Activity Line Separator

**Files:**
- Modify: `frontend/src/components/ToolPanelContent.vue:46`

- [ ] **Step 1: Change separator from middot to pipe**

In `ToolPanelContent.vue` line 46, change:

```html
<span v-if="activitySubtitle" class="panel-activity-separator">&middot;</span>
```

To:

```html
<span v-if="activitySubtitle" class="panel-activity-separator">│</span>
```

- [ ] **Step 2: Verify**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ToolPanelContent.vue
git commit -m "style(panel): change activity separator from middot to pipe (Manus-style)"
```

---

### Task 3: Unified Content-Title Bar

**Files:**
- Modify: `frontend/src/components/ToolPanelContent.vue:86-100, 1142-1212, 1345-1349`

The current `showUrlStatusBar` always returns `false` (line 1348), so the url-status-bar div (line 87) is dead code. The `contentHeaderLabel` computed (line 1142) already handles terminal, editor, search, chart, deals, canvas, wide_research. We need to:
1. Add browser URL handling to `contentHeaderLabel`
2. Add terminal session name support
3. Remove the dead `url-status-bar` div
4. Fix the `v-if` condition on `panel-content-header`

- [ ] **Step 1: Update `contentHeaderLabel` to handle browser URL**

In `ToolPanelContent.vue`, find the `contentHeaderLabel` computed (line 1142). Add browser URL handling after the plan presentation check (after line 1150 `return 'Plan';`). Insert before the terminal block:

```typescript
  // Browser: show URL
  if (currentViewType.value === 'live_preview') {
    return resolvedBrowserUrl.value || '/'
  }
```

**Important:** Keep ALL existing branches below (terminal, editor, search, chart, deals, canvas, wide_research, generic). Only insert this new block above them.

- [ ] **Step 2: Add terminal session name to `contentHeaderLabel`**

Import `deriveSessionName` near the other utility imports in the script section:

```typescript
import { deriveSessionName } from '@/utils/sessionName';
```

Replace ONLY the terminal block (lines 1152-1169) within `contentHeaderLabel`. Keep all other branches (editor at 1171, search at 1182, chart at 1188, etc.) untouched:

```typescript
  // Terminal: show session name or working directory
  if (currentViewType.value === 'terminal') {
    // Prefer explicit session name from backend
    const sessionName = props.toolContent?.session_name
    if (sessionName) return sessionName
    // Derive from command as fallback
    const cmd = props.toolContent?.command
    if (cmd) {
      const derived = deriveSessionName(cmd)
      if (derived !== 'terminal') return derived
    }
    // Existing PS1 extraction fallback
    const content = props.toolContent?.content;
    if (content?.console && Array.isArray(content.console) && content.console.length > 0) {
      const lastRecord = content.console[content.console.length - 1];
      const ps1 = lastRecord?.ps1;
      if (typeof ps1 === 'string' && ps1.trim()) {
        let cleanedPs1 = stripCmdMarkers(ps1).trim();
        if (cleanedPs1 && !cleanedPs1.endsWith('$')) cleanedPs1 += ' $';
        return cleanedPs1;
      }
    }
    const execDir = props.toolContent?.args?.exec_dir;
    if (typeof execDir === 'string' && execDir) {
      return execDir.replace(/^\/home\/ubuntu/, '~');
    }
    return 'Terminal';
  }
```

- [ ] **Step 3: Remove dead `url-status-bar` div**

Remove lines 86-89:
```html
        <!-- URL Status Bar (browser views — replaces content header) -->
        <div v-if="showUrlStatusBar" class="url-status-bar">
          <span class="url-status-text">{{ resolvedBrowserUrl || '/' }}</span>
        </div>
```

- [ ] **Step 4: Simplify `panel-content-header` v-if condition**

The old condition at line 94 was:
```html
v-if="(contentConfig || showReportPresentation || showPlanPresentation) && (!embedded || forceViewType) && !showUrlStatusBar"
```

Since we removed the URL status bar, the `!showUrlStatusBar` check is no longer needed. Also, `contentHeaderLabel` now covers browser views. Change to:

```html
v-if="(contentHeaderLabel || contentConfig || showReportPresentation || showPlanPresentation) && (!embedded || forceViewType)"
```

This shows the bar whenever there's a title to display (browser URL, filename, session name, etc.).

- [ ] **Step 5: Remove `showUrlStatusBar` computed and related CSS**

Remove lines 1345-1349 (the `showUrlStatusBar` computed). Also search the `<style>` section for `.url-status-bar` and `.url-status-text` CSS rules and remove them.

- [ ] **Step 6: Verify**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check && bun run lint`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/ToolPanelContent.vue
git commit -m "feat(panel): unified content-title bar with session names and browser URL"
```

---

### Task 4: Header Control Buttons

**Files:**
- Modify: `frontend/src/components/ToolPanelContent.vue:50-73, 521, 1923-1929`
- Modify: `frontend/src/components/ToolPanel.vue:42-46, 99-105`
- Modify: `frontend/src/pages/ChatPage.vue:486-514`

- [ ] **Step 1: Update Lucide imports in ToolPanelContent**

In `ToolPanelContent.vue`, update the Lucide import (line 521). Keep `MonitorUp` (moved to floating viewport button). Replace `Minimize2` with new icons:

Replace:
```typescript
import { Minimize2, MonitorUp, X, Loader2, FileText, PencilLine } from 'lucide-vue-next';
```

With:
```typescript
import { MessageSquare, Columns2, MonitorUp, X, Loader2, FileText, PencilLine } from 'lucide-vue-next';
```

- [ ] **Step 2: Replace header control buttons**

Replace the control buttons section (lines 50-73) with:

```html
        <div class="flex items-center gap-1">
          <!-- Chat: collapse panel, focus chat -->
          <button
            class="panel-control-btn"
            @click="switchToChat"
            aria-label="Switch to chat"
          >
            <MessageSquare class="w-4 h-4" />
          </button>
          <!-- Split: toggle 50/50 width (desktop only) -->
          <button
            v-if="!isMobilePanel"
            class="panel-control-btn"
            @click="toggleSplit"
            aria-label="Toggle split view"
          >
            <Columns2 class="w-4 h-4" />
          </button>
          <!-- Close -->
          <button
            class="panel-control-btn"
            @click="hide"
            aria-label="Close"
          >
            <X class="w-4 h-4" />
          </button>
        </div>
```

- [ ] **Step 3: Add `switchToChat`, `toggleSplit`, and `isMobilePanel`**

Add to the script section (place near the existing event handler section around line 1930):

```typescript
// Mobile detection for split button visibility
// Use a unique name to avoid conflicts with any parent-level isMobile
const isMobilePanel = ref(window.innerWidth < 1024)
const onPanelResize = () => { isMobilePanel.value = window.innerWidth < 1024 }
```

Add `onPanelResize` listener into the existing `onMounted`/`onUnmounted` blocks (find them in the file and add the calls alongside existing listeners, DO NOT create new onMounted/onUnmounted blocks):

```typescript
// Inside existing onMounted:
window.addEventListener('resize', onPanelResize)

// Inside existing onUnmounted:
window.removeEventListener('resize', onPanelResize)
```

Add split toggle logic:

```typescript
// Split view state
const isSplitMode = ref(false)

const switchToChat = () => {
  emit('switchToChat')
}

const toggleSplit = () => {
  isSplitMode.value = !isSplitMode.value
  // Signal parent to change width: -1 = 50% split, 0 = restore previous
  emit('requestWidth', isSplitMode.value ? -1 : 0)
}
```

- [ ] **Step 4: Register new emits in ToolPanelContent**

In `ToolPanelContent.vue` line 1923, update `defineEmits`:

```typescript
const emit = defineEmits<{
  (e: 'jumpToRealTime'): void,
  (e: 'hide'): void,
  (e: 'stepForward'): void,
  (e: 'stepBackward'): void,
  (e: 'seekByProgress', progress: number): void,
  (e: 'switchToChat'): void,
  (e: 'requestWidth', width: number): void,
}>();
```

- [ ] **Step 5: Move Takeover button to floating position in viewport**

In the content area template (inside the `relative flex flex-col overflow-hidden` container, near where LiveViewer is rendered — around line 460), add a floating takeover button:

```html
          <!-- Floating takeover button (moved from header) -->
          <button
            v-if="!!props.sessionId && !embedded"
            class="absolute bottom-3 right-3 z-10 p-2 rounded-lg bg-[var(--fill-tsp-gray-main)] hover:bg-[var(--fill-tsp-gray-hover)] transition-colors opacity-60 hover:opacity-100"
            @click="takeOver"
            :disabled="takeoverLoading"
            aria-label="Open takeover"
          >
            <MonitorUp class="w-4 h-4 text-[var(--icon-secondary)]" />
          </button>
```

- [ ] **Step 6: Register `switchToChat` emit in ToolPanel**

In `ToolPanel.vue` line 99, update `defineEmits`:

```typescript
const emit = defineEmits<{
  (e: 'jumpToRealTime'): void
  (e: 'panelStateChange', isOpen: boolean, userAction: boolean): void
  (e: 'timelineStepForward'): void
  (e: 'timelineStepBackward'): void
  (e: 'timelineSeek', progress: number): void
  (e: 'switchToChat'): void
}>()
```

- [ ] **Step 7: Wire `switchToChat` in ToolPanel template**

In `ToolPanel.vue` around line 42-46 (where `@hide`, `@jumpToRealTime` etc. are bound), add:

```html
        @switchToChat="emit('switchToChat')"
```

For `requestWidth`, handle it locally in ToolPanel since panel width is managed here. Add the handler and binding:

Template binding:
```html
        @requestWidth="handleRequestWidth"
```

Script handler:
```typescript
// Width before split (for restore)
const preSplitWidth = ref<number>(0)

const handleRequestWidth = (signal: number) => {
  const parent = toolPanelContentRef.value?.$el?.parentElement
  if (signal === -1 && parent) {
    // 50% split: save current width, set to half
    preSplitWidth.value = panelWidth.value
    // panelWidth is a computed from props.size — we need to emit upward
    emit('timelineSeek', -1) // WRONG — we need a new approach
  }
}
```

**Actually, the width is controlled by `toolPanelSize` in `ChatPage.vue` (line 751).** So `requestWidth` must bubble all the way to `ChatPage`. Add to `ToolPanel.vue` defineEmits:

```typescript
  (e: 'requestWidth', width: number): void
```

And re-emit: `@requestWidth="(w: number) => emit('requestWidth', w)"`

- [ ] **Step 8: Handle `switchToChat` and `requestWidth` in ChatPage**

In `ChatPage.vue`, on the `<ToolPanel>` element (line 486), add:

```html
        @switchToChat="handleSwitchToChat"
        @requestWidth="handleRequestWidth"
```

Add handlers in the script:

```typescript
// Manus-style: switch to chat (collapse panel, focus input)
const handleSwitchToChat = () => {
  toolPanel.value?.hideToolPanel(true)
}

// Manus-style: split view width control
const preSplitWidth = ref(0)
const handleRequestWidth = (signal: number) => {
  if (signal === -1) {
    // 50% split
    preSplitWidth.value = toolPanelSize.value
    toolPanelSize.value = Math.floor(window.innerWidth * 0.5)
  } else if (signal === 0) {
    // Restore previous
    toolPanelSize.value = preSplitWidth.value || 0
  } else {
    toolPanelSize.value = signal
  }
}
```

Note: `toolPanel` ref already exists (line 486 `ref="toolPanel"`). `toolPanelSize` is reactive state (line 751).

- [ ] **Step 9: Verify**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check && bun run lint`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/ToolPanelContent.vue frontend/src/components/ToolPanel.vue frontend/src/pages/ChatPage.vue
git commit -m "feat(panel): replace header buttons with Chat/Split/Close (Manus-style)"
```

---

### Task 5: Floating "Jump to Live" Button

**Files:**
- Modify: `frontend/src/components/ToolPanelContent.vue`

Note: `showTimeline` is a prop of `ToolPanelContent` (confirmed at line 586: `showTimeline?: boolean`).

- [ ] **Step 1: Add floating button template**

Inside the content container div (the `relative flex flex-col overflow-hidden` div at line 78), after the content area and before the timeline controls (line 477), add:

```html
        <!-- Floating "Jump to live" button (Manus-style) -->
        <Transition name="fade-jump">
          <button
            v-if="showTimeline && !isTimelineLive"
            class="jump-to-live-floating"
            @click="jumpToRealTime"
          >
            <Play class="w-3.5 h-3.5" />
            <span>Jump to live</span>
          </button>
        </Transition>
```

- [ ] **Step 2: Add `isTimelineLive` computed and Play import**

Add `Play` to the Lucide import:
```typescript
import { MessageSquare, Columns2, MonitorUp, X, Loader2, FileText, PencilLine, Play } from 'lucide-vue-next';
```

Add computed:
```typescript
const isTimelineLive = computed(() => {
  return props.realTime || (props.timelineProgress ?? 0) >= 99.5
})
```

- [ ] **Step 3: Add CSS for the floating button**

Add to the `<style>` section (use unique transition name `fade-jump` to avoid conflicts with existing transitions):

```css
.jump-to-live-floating {
  position: absolute;
  bottom: 56px; /* Above timeline controls */
  left: 50%;
  transform: translateX(-50%);
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
  color: white;
  border: none;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}
.jump-to-live-floating:hover {
  background: rgba(0, 0, 0, 0.85);
}
.fade-jump-enter-active,
.fade-jump-leave-active {
  transition: opacity 0.15s ease;
}
.fade-jump-enter-from,
.fade-jump-leave-to {
  opacity: 0;
}
```

- [ ] **Step 4: Verify**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check && bun run lint`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ToolPanelContent.vue
git commit -m "feat(panel): add floating 'Jump to live' overlay button (Manus-style)"
```

---

### Task 6: Timeline Simplification

**Files:**
- Modify: `frontend/src/components/timeline/TimelineControls.vue`
- Modify: `frontend/src/components/ToolPanelContent.vue:487-489`

- [ ] **Step 1: Remove tooltip from TimelineControls template**

In `TimelineControls.vue`, remove the tooltip block (lines 42-49):

```html
          <!-- Floating Tooltip (timestamp + tool name on hover/drag) -->
          <div
            v-if="tooltipVisible"
            class="scrubber-tooltip"
            :style="{ left: `${tooltipPosition}%` }"
          >
            <span v-if="tooltipToolLabel" class="scrubber-tooltip-label">{{ tooltipToolLabel }}</span>
            <span v-if="tooltipTimestamp" class="scrubber-tooltip-time">{{ tooltipTimestamp }}</span>
          </div>
```

- [ ] **Step 2: Remove unused props from TimelineControls**

In `TimelineControls.vue`, remove from the `Props` interface (lines 105-110):

```typescript
  /** Tool timeline entries for markers and hover labels */
  toolTimeline?: ToolContent[]
  /** 1-based current step index (0 if nothing selected) */
  currentStep?: number
  /** Total number of steps in the tool timeline */
  totalSteps?: number
```

Also remove imports only used by tooltip:
- `import type { ToolContent }` (line 92) — remove if no other usage
- `import { getToolDisplay }` (line 95) — remove if only used for tooltip

- [ ] **Step 3: Clean up tooltip-related script code**

Remove ALL tooltip-related refs, computeds, and handlers from the script section. These include (verify each exists before removing):
- `tooltipVisible` ref
- `tooltipPosition` ref / computed
- `tooltipToolLabel` computed
- `tooltipTimestamp` computed
- `hoveredToolIndex` / `hoveredTool` computed
- `handleMouseMove`, `handleMouseEnter`, `handleMouseLeave` functions
- Any `_formattedTimestamp` or `normalizeTimestampSeconds` usage only for tooltip

Also remove `.scrubber-tooltip`, `.scrubber-tooltip-label`, `.scrubber-tooltip-time` CSS classes from the `<style>` section.

**Verify:** After removal, the `@mouseenter`, `@mouseleave`, `@mousemove` event bindings on the scrubber track (lines 37-39) must also be removed since their handlers are gone.

- [ ] **Step 4: Remove corresponding bindings in ToolPanelContent**

In `ToolPanelContent.vue`, remove lines 487-489:

```html
            :tool-timeline="toolTimeline"
            :current-step="timelineCurrentStep"
            :total-steps="timelineTotalSteps"
```

- [ ] **Step 5: Verify**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check && bun run lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/timeline/TimelineControls.vue frontend/src/components/ToolPanelContent.vue
git commit -m "refactor(timeline): simplify TimelineControls, remove tooltip and unused props"
```

---

### Task 7: Terminal Edge-to-Edge

**Files:**
- Modify: `frontend/src/components/toolViews/TerminalContentView.vue:1-14`

- [ ] **Step 1: Remove ContentContainer wrapper**

Replace the template (lines 1-14):

```html
<template>
  <ContentContainer :scrollable="false" padding="none" class="terminal-view">
    <div class="terminal-body">
      <div class="terminal-shell" :class="{ 'dark-mode': isDarkMode }">
        <div ref="terminalRef" class="terminal-surface"></div>
        <EmptyState
          v-if="!content"
          :message="emptyLabel"
          :icon="emptyIcon"
          overlay
        />
      </div>
    </div>
  </ContentContainer>
</template>
```

With:

```html
<template>
  <div class="terminal-view">
    <div class="terminal-body">
      <div class="terminal-shell" :class="{ 'dark-mode': isDarkMode }">
        <div ref="terminalRef" class="terminal-surface"></div>
        <EmptyState
          v-if="!content"
          :message="emptyLabel"
          :icon="emptyIcon"
          overlay
        />
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Remove ContentContainer import**

In the script section, find and remove:
```typescript
import ContentContainer from './shared/ContentContainer.vue';
```

(Only remove if no other usage of `ContentContainer` exists in this file.)

- [ ] **Step 3: Add hidden scrollbar CSS**

In the `<style>` section, add:

```css
.terminal-shell {
  scrollbar-width: none; /* Firefox */
}
.terminal-shell::-webkit-scrollbar {
  display: none; /* Chrome, Safari */
}
```

Also ensure `.terminal-view` has full dimensions:
```css
.terminal-view {
  height: 100%;
  width: 100%;
  overflow: hidden;
}
```

- [ ] **Step 4: Verify**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check && bun run lint`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/toolViews/TerminalContentView.vue
git commit -m "style(terminal): edge-to-edge layout with hidden scrollbar (Manus-style)"
```

---

### Task 8: TaskProgressBar Cleanup

**Files:**
- Modify: `frontend/src/components/TaskProgressBar.vue:329`

- [ ] **Step 1: Hide LiveMiniPreview when tool panel is open**

The `TaskProgressBar` receives a `compact` prop (set to `true` by ToolPanelContent at line 509). When the tool panel is open, the thumbnail is redundant.

In `TaskProgressBar.vue` line 329, the actual computed is:
```typescript
const showCollapsedThumbnail = computed(() => props.showThumbnail)
```

Change to:
```typescript
const showCollapsedThumbnail = computed(() => props.showThumbnail && !props.compact)
```

This hides the thumbnail when `compact=true` (i.e., when rendered inside the tool panel), matching the clean Manus collapsed bar: `[icon] [description] [N/M] [chevron]`.

- [ ] **Step 2: Verify**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check && bun run lint`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TaskProgressBar.vue
git commit -m "style(taskbar): hide thumbnail in compact mode when panel is open"
```

---

### Task 9: Final Verification

- [ ] **Step 1: Full type check**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check`
Expected: PASS with zero errors

- [ ] **Step 2: Full lint check**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run lint`
Expected: PASS with zero errors

- [ ] **Step 3: Visual review**

Start the dev stack and verify:
- Activity line shows "Pythinker is using [Tool] │ [action]" with pipe separator
- Content-title bar shows filename for editor, session name for terminal, "Search" for search, URL for browser
- Header has Chat + Split + Close buttons (Takeover moved to floating viewport button)
- Floating "Jump to live" appears when timeline is scrubbed away from live
- Timeline has step buttons + scrubber + live indicator (no tooltip on hover)
- Terminal renders edge-to-edge with no scrollbar
- TaskProgressBar collapsed view is clean: icon + text + counter + chevron (no thumbnail when panel is open)

Run: `cd /Users/panda/Desktop/Projects/Pythinker && ./dev.sh watch`

- [ ] **Step 4: Fix any remaining issues**

If lint or type-check finds issues, fix them and commit each fix separately with descriptive messages:

```bash
git add <specific-files>
git commit -m "fix(panel): <description of fix>"
```
