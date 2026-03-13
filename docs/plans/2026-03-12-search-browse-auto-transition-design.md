# Search → Browse Auto-Transition Design

**Date:** 2026-03-12
**Status:** Approved
**Scope:** Frontend-only, single file change

## Problem

When the agent does research, the search→browse workflow is invisible. The backend's `_browse_top_results()` silently navigates top URLs in the background, but the user never sees it. The panel stays on the search results view until the agent moves to the next tool.

## Design

### Principle

All agent work is visible in the live panel. Search, browse, terminal, file editing, report writing — every phase is shown in real-time. The only gap today is the search→browse handoff.

### User Experience

1. **Search results appear** — panel shows `SearchContentView` with favicons, titles, snippets
2. **5-second timer starts** — when search completes (`ToolEvent status=CALLED`)
3. **Auto-transition to live browser** — `forceBrowserView = true` reveals the persistent CDP screencast (already mounted at z-index -1, already connected, already navigating URLs via `_browse_top_results`)
4. **Activity headline updates** — "Using Search | [query]" → "Using Browser | Browsing [url]"

### Timer Cancellation

The 5-second timer is cancelled if:
- User clicks a search result manually (triggers `handleBrowseUrl`)
- A new tool event arrives (agent moved to terminal, editor, etc.)
- Session ends or component unmounts

### What Already Works (No Changes)

- Terminal commands → `TerminalContentView` live streaming
- File editing → `EditorContentView` streams content
- Report writing → `StreamingReportView` markdown streaming
- Browser navigation → `LiveViewer` CDP screencast
- Tool transitions → `useContentConfig` auto-resets on new tool event
- Background browsing → `_browse_top_results()` navigates top 3 URLs

### What Needs Building

One change in `ToolPanelContent.vue` (~30 lines):
- Watch for search tool completion
- Start 5-second timer
- Set `forceBrowserView = true` after timeout
- Clean up timer on cancel conditions

### Architecture Leverage

- **Persistent browser** already mounted at z-index -1 (instant reveal, no reconnection)
- **`forceBrowserView` ref** already exists for search→browser override
- **`_browse_top_results()`** already runs as fire-and-forget background task
- **Activity headline** already reactive to tool state changes

Zero backend changes. Zero new components. Zero new composables.
