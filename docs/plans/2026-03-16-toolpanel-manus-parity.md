# ToolPanel Manus-Parity Standardization — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task and use frontedn-design skill too .

**Goal:** Standardize all ToolPanel views to match Manus "Computer" aesthetic — unified context bar, consistent terminal fonts/colors, flat loading backgrounds.

**Architecture:** Restyle `.panel-content-header` to match `.url-status-bar` visually. Update `contentHeaderLabel` to show view-appropriate context text. Align terminal font stacks and dark themes. Flatten loading state backgrounds.

**Tech Stack:** Vue 3 (Composition API, `<script setup>`), Tailwind CSS, CSS variables, xterm.js

---

### Task 1: Unify Context Bar CSS

**Files:**
- Modify: `frontend/src/components/ToolPanelContent.vue:93-95` (template)
- Modify: `frontend/src/components/ToolPanelContent.vue:2156-2159` (CSS)

**Step 1: Replace inline Tailwind classes on `.panel-content-header` with unified styling**

Change line 95 from:
```html
class="panel-content-header h-[36px] flex items-center justify-center px-3 w-full bg-[var(--background-white-main)] border-b border-[var(--border-light)] rounded-t-[12px] relative">
```
to:
```html
class="panel-content-header">
```

**Step 2: Replace `.panel-content-header` CSS block (lines 2156-2159) with unified context bar styling**

Replace:
```css
/* ===== CONTENT HEADER ===== */
.panel-content-header {
  box-shadow: inset 0 1px 0 0 var(--border-white);
}
```

With:
```css
/* ===== CONTENT HEADER (unified context bar — matches URL status bar) ===== */
.panel-content-header {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  width: 100%;
  height: 32px;
  padding: 0 12px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-light);
  border-radius: 12px 12px 0 0;
  background: color-mix(in srgb, var(--fill-tsp-gray-main) 50%, transparent);
}

:global(.dark) .panel-content-header {
  background: rgba(255, 255, 255, 0.02);
  border-bottom-color: rgba(255, 255, 255, 0.05);
}
```

**Step 3: Update center label styling (line 98) to match URL bar text**

Change line 98 from:
```html
<div class="text-[var(--text-tertiary)] text-sm font-medium max-w-[80%] flex items-center justify-center gap-1.5 min-w-0">
```
to:
```html
<div class="context-bar-label">
```

Add this CSS after the `.panel-content-header` block:
```css
.context-bar-label {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  max-width: 80%;
  min-width: 0;
  font-size: 13px;
  font-weight: 400;
  letter-spacing: 0.01em;
  color: var(--text-tertiary);
}

.context-bar-label > span {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

:global(.dark) .context-bar-label {
  color: color-mix(in srgb, var(--text-tertiary) 70%, transparent);
}
```

**Step 4: Verify visually**

Run: `cd frontend && bun run type-check`
Expected: exit 0, no errors

**Step 5: Commit**

```bash
git add frontend/src/components/ToolPanelContent.vue
git commit -m "fix(ui): unify content header bar to match URL status bar styling"
```

---

### Task 2: Update Context Text Per View

**Files:**
- Modify: `frontend/src/components/ToolPanelContent.vue:1158-1186` (`contentHeaderLabel` computed)

**Step 1: Replace `contentHeaderLabel` computed**

