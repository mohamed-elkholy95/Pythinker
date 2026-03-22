# Mobile Responsive Enhancement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix and enhance mobile responsiveness across TaskProgressBar, LiveMiniPreview, ReportModal, ToolPanelContent, and ChatPage for phone screens (360-430px).

**Architecture:** CSS-first approach using scoped `@media` queries and Tailwind responsive classes. No new composables or component restructuring — targeted fixes to existing `<style scoped>` blocks and minimal template adjustments. Consistent breakpoint: `max-width: 639px` (below Tailwind `sm:`) for phone, `max-width: 767px` for small tablet.

**Tech Stack:** Vue 3 SFC scoped CSS, Tailwind CSS v4, existing Lucide icons

---

### Task 1: TaskProgressBar — Mobile collapsed bar and expanded panel

**Files:**
- Modify: `frontend/src/components/TaskProgressBar.vue`

**Step 1: Fix collapsed bar on mobile**

The collapsed bar has a floating thumbnail that causes text overlap on phones. The padding-left is already responsive (80px mobile, 124px desktop at line 747-754). But the thumbnail itself at 56x40 is too small to be useful on phones — hide it on very small screens and reclaim space.

Add to `<style scoped>` after line 754:

```css
/* ===== MOBILE OVERRIDES ===== */
@media (max-width: 479px) {
  /* Hide floating thumbnail on very small phones — not enough room */
  .live-preview-thumbnail-floating {
    display: none;
  }
  .progress-bar-collapsed.has-thumbnail {
    padding-left: 16px;
  }
}
```

**Step 2: Fix expanded header stacking on mobile**

The expanded header (line 7-64) uses `flex items-start gap-4` with 3 columns: LiveMiniPreview + title + buttons. On phones, this crushes. Stack vertically.

Add to `<style scoped>`:

```css
@media (max-width: 639px) {
  .expanded-header .flex.items-start {
    flex-direction: column;
    gap: 12px;
  }

  /* Make action buttons row sit at the top-right of the expanded header */
  .expanded-header .flex.items-center.gap-1.flex-shrink-0 {
    position: absolute;
    top: 12px;
    right: 12px;
  }

  .expanded-header {
    position: relative;
    padding: 14px 16px;
  }

  /* Larger touch targets for action buttons */
  .action-btn {
    padding: 10px;
    min-width: 44px;
    min-height: 44px;
  }

  .expand-btn {
    padding: 10px;
    min-width: 44px;
    min-height: 44px;
  }

  /* Task list: ensure text doesn't get cut */
  .task-description {
    font-size: 14px;
    line-height: 1.5;
  }

  /* Expanded panel: use more vertical space on mobile */
  .progress-bar-expanded {
    max-height: 80vh;
    border-radius: 12px 12px 0 0;
  }

  .task-list {
    max-height: 55vh;
  }

  /* Collapsed text: slightly larger for readability */
  .collapsed-task-text {
    font-size: 13px;
  }

  /* Timer section: stack on very narrow */
  .timer-section {
    flex-wrap: wrap;
    gap: 8px;
  }
}
```

**Step 3: Run lint to verify**

Run: `cd frontend && bun run lint`
Expected: PASS (CSS-only changes, no lint issues)

**Step 4: Commit**

```bash
git add frontend/src/components/TaskProgressBar.vue
git commit -m "fix(ui): mobile-responsive TaskProgressBar — stack expanded header, fix thumbnail overlap"
```

---

### Task 2: LiveMiniPreview — Mobile sizing and touch feedback

**Files:**
- Modify: `frontend/src/components/LiveMiniPreview.vue`

**Step 1: Read current size classes**

The component uses a `size` prop with `sm | md | lg` mapping to CSS classes. Read lines 690-710 to find the size class definitions and the viewport transform style computation.

**Step 2: Add mobile-aware sizing**

Add to `<style scoped>` (after the existing size class definitions):

```css
/* ===== MOBILE OVERRIDES ===== */
@media (max-width: 639px) {
  /* On mobile, the lg size in expanded TaskProgressBar needs to fit the narrower screen */
  .live-mini-preview.size-lg {
    max-width: 100%;
    width: 100%;
    aspect-ratio: 16 / 10;
  }

  /* Add touch feedback */
  .live-mini-preview {
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }

  .live-mini-preview:active {
    transform: scale(0.98);
    transition: transform 0.1s ease;
  }

  /* Direct-render panels: bump min font sizes for readability */
  .dc-header-title {
    font-size: 11px;
  }

  .dc-md-text {
    font-size: 11px;
    line-height: 1.4;
  }
}
```

**Step 3: Run lint**

