# ToolPanel Manus-Parity Standardization Design

**Date:** 2026-03-16
**Status:** Approved
**Goal:** Standardize all ToolPanel views to match Manus "Computer" aesthetic — unified context bar, consistent fonts, colors, and loading states across every view.

---

## Reference

Manus design pattern (from screenshots):
- Dark outer frame (18px radius), content fills edge-to-edge
- Title: "Manus's Computer" + activity line (icon + status + separator + detail)
- URL/context bar: centered, muted, semi-transparent background — serves as the "app context" indicator
- Content: full-bleed, no extra padding between frame and content
- Timeline: dark background matching frame, colored dots, blue fill, "live" green dot

## Current State

Pythinker already matches Manus ~80%. The gaps are:
1. **Two different bar styles** — URL bar (`.url-status-bar`) matches Manus perfectly. Content header (`.panel-content-header`) has white background, 36px height, different styling.
2. **Terminal font families differ** — `TerminalContentView` uses `SF Mono`, `TerminalLiveView` uses `JetBrains Mono`.
3. **Terminal dark theme colors differ** — `TerminalContentView` uses `#1a1a1a`, `TerminalLiveView` uses `#1a1b26` (Tokyo Night).
4. **Loading state gradient** — `LoadingState` uses a gradient background inconsistent with flat content areas.
5. **No context bar for non-browser views** — Terminal, Search, Chart, Deals, Canvas, Generic views show a different-styled header or nothing.

## Changes

### Change 1: Unify Context Bar Styling

Make `.panel-content-header` visually identical to `.url-status-bar`:

**Before:**
- Height: 36px
- Background: `var(--background-white-main)` (white)
- Border-radius: `12px` (inline Tailwind)
- Font: 14px, `var(--text-tertiary)`

**After:**
- Height: 32px
- Background: `color-mix(in srgb, var(--fill-tsp-gray-main) 50%, transparent)`
- Border-radius: `12px 12px 0 0`
- Font: 13px, `var(--text-tertiary)`, centered, ellipsis
- Dark mode: `rgba(255, 255, 255, 0.02)`

Tab controls (editor Code/Preview, chart interactivity) remain right-floated inside the same bar.

### Change 2: Context Text Per View

Update `contentHeaderLabel` computed in `ToolPanelContent.vue`:

| View | Current | New |
|------|---------|-----|
| Browser | URL bar (separate) | URL bar (keep — already correct) |
| Terminal | `"Terminal"` | Working dir from ps1, fallback `"Terminal"` |
| Editor | filename | filename (keep — already good) |
| Report | `"Report"` / `"Writing report..."` | Keep as-is |
| Plan | `"Plan"` / `"Creating plan..."` | Keep as-is |
| Search | (none — falls through to displayName) | `Searching "query"` |
| Chart | (none) | chart title or `"Chart"` |
| Deals | (none) | `Finding deals: "query"` |
| Canvas | (none) | project name or `"Canvas"` |
| Generic | displayName or empty | tool display name |

### Change 3: Standardize Terminal Font Family

Both `TerminalContentView.vue` and `TerminalLiveView.vue` use:
```
'JetBrains Mono', 'Fira Code', 'SF Mono', Menlo, Monaco, 'Cascadia Code', monospace
```

### Change 4: Standardize Terminal Dark Theme

Both components use Tokyo Night palette (`#1a1b26` background, `#c0caf5` foreground).

### Change 5: Loading State Background

`LoadingState.vue` changes from gradient to flat:
```css
/* Before */
background: linear-gradient(to bottom, var(--background-secondary), var(--background-surface));

/* After */
background: var(--background-white-main);
```

### Change 6: Ensure Context Bar Shows for All Views

Current condition (line 94):
```
v-if="(contentConfig || showReportPresentation || showPlanPresentation) && (!embedded || forceViewType) && !showUrlStatusBar"
```

This already works — `contentConfig` is non-null for all tool types that have `TOOL_CONTENT_CONFIG` entries. The condition is correct.

## Files Modified

1. **`ToolPanelContent.vue`** — Context bar CSS unification, `contentHeaderLabel` updates
2. **`ToolPanelContent.vue` CSS** — `.panel-content-header` styling to match `.url-status-bar`
3. **`TerminalContentView.vue`** — Font family + dark theme color
4. **`TerminalLiveView.vue`** — Font family alignment
5. **`LoadingState.vue`** — Background change

## Files NOT Modified

- `EditorContentView.vue` — already edge-to-edge, uses shared components
- `SearchContentView.vue` — already clean
- `ContentContainer.vue` — already good
- `EmptyState.vue` — already good
- `ToolPanel.vue` — already matches Manus
- Timeline components — already close to Manus
- `ShellToolView.vue` — static fallback, rarely visible

## Non-Goals

- No structural component changes (no new components created)
- No changes to the outer frame, header, or timeline
- No changes to view content rendering logic
- No changes to backend