Replace lines 1158-1186 with:
```javascript
// Content header label — unified context bar text (Manus-style)
const contentHeaderLabel = computed(() => {
  // Report streaming/display takes priority
  if (showReportPresentation.value) {
    if (props.isSummaryStreaming) return 'Writing report...';
    return 'Report';
  }
  if (showPlanPresentation.value) {
    if (props.isPlanStreaming) return 'Creating plan...';
    return 'Plan';
  }
  // Terminal: show working directory from PS1 prompt
  if (currentViewType.value === 'terminal') {
    const content = props.toolContent?.content;
    if (content?.console && Array.isArray(content.console) && content.console.length > 0) {
      const lastRecord = content.console[content.console.length - 1];
      const ps1 = lastRecord?.ps1;
      if (typeof ps1 === 'string' && ps1.trim()) return ps1.trim();
    }
    const execDir = props.toolContent?.args?.exec_dir;
    if (typeof execDir === 'string' && execDir) {
      return execDir.replace(/^\/home\/ubuntu/, '~');
    }
    return 'Terminal';
  }
  // Editor: show filename
  if (currentViewType.value === 'editor') {
    const nameArg = props.toolContent?.args?.filename;
    if (typeof nameArg === 'string' && nameArg) return nameArg;
    if (resolvedFilePath.value) {
      const parts = resolvedFilePath.value.split('/');
      const name = parts[parts.length - 1] || '';
      if (name) return name;
    }
    return 'Editor';
  }
  // Search: show query
  if (currentViewType.value === 'search') {
    const q = searchQuery.value;
    if (typeof q === 'string' && q) return `Searching "${q}"`;
    return 'Search';
  }
  // Chart: show chart title or fallback
  if (currentViewType.value === 'chart') {
    return 'Chart';
  }
  // Deals: show query
  if (currentViewType.value === 'deals') {
    const q = props.toolContent?.args?.query;
    if (typeof q === 'string' && q) return `Finding deals: "${q}"`;
    return 'Deal Finder';
  }
  // Canvas: show project name
  if (currentViewType.value === 'canvas') {
    const name = props.toolContent?.args?.name || props.toolContent?.args?.project_id;
    if (typeof name === 'string' && name) return name;
    return 'Canvas';
  }
  // Wide research
  if (currentViewType.value === 'wide_research') {
    const q = searchQuery.value;
    if (typeof q === 'string' && q) return `Researching "${q}"`;
    return 'Deep Research';
  }
  // Generic: tool display name
  return toolDisplay.value?.displayName || '';
});
```

**Step 2: Remove icon components from context bar template**

In lines 99-113, the `FileText`, `BarChart3`, and `Palette` icons add visual noise to the clean context bar. Remove them — the context text is sufficient:

Replace lines 97-115:
```html
          <!-- Center: Operation label (Manus-style minimal — no status badges, timers, or step counters) -->
          <div class="text-[var(--text-tertiary)] text-sm font-medium max-w-[80%] flex items-center justify-center gap-1.5 min-w-0">
            <FileText
              v-if="showReportPresentation"
              :size="14"
              class="flex-shrink-0 text-[var(--text-tertiary)]"
            />
            <BarChart3
              v-else-if="currentViewType === 'chart'"
              :size="14"
              class="flex-shrink-0 text-[var(--text-tertiary)]"
            />
            <Palette
              v-else-if="currentViewType === 'canvas'"
              :size="14"
              class="flex-shrink-0 text-[var(--text-tertiary)]"
            />
            <span class="truncate">{{ contentHeaderLabel }}</span>
          </div>
```

With:
```html
          <!-- Center: Context text (Manus-style — plain centered text, no icons) -->
          <div class="context-bar-label">
            <span>{{ contentHeaderLabel }}</span>
          </div>
```

**Step 3: Verify**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: exit 0

**Step 4: Commit**

```bash
git add frontend/src/components/ToolPanelContent.vue
git commit -m "fix(ui): show view-appropriate context text in unified context bar"
```

---

### Task 3: Standardize Terminal Font Family

**Files:**
- Modify: `frontend/src/components/toolViews/TerminalContentView.vue:179,312`
- Modify: `frontend/src/components/toolViews/TerminalLiveView.vue:87`

**Step 1: Define the canonical monospace font stack**

The shared stack (JetBrains Mono first, broadest fallback):
```
'JetBrains Mono', 'Fira Code', 'SF Mono', Menlo, Monaco, 'Cascadia Code', monospace
```

**Step 2: Update TerminalContentView.vue**

In line 179 (JS Terminal config), change:
```javascript
fontFamily: "'SF Mono', Menlo, Monaco, 'Cascadia Code', 'Courier New', monospace",
```
to:
```javascript
fontFamily: "'JetBrains Mono', 'Fira Code', 'SF Mono', Menlo, Monaco, 'Cascadia Code', monospace",
```

In line 312 (CSS `.terminal-shell`), change:
```css
font-family: 'SF Mono', Menlo, Monaco, 'Cascadia Code', 'Courier New', monospace;
```
to:
```css
font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Menlo, Monaco, 'Cascadia Code', monospace;
```

**Step 3: Verify TerminalLiveView.vue is already correct**

Read line 87 of `TerminalLiveView.vue` — it already uses `'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace`. Add `'SF Mono', Menlo, Monaco` to the fallback chain for consistency:

Change:
```javascript
fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
```
to:
```javascript
fontFamily: "'JetBrains Mono', 'Fira Code', 'SF Mono', Menlo, Monaco, 'Cascadia Code', monospace",
```

**Step 4: Commit**

