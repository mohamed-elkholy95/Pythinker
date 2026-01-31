# VNC Browser Window Shift Fix

## Problem Description

The browser window was shifting to the right in the VNC display during navigation, browsing, and restart operations. This made the browser content partially off-screen and difficult to view.

## Root Cause Analysis

The issue was caused by how Playwright handles browser pages during restart and reconnection operations:

1. **Multiple Windows Created**: When Playwright calls `context.new_page()`, it creates a NEW browser window in Chrome, not a tab ([Playwright Issue #5034](https://github.com/microsoft/playwright/issues/5034))

2. **Positioning Only Applies to First Window**: Chrome's `--window-position=0,0` flag only positions the FIRST window at startup. Subsequent windows created by Playwright use Chrome's default positioning, which is offset to the right.

3. **Restart Created New Windows**: The `restart()` method was calling `cleanup()` which closed all pages, then `initialize()` which created new pages. Each new page = new window = shifted position.

4. **Openbox Timing Issues**: Although openbox is configured to position Chromium windows at 0,0, there's a race condition where new windows appear before openbox can reposition them.

## The Fix

Made three key changes to `playwright_browser.py`:

### 1. Modified `restart()` Method

**Before:**
- Called `cleanup()` → closed all pages
- Called `initialize()` → created new pages/windows
- Result: New windows shifted in VNC

**After:**
- Only reinitializes connection if health check fails
- Does NOT close existing pages
- Reuses existing browser window
- Avoids creating new windows

### 2. Improved `initialize()` Method

**Before:**
- Only reused blank pages (`about:blank`)
- Created new page if existing page had content
- Each new page = new shifted window

**After:**
- Aggressively reuses ANY existing page
- Prefers the FIRST page (original Chrome window at 0,0)
- Only creates new page as last resort
- Logs warning when creating new pages

### 3. Enhanced `_ensure_page()` Method

**Before:**
- Created new page immediately if current page was closed
- New page = new shifted window

**After:**
- Searches for ANY existing page in context first
- Only creates new page if no pages exist
- Reuses existing pages to avoid window creation

## Why This Works

1. **Prevents New Window Creation**: By reusing existing pages instead of creating new ones, we avoid creating new Chrome windows that would be positioned incorrectly.

2. **Preserves Original Window**: The original Chrome window (created at startup) is positioned correctly at 0,0 by the `--window-position` flag and openbox rules. By reusing this window, the browser stays centered.

3. **Survives Reconnections**: When Playwright disconnects and reconnects to Chrome (which keeps running), it now finds and reuses the existing window instead of creating a new one.

## Testing

To verify the fix:

1. **Start a session** and use browser tools
2. **Trigger navigation** - browser should stay centered
3. **Trigger browser restart** (via error recovery or explicit restart) - browser should stay centered
4. **Check VNC display** - browser content should remain at x=0, y=0

## Technical Details

### Key Code Changes

```python
# In restart(): Don't close pages, just refresh connection
self._connection_healthy = await self._verify_connection_health()
if not self._connection_healthy:
    # Reinitialize without closing pages
    self.page = None  # Clear references but don't close
    self.context = None
    self.browser = None
    await self.initialize()

# In initialize(): Reuse ANY existing page
if len(pages) > 0:
    candidate_page = pages[0]  # Prefer first page (original window)
    if not candidate_page.is_closed():
        self.page = candidate_page  # Reuse!
        logger.info(f"Reusing existing page to avoid creating new window")

# In _ensure_page(): Search for existing pages first
pages = self.context.pages
for page in pages:
    if not page.is_closed():
        self.page = page  # Reuse!
        return
```

### Browser Lifecycle

1. **Chrome starts** (supervisord) → Creates window at 0,0 ✓
2. **Playwright connects** (CDP) → Finds default context
3. **Playwright reuses first page** → Uses original window ✓
4. **Agent navigates/restarts** → Keeps using same window ✓
5. **Window stays at 0,0** → No VNC shift ✓

## Related Issues

- [Playwright #5034](https://github.com/microsoft/playwright/issues/5034) - New browser windows instead of tabs
- [Playwright #3696](https://github.com/microsoft/playwright/issues/3696) - newPage() opens new window in Firefox
- Pythinker commit 8a003df - Added openbox window manager
- Pythinker commit d02ca92 - Removed --start-maximized flag

## Future Improvements

1. **Force Tab Mode**: Investigate if Chrome can be configured to create tabs instead of windows for `new_page()` calls

2. **CDP Window Positioning**: Use CDP commands to explicitly position windows at 0,0 when they must be created:
   ```python
   cdp_session = await context.new_cdp_session(page)
   await cdp_session.send("Browser.setWindowBounds", {
       "windowId": window_id,
       "bounds": {"left": 0, "top": 0, "width": 1280, "height": 1024}
   })
   ```

3. **Window Manager Integration**: Consider using wmctrl or xdotool to programmatically position windows when created

4. **Single Page Architecture**: Enforce a single-page model where all navigation happens on the same page object
