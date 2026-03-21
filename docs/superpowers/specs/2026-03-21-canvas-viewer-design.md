# Canvas Viewer — Design Specification

**Date:** 2026-03-21
**Goal:** Replace the side tool panel with a full-screen canvas viewer modal for charts, images, and visual content. Matches Manus AI's canvas editor UX.

---

## Overview

When the agent produces a chart (Plotly PNG/HTML) or image artifact, instead of showing it cramped in the right-side ToolPanel split, open a full-screen modal overlay with zoom controls, download, and a bottom toolbar.

---

## Layout

### Top Bar (fixed, 48px height)

```
[⚙] [— 72% +]                                    [↗ fullscreen] | [× close]
```

- **Left:** Settings gear (dropdown: download PNG, open interactive, copy to clipboard) + zoom pill (minus button, percentage text, plus button)
- **Right:** Fullscreen toggle + close button, separated by a `|` divider
- Background: transparent, buttons use `var(--fill-tsp-white-main)` with border

### Image Action Bar (floating, centered above image)

```
[HD Upscale] [⊞ Remove bg] [✏ Edit text] [⬇ download] [··· more]
```

- Floating pill centered horizontally above the image
- Background: white with shadow and border-radius (12px)
- Actions:
  - **Upscale** (HD icon): Future — AI upscale
  - **Remove bg**: Future — background removal
  - **Edit text**: Future — OCR text editing
  - **Download** (⬇ icon): Download PNG immediately
  - **More** (··· icon): Additional options dropdown
- Separator line between Edit text and download icon
- Light/dark theme aware

### Image Info Bar (between action bar and image)

```
kmeans_clusters.png                                    800 × 600
```

- Left: filename in muted text
- Right: dimensions in muted text
- Full width of the image card

### Center Area (flex-1, scrollable)

- Background: `var(--background-gray-light)` (light) / `#1a1a1a` (dark)
- Image/chart rendered on a white card with subtle shadow, centered
- Card has slight border-radius (8px) and drop shadow
- Image scales to fit viewport with padding (auto-fit on open)
- Scroll wheel zooms, drag to pan (when hand tool active)

### Selection Handles

- When image is selected (default on open): blue border (2px) with 4 corner circles (8px diameter, blue fill, white border)
- Corner handles at: top-left, top-right, bottom-left, bottom-right
- Visual only for V1 (no resize functionality yet — future feature)
- Deselects when clicking outside the image

### Bottom Toolbar (fixed, centered, 48px)

```
                    [↗ ∨] [🖼] [≡ ∨]
```

- Floating centered pill with rounded corners (24px radius)
- Background: `var(--background-menu-white)` with shadow
- Three tool groups:
  - **Select tool** (arrow icon + dropdown chevron): Select mode (V shortcut)
  - **Image tool** (image icon): Download / copy image
  - **Notes tool** (text icon + dropdown chevron): Future — add annotations
- Dark mode: darker background, lighter icons

---

## Component Architecture

### New Components

1. **`CanvasViewerModal.vue`** — The full-screen modal overlay
   - Props: `visible: boolean`, `imageUrl: string`, `title: string`, `dimensions: { width: number, height: number }`, `interactive: boolean`, `htmlUrl?: string`
   - Emits: `close`, `download`
   - Manages: zoom state, pan state, active tool, keyboard shortcuts

2. **`CanvasViewerToolbar.vue`** — Bottom floating toolbar
   - Props: `activeTool: 'select' | 'hand'`
   - Emits: `tool-change`, `download`, `annotate`

3. **`CanvasZoomControls.vue`** — Top-left zoom pill
   - Props: `zoom: number` (0-1 scale, displayed as percentage)
   - Emits: `zoom-in`, `zoom-out`, `zoom-reset`

### Modified Components

4. **`ChartToolViewEnhanced.vue`** — Add "expand to canvas" button; clicking chart image opens the modal
5. **`ToolPanelContent.vue`** — When content type is chart/image AND user clicks expand, emit event to open canvas viewer
6. **`ChatPage.vue`** — Mount `CanvasViewerModal` at page level, wire open/close

---

## Interaction Flow

1. Agent generates chart → appears in ToolPanel as today (small preview)
2. User clicks the chart image or an "Open in Canvas" button
3. `CanvasViewerModal` opens as a full-screen overlay (z-index above everything)
4. Image auto-fits to viewport with padding
5. User can zoom (scroll wheel / +/- buttons), pan (hand tool / drag)
6. User can download (gear menu or image tool button)
7. User presses Escape or clicks X → modal closes, returns to chat

---

## Zoom Behavior

- Default: auto-fit (image fills viewport with 48px padding on all sides)
- Scroll wheel: zoom in/out by 10% increments
- +/- buttons: zoom by 10% increments
- Percentage display: shows current zoom (e.g., "72%")
- Min zoom: 10%, Max zoom: 500%
- Double-click: toggle between fit-to-view and 100%

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Escape` | Close modal |
| `V` | Select tool |
| `H` | Hand/pan tool |
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| `0` | Fit to view |
| `Ctrl+S` / `Cmd+S` | Download |

---

## Styling

- Uses existing CSS variables for theme consistency
- Light mode: `#f5f5f5` canvas background, white image card
- Dark mode: `#1a1a1a` canvas background, `#2a2a2a` image card
- Toolbar: glass-morphism effect (backdrop-blur, semi-transparent bg)
- Transitions: 200ms ease for open/close, 100ms for zoom
- No scrollbars on the canvas area (pan-based navigation)

---

## Files to Create

| File | Purpose |
|------|---------|
| `frontend/src/components/canvas/CanvasViewerModal.vue` | Main modal overlay (orchestrator) |
| `frontend/src/components/canvas/CanvasZoomControls.vue` | Top-left zoom pill (-, %, +) |
| `frontend/src/components/canvas/CanvasBottomToolbar.vue` | Bottom floating toolbar (select, image, notes) |
| `frontend/src/components/canvas/CanvasImageActionBar.vue` | Floating action bar above image (upscale, remove bg, edit text, download, more) |
| `frontend/src/components/canvas/CanvasImageFrame.vue` | Image card with selection handles (blue border + corner circles) and info bar (filename, dimensions) |

## Files to Modify

| File | Change |
|------|--------|
| `frontend/src/pages/ChatPage.vue` | Mount modal, wire open/close events |
| `frontend/src/components/toolViews/ChartToolViewEnhanced.vue` | Add click-to-expand on chart image |
| `frontend/src/components/ToolPanelContent.vue` | Emit expand event for chart/image content |

---

## Success Criteria

- Chart/image opens in full-screen modal matching Manus screenshots
- Zoom controls work (scroll wheel + buttons + keyboard)
- Download works (PNG)
- Escape closes modal
- Works in both light and dark mode
- No regression on existing ToolPanel behavior for non-chart content (terminal, browser, etc.)
