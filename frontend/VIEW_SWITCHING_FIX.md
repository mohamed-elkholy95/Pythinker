# View Switching Fix: LiveViewer Enhancement

## Problem Statement

When an agent session completes, the main LiveViewer was stuck showing the browser (Google) even when the last tool used was terminal. The mini preview correctly showed the terminal, but the main viewer didn't update.

**User Report:**
> "when agent finished last screen is not showing on live view instead it show google browser last thing was terminal but show browser"
> "although mini live view show properly last thing terminal"

## Root Cause

The `LiveViewer.vue` component was a thin wrapper that **only rendered SandboxViewer** (CDP screencast/browser view). It had no awareness of different view types (terminal, editor, search, etc.).

Meanwhile, `LiveMiniPreview.vue` correctly used `useContentConfig` composable to determine the view type and rendered the appropriate component based on the last tool used.

## Solution Architecture

### 1. Enhanced LiveViewer Component

**File:** `frontend/src/components/LiveViewer.vue`

**Changes:**
- Added `toolContent` prop to receive current tool information
- Integrated `useContentConfig` composable to determine `currentViewType`
- Conditional rendering based on view type:
  - `terminal` → `TerminalContentView`
  - `editor` → `EditorContentView`
  - `search` → `SearchContentView`
  - `live_preview` / `chart` / default → `SandboxViewer` (browser)
- Added content props: `terminalContent`, `editorContent`, `editorFilePath`, `searchResults`, `searchQuery`
- Intelligent fallback logic: shows browser for active tools without content yet

**Key Logic:**
```vue
// Use content config to determine view type
const { currentViewType } = useContentConfig(toRef(() => props.toolContent))

// Determine when to show browser view
const shouldShowBrowser = computed(() => {
  // Show browser for live_preview type or when no specific view type
  if (!currentViewType.value || currentViewType.value === 'live_preview') {
    return props.enabled && props.sessionId
  }

  // For terminal/editor without content yet but active, fall back to browser
  if (currentViewType.value === 'terminal' && !props.terminalContent && props.isActive) {
    return props.enabled && props.sessionId
  }

  return false
})
```

### 2. Updated Parent Components

**File:** `frontend/src/components/ToolPanelContent.vue`

**Changes:**
- Updated both LiveViewer instances to pass:
  - `:tool-content="toolContent"` - Current tool for view type detection
  - `:is-active="isActiveOperation"` - Active state
  - `:terminal-content="terminalContent"` - Terminal output
  - `:editor-content="editorContent"` - File content
  - `:editor-file-path="resolvedFilePath"` - File path
  - `:search-results="searchResults"` - Search results
  - `:search-query="searchQuery"` - Search query

## Vue Best Practices Applied

### 1. **Single Responsibility**
- LiveViewer now has a clear responsibility: orchestrate view switching based on tool type
- Each content view (Terminal, Editor, Search) handles its specific rendering

### 2. **Explicit Data Flow (Props Down, Events Up)**
- Tool content flows down via props
- Events (`connected`, `disconnected`, `error`) flow up to parent
- No direct state mutation between components

### 3. **Composable Reuse**
- Both `LiveViewer` and `LiveMiniPreview` now use the same `useContentConfig` composable
- Ensures consistent view type detection logic

### 4. **Computed Properties for Derived State**
- `shouldShowBrowser` derives when to show browser based on multiple conditions
- `currentViewType` comes from composable, ensuring single source of truth

### 5. **Reactive Dependencies**
- Uses `toRef(() => props.toolContent)` to maintain reactivity
- Automatically updates when tool content changes

## Design Consistency

### Unified View Switching UX

Both mini preview and main viewer now:
1. Use the same `useContentConfig` logic
2. Show the same view type for the same tool
3. Update simultaneously when agent switches tools
4. Display the final state correctly when agent completes

### Visual Coherence

- Terminal view: Same xterm.js rendering in both viewers
- Editor view: Same Monaco-like editor in both viewers
- Search view: Same search results layout in both viewers
- Browser view: CDP screencast for real-time visibility

## Testing Checklist

- [ ] Agent runs terminal command → both viewers show terminal
- [ ] Agent runs file operation → both viewers show editor
- [ ] Agent performs search → both viewers show search results
- [ ] Agent uses browser → both viewers show CDP screencast
- [ ] Agent finishes with terminal → main viewer shows terminal (not browser)
- [ ] Agent switches tools → both viewers update immediately
- [ ] Chart generation → main viewer shows browser with canvas content

## Future Enhancements

1. **Smooth Transitions**: Add fade/slide transitions when switching view types
2. **View Type Persistence**: Remember user's last view mode per tool type
3. **Content Caching**: Cache terminal/editor content to prevent flicker on rapid switches
4. **Custom View Types**: Support plugin-contributed view types via registry pattern

## Files Modified

1. `frontend/src/components/LiveViewer.vue` - Enhanced with view type awareness
2. `frontend/src/components/ToolPanelContent.vue` - Updated prop passing (2 locations)

## Dependencies

**Existing Composables:**
- `useContentConfig` - View type detection logic
- Already used by `LiveMiniPreview`, now also used by `LiveViewer`

**Existing Components:**
- `TerminalContentView` - Terminal output rendering
- `EditorContentView` - File editor rendering
- `SearchContentView` - Search results rendering
- `SandboxViewer` - Browser/CDP screencast rendering
- `InactiveState` - Fallback empty state

No new dependencies added. This is a pure refactoring that reuses existing architecture.

---

**Implementation Date:** 2026-02-16
**Vue Version:** 3.x with Composition API
**Pattern:** Single File Components (SFC) with `<script setup>`