```bash
git add frontend/src/components/toolViews/TerminalContentView.vue frontend/src/components/toolViews/TerminalLiveView.vue
git commit -m "fix(ui): standardize terminal font stack across live and static views"
```

---

### Task 4: Standardize Terminal Dark Theme

**Files:**
- Modify: `frontend/src/components/toolViews/TerminalContentView.vue:71-94`

**Step 1: Replace dark theme in TerminalContentView to match TerminalLiveView's Tokyo Night**

Replace lines 71-94:
```javascript
// Dark theme
const darkTheme = {
  background: '#1a1a1a',
  foreground: '#e5e7eb',
  cursor: '#e5e7eb',
  cursorAccent: '#1a1a1a',
  selectionBackground: 'rgba(0, 0, 0, 0.3)',
  selectionForeground: '#e5e7eb',
  black: '#1f2937',
  red: '#f87171',
  green: '#4ade80',
  yellow: '#facc15',
  blue: '#60a5fa',
  magenta: '#c084fc',
  cyan: '#22d3ee',
  white: '#f8f9fa',
  brightBlack: '#9ca3af',
  brightRed: '#fca5a5',
  brightGreen: '#86efac',
  brightYellow: '#fde047',
  brightBlue: '#93c5fd',
  brightMagenta: '#d8b4fe',
  brightCyan: '#67e8f9',
  brightWhite: '#ffffff',
};
```

With Tokyo Night palette (matching TerminalLiveView):
```javascript
// Dark theme (Tokyo Night — shared with TerminalLiveView)
const darkTheme = {
  background: '#1a1b26',
  foreground: '#c0caf5',
  cursor: '#c0caf5',
  cursorAccent: '#1a1b26',
  selectionBackground: '#33467c',
  selectionForeground: '#c0caf5',
  black: '#15161e',
  red: '#f7768e',
  green: '#9ece6a',
  yellow: '#e0af68',
  blue: '#7aa2f7',
  magenta: '#bb9af7',
  cyan: '#7dcfff',
  white: '#a9b1d6',
  brightBlack: '#414868',
  brightRed: '#f7768e',
  brightGreen: '#9ece6a',
  brightYellow: '#e0af68',
  brightBlue: '#7aa2f7',
  brightMagenta: '#bb9af7',
  brightCyan: '#7dcfff',
  brightWhite: '#c0caf5',
};
```

**Step 2: Update CSS dark background to match**

In the CSS (around line 310, `.terminal-shell` background), the dark mode background reference `var(--bolt-elements-bg-depth-1)` should resolve to `#1a1b26`. Check if this CSS var exists. If it doesn't or resolves differently, add an explicit override:

After the `.terminal-shell` block, ensure there's:
```css
.terminal-shell.dark-mode {
  background: #1a1b26;
}
```

Also update the empty state overlay dark background (line 394-398) from `rgba(26, 26, 26, 0.9)` to `rgba(26, 27, 38, 0.9)` to match:
```css
:global(.dark) .terminal-view :deep(.empty-state.overlay) {
  background: rgba(26, 27, 38, 0.9);
}
```

**Step 3: Commit**

```bash
git add frontend/src/components/toolViews/TerminalContentView.vue
git commit -m "fix(ui): unify terminal dark theme to Tokyo Night palette"
```

---

### Task 5: Flatten Loading State Background

**Files:**
- Modify: `frontend/src/components/toolViews/shared/LoadingState.vue:89-94`

**Step 1: Replace gradient with flat background**

Change lines 89-94:
```css
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    to bottom,
    var(--background-secondary),
    var(--background-surface)
  );
  padding: var(--space-12);
}
```

To:
```css
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: var(--background-white-main);
  padding: var(--space-12);
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/toolViews/shared/LoadingState.vue
git commit -m "fix(ui): flatten loading state background for consistency with content views"
```

---

### Task 6: Final Verification

**Step 1: Run full frontend checks**

```bash
cd frontend && bun run lint && bun run type-check
```

Expected: Both pass with no errors.

**Step 2: Visual verification**

1. Navigate to a completed session with terminal commands
2. Verify context bar shows `ubuntu@sandbox:~ $` for terminal
3. Verify context bar shows filename for editor
4. Verify context bar styling matches URL bar (semi-transparent gray background, 13px centered text)
5. Verify terminal dark mode uses Tokyo Night colors
6. Verify loading states have flat white background
7. Take before/after screenshots

**Step 3: Final commit (if needed)**

```bash
git add -A
git commit -m "chore(ui): final visual polish for Manus-parity context bar"
```