Run: `cd frontend && bun run lint`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/LiveMiniPreview.vue
git commit -m "fix(ui): mobile LiveMiniPreview — full-width lg size, touch feedback"
```

---

### Task 3: ReportModal — Mobile header and layout

**Files:**
- Modify: `frontend/src/components/report/ReportModal.vue`

**Step 1: Make dialog fill mobile screens**

The dialog uses `w-[95vw] max-w-[1180px] h-[90vh] max-h-[900px]` (line 12). On phones, we need full-screen with no gap.

Change the DialogContent `:class` binding (line 7-13) to add mobile-first fullscreen:

In the template, modify the class conditional at line 12 from:
```
: 'w-[95vw] max-w-[1180px] h-[90vh] max-h-[900px]'
```
to:
```
: 'w-[95vw] max-w-[1180px] h-[90vh] max-h-[900px] max-sm:w-screen max-sm:max-w-none max-sm:h-[100dvh] max-sm:max-h-none max-sm:rounded-none'
```

**Step 2: Condense header actions on mobile**

The header has 7 buttons (edit, share, download, more, fullscreen, close). On mobile, hide fullscreen (already full), keep close and overflow the rest.

Add to `<style scoped>` after `.action-btn-active:hover` (around line 834):

```css
/* ===== MOBILE HEADER ===== */
@media (max-width: 639px) {
  .modal-header {
    padding: 10px 12px;
    gap: 8px;
  }

  .header-icon {
    width: 32px;
    height: 32px;
    border-radius: 6px;
  }

  .header-icon .w-5 {
    width: 16px;
    height: 16px;
  }

  .header-title {
    font-size: 13px;
    max-width: 160px;
  }

  .header-meta {
    font-size: 11px;
  }

  .header-left {
    gap: 8px;
  }

  /* Touch-friendly action buttons */
  .action-btn {
    width: 40px;
    height: 40px;
    min-width: 40px;
  }

  /* Document content: reduce side padding */
  .document-content {
    padding: 20px 16px 32px;
  }

  .doc-title {
    font-size: 22px;
  }

  /* Hide TOC on mobile — it overlaps content */
  .toc-container {
    display: none;
  }

  /* Suggestion bar: stack vertically */
  .suggestion-bar {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
    padding: 12px;
  }
}
```

**Step 3: Run lint**

Run: `cd frontend && bun run lint`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/report/ReportModal.vue
git commit -m "fix(ui): mobile ReportModal — fullscreen on phone, condensed header, hidden TOC"
```

---

### Task 4: ToolPanelContent — Mobile frame header and controls

**Files:**
- Modify: `frontend/src/components/ToolPanelContent.vue`

**Step 1: Find the scoped styles section**

Search for `<style scoped>` in the file. The frame header is `.panel-frame-header`, the control buttons are `.panel-control-btn`. Read those styles.

**Step 2: Add mobile overrides**

Add at the end of `<style scoped>`:

```css
/* ===== MOBILE OVERRIDES ===== */
@media (max-width: 639px) {
  .panel-frame-header {
    padding: 10px 12px;
  }

  /* Larger touch targets for close/takeover buttons */
  .panel-control-btn {
    min-width: 44px;
    min-height: 44px;
    padding: 10px;
  }

  /* Activity line: allow wrapping */
  .panel-activity-line {
    flex-wrap: wrap;
  }

  /* Content header: reduce padding */
  .panel-content-header {
    padding: 6px 10px;
  }

  /* View mode tabs: smaller on mobile */
  .panel-content-header .text-xs {
    font-size: 11px;
    padding: 4px 6px;
  }
}
```

**Step 3: Run lint**

Run: `cd frontend && bun run lint`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/ToolPanelContent.vue
git commit -m "fix(ui): mobile ToolPanelContent — larger touch targets, wrapped activity line"
```

---

### Task 5: ToolPanel — Mobile overlay improvements

**Files:**
- Modify: `frontend/src/components/ToolPanel.vue`

**Step 1: Add safe-area padding for mobile**

The panel goes full-screen on mobile (`width: 100%` at line 84). But it uses `sm:ml-3 sm:py-3 sm:mr-4` only for desktop. Mobile needs safe area insets and a visible close affordance.

In the template, line 6, change:
```
'h-full w-full top-0 ltr:right-0 rtl:left-0 z-50 fixed sm:sticky sm:top-0 sm:right-0 sm:h-[100vh] sm:ml-3 sm:py-3 sm:mr-4': isShow,
```
to:
```
'h-full w-full top-0 ltr:right-0 rtl:left-0 z-50 fixed sm:sticky sm:top-0 sm:right-0 sm:h-[100vh] sm:ml-3 sm:py-3 sm:mr-4 max-sm:pb-[env(safe-area-inset-bottom)]': isShow,
```

**Step 2: Run lint + type-check**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/ToolPanel.vue
git commit -m "fix(ui): mobile ToolPanel — safe-area-inset padding for notched phones"
```

---

### Task 6: ChatPage — Mobile header and chat input refinements

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`

**Step 1: Read the chat input section**

Search for the message input area (textarea or input component) — likely near the bottom of the template. Identify its CSS class and any padding.

**Step 2: Add mobile refinements to existing responsive patterns**

The ChatPage already has `sm:` classes (line 21-29). Add targeted fixes for very small screens.

Find the `<style scoped>` section and add:

```css
/* ===== MOBILE REFINEMENTS ===== */
@media (max-width: 479px) {
  /* Header: tighter spacing on very small phones */
  .chat-header {
    padding-inline-start: 6px;
    padding-inline-end: 6px;
    gap: 4px;
  }

  /* Chat view toggle: compact on small phones */
  .chat-view-toggle-btn {
    padding-inline: 6px;
    font-size: 12px;
  }
}

@media (max-width: 639px) {
  /* Research badge: hide on phone (already hidden on md: but catch sm-md gap) */
  .chat-header .hidden.md\\:inline-flex {
    display: none;
  }
}
```

**Step 3: Run lint + type-check**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "fix(ui): mobile ChatPage — tighter header spacing for small phones"
```

---

### Task 7: Run full test suite and verify

**Step 1: Run frontend lint + type-check**

Run: `cd frontend && bun run lint && bun run type-check`
Expected: PASS (all changes are CSS-only or class attribute changes)

**Step 2: Run frontend tests**

Run: `cd frontend && bun run test:run`
Expected: 853+ passed. Same 7 pre-existing failures in UnifiedStreamingView.spec.ts (unrelated).

**Step 3: Visual spot-check note**

Since this is a headless server, visual verification requires either:
- Chrome DevTools MCP screenshot of `localhost:5174` at 375px viewport width
- Or manual check on a phone browser

---

### Task 8: Final commit and push

**Step 1: Verify all changes**

Run: `git diff --stat` to confirm only the expected 6 files are modified.

**Step 2: Push to remote**

```bash
git push origin tuf-15
```
