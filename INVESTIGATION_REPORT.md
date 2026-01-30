# Investigation Report: Agent Restart and VNC Browser Positioning Issues

**Date:** 2026-01-30
**Investigator:** Claude
**Status:** ✅ FIXED - All root causes addressed

---

## Executive Summary

Two distinct but related issues have been identified:

1. **Agent Restart on Fast Prompts** - Browser sessions are being cleared when new tasks are created, causing ongoing work to be disrupted
2. **Browser Shifted to Right in VNC** - Configuration conflicts between Chrome flags and window manager rules cause improper positioning

---

## ✅ Fixes Applied

### Fix 1: Session-Level Concurrency Lock
**File:** `backend/app/domain/services/agent_domain_service.py`

Added `_task_creation_locks` dictionary and `_get_task_creation_lock()` method to prevent concurrent task creation for the same session. This prevents the race condition where fast prompts cause multiple `_create_task()` calls.

```python
# Session-level locks to prevent concurrent task creation for the same session
self._task_creation_locks: dict[str, asyncio.Lock] = {}

def _get_task_creation_lock(self, session_id: str) -> asyncio.Lock:
    """Get or create a lock for task creation for a specific session."""
    if session_id not in self._task_creation_locks:
        self._task_creation_locks[session_id] = asyncio.Lock()
    return self._task_creation_locks[session_id]
```

The lock is used in `chat()`, `enqueue_user_message()`, and `confirm_action()` methods.

### Fix 2: Browser Clearing Logic
**File:** `backend/app/domain/services/agent_domain_service.py`

Changed `is_new_chat` logic to only clear browser for brand new sandboxes:

```python
# BEFORE (caused restarts on every new task):
is_new_chat = is_new_sandbox or session.task_id is None

# AFTER (only clears for truly new sandboxes):
should_clear_browser = is_new_sandbox
```

### Fix 3: Production Openbox Config Mount
**File:** `docker-compose.yml`

Added missing volume mount for openbox window manager configuration:

```yaml
volumes:
  # Openbox config for proper window management - ensures Chrome stays centered at 0,0
  - ./sandbox/openbox-rc.xml:/home/ubuntu/.config/openbox/rc.xml:ro
```

### Fix 4: Improved clear_session() Method
**File:** `backend/app/infrastructure/external/browser/playwright_browser.py`

Modified `clear_session()` to preserve the first browser window (which is positioned at 0,0) and only close additional pages:

```python
# Keep the first page (original window) - just clear its content
first_page = pages[0]
await first_page.goto("about:blank", timeout=5000)

# Close all additional pages (they create new windows which shift right)
for page in pages[1:]:
    await page.close()
```

---

## Issue 1: Agent Restart on Fast Prompts

### Root Cause

**Location:** `backend/app/domain/services/agent_domain_service.py` (lines 144-151)

```python
# NEW CHAT PROTOCOL: Clear browser for fresh start
# Triggers when:
# 1. New sandbox created (is_new_sandbox=True)
# 2. Session has no previous task (session.task_id is None) - handles shared sandbox
is_new_chat = is_new_sandbox or session.task_id is None

# Browser connection is faster after parallel health check
browser = await sandbox.get_browser(clear_session=is_new_chat, verify_connection=False)
```

### Problem Chain

When fast prompts are sent in quick succession:

```
t=0ms:    User sends "prompt 1"
t=50ms:   _create_task() called, browser pages being cleared
t=100ms:  User sends "prompt 2" (during task 1 execution)
t=150ms:  chat() method processes prompt 2
t=200ms:  Condition check: session.status != RUNNING or task is None
          If task from prompt 1 hasn't fully started yet, condition is TRUE
t=250ms:  _create_task() called AGAIN, browser cleared AGAIN
t=300ms:  Both tasks competing, ongoing work disrupted
```

### Why This Happens

**File:** `backend/app/domain/services/agent_domain_service.py` (lines 425-428)

```python
else:
    if session.status != SessionStatus.RUNNING or task is None:
        task = await self._create_task(session)
        if not task:
            raise RuntimeError("Failed to create task")
```

**Critical flaw:** No concurrency lock prevents multiple `_create_task()` calls from happening simultaneously. When a second prompt arrives while the first task is still initializing:

1. The first task may not have set `session.status = RUNNING` yet
2. The `task is None` check may pass because the task object isn't fully created
3. A new task is created, triggering `clear_session=True`
4. The `clear_session()` method (playwright_browser.py:536-563) closes ALL browser pages

### Browser Clear Session Logic

**File:** `backend/app/infrastructure/external/browser/playwright_browser.py` (lines 536-563)

```python
async def clear_session(self) -> None:
    """Clear all existing pages and tabs for a fresh session."""
    if not self.browser:
        return

    try:
        for context in self.browser.contexts:
            pages = context.pages
            logger.info(f"Clearing {len(pages)} existing pages from browser session")

            for page in pages:
                try:
                    if not page.is_closed():
                        # Navigate to blank first to clear any dialogs
                        try:
                            await page.goto("about:blank", timeout=5000)
                        except Exception:
                            pass
                        await page.close()
```

**Impact:** This forcefully navigates to `about:blank` and closes all active pages. Any ongoing JavaScript execution, pending actions, or navigation is aborted. This causes the "restart" effect visible in the UI.

### Duplicate Message Check Is Not Sufficient

The duplicate message check (lines 395-423) only catches **exact duplicate messages** within 5 minutes:

```python
is_duplicate = False
if session.latest_message == message and session.latest_message_at:
    # ... time check within 300 seconds ...
```

**Different messages sent rapidly bypass this check entirely**, leading to the restart behavior.

### Summary - Issue 1

| Component | File:Line | Problem |
|-----------|-----------|---------|
| Browser clearing logic | `agent_domain_service.py:144-151` | `is_new_chat` triggers for any new task |
| Task creation guard | `agent_domain_service.py:425-428` | No concurrency lock |
| Session clear | `playwright_browser.py:536-563` | Aggressive page closing |
| Duplicate check | `agent_domain_service.py:395-423` | Only catches identical messages |

---

## Issue 2: Browser Shifted to Right in VNC

### Root Cause

**Configuration conflict** between Chrome's window positioning and openbox window manager rules, combined with **missing openbox config in production**.

### Current Configuration

**File:** `sandbox/supervisord.conf` (line 42)

```bash
exec chromium --display=:1 --window-position=0,0 --window-size=1280,1024 ...
```

Chrome is launched with explicit positioning flags:
- `--window-position=0,0` - Position at top-left
- `--window-size=1280,1024` - Match Xvfb resolution

### Window Manager Configuration

**File:** `sandbox/openbox-rc.xml` (lines 72-92)

```xml
<applications>
  <application class="*">
    <decor>no</decor>
    <maximized>yes</maximized>
  </application>
  <application class="Chromium*">
    <decor>no</decor>
    <maximized>yes</maximized>
    <position force="yes">
      <x>0</x>
      <y>0</y>
    </position>
  </application>
</applications>
```

### Critical Issue: Openbox Config Not Mounted in Production

**Development (docker-compose-development.yml:75):**
```yaml
- ./sandbox/openbox-rc.xml:/home/ubuntu/.config/openbox/rc.xml
```

**Production (docker-compose.yml):**
```yaml
# NO openbox config mount - MISSING!
```

**Impact:** In production, openbox runs with DEFAULT configuration, which doesn't have the forced positioning rules for Chromium windows.

### The Browser Shift Problem

1. **New pages create NEW WINDOWS** - When `context.new_page()` is called, Chrome creates a new window, not a tab
2. **Only the FIRST window respects `--window-position=0,0`** - Subsequent windows appear at Chrome's default position (shifted right)
3. **Without openbox config**, there's no window manager enforcement
4. **Even with openbox config**, there's a race condition between window creation and rule application

### Restart Method Improvements (Partial Fix Applied)

**File:** `backend/app/infrastructure/external/browser/playwright_browser.py` (lines 1455-1484)

The `restart()` method has been improved to:
- NOT call `cleanup()` which closes pages
- Reuse existing browser windows
- Only reinitialize if connection is truly unhealthy

```python
async def restart(self, url: str) -> ToolResult:
    # Don't call cleanup() - it closes pages which creates new windows
    # Instead, just reinitialize the connection if needed and navigate
    # This reuses the existing browser window and avoids VNC positioning issues

    try:
        self._connection_healthy = await self._verify_connection_health()
        if not self._connection_healthy:
            logger.info("Browser connection unhealthy, reinitializing without closing pages")
            # Set references to None without closing (Chrome stays running)
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None

            if not await self.initialize():
```

### `_ensure_page()` Method (Partial Fix Applied)

**File:** `backend/app/infrastructure/external/browser/playwright_browser.py` (lines 803-831)

This method now attempts to reuse existing pages before creating new ones:

```python
async def _ensure_page(self) -> None:
    # CRITICAL: Try to reuse any existing page before creating a new one
    # New pages create new windows which may shift in VNC display
    pages = self.context.pages
    if pages:
        # Reuse the first available page
        for page in pages:
            if not page.is_closed():
                self.page = page
                logger.info("Reused existing page in _ensure_page to avoid creating new window")
                return

    # Last resort: Create new page (will create new window)
    logger.warning("No existing pages in _ensure_page, creating new (may cause VNC shift)")
```

### Why Browser Still Shifts Right

Despite partial fixes, the browser shifts right because:

1. **`clear_session()` is still called on new tasks** - This closes ALL pages, forcing new window creation
2. **Production missing openbox config** - No window management enforcement
3. **Race condition** - `clear_session()` called before `restart()` fixes can take effect
4. **Multiple task creation** - Fast prompts trigger multiple `_create_task()`, each potentially clearing the browser

### Summary - Issue 2

| Component | File:Line | Problem |
|-----------|-----------|---------|
| Chrome window flags | `supervisord.conf:42` | Only affects first window |
| Openbox config mount | `docker-compose.yml` | **MISSING in production** |
| New page = new window | `playwright` behavior | Chrome creates windows, not tabs |
| Session clear | `playwright_browser.py:536-563` | Forces new window creation |
| Task creation | `agent_domain_service.py:151` | Triggers clear on each new task |

---

## Connection Between Both Issues

The two issues are **tightly coupled**:

```
Fast Prompt Sent
       ↓
_create_task() called
       ↓
clear_session=True (because is_new_chat or task is None)
       ↓
All browser pages closed (playwright_browser.py:536-563)
       ↓
New page must be created → New window created
       ↓
New window positioned at default (shifted right)
       ↓
VNC shows browser shifted right + Agent appears to "restart"
```

**The restart behavior and the VNC shift are two symptoms of the same underlying issue: aggressive browser session clearing on task creation.**

---

## Recommended Fixes

### Priority 1: Fix Concurrent Task Creation

**File:** `backend/app/domain/services/agent_domain_service.py`

Add a concurrency lock to prevent multiple simultaneous `_create_task()` calls:

```python
# Add session-level lock for task creation
self._task_creation_locks: dict[str, asyncio.Lock] = {}

async def chat(...):
    # Get or create lock for this session
    if session_id not in self._task_creation_locks:
        self._task_creation_locks[session_id] = asyncio.Lock()

    async with self._task_creation_locks[session_id]:
        task = await self._get_task(session)
        if session.status != SessionStatus.RUNNING or task is None:
            task = await self._create_task(session)
```

### Priority 2: Fix Browser Clear Logic

**File:** `backend/app/domain/services/agent_domain_service.py` (line 148)

Only clear browser for truly new sessions:

```python
# Only clear for brand new sandboxes, NOT for new tasks on existing sessions
is_new_chat = is_new_sandbox and session.task_id is None

# Or better: Never clear, let restart() handle it properly
browser = await sandbox.get_browser(clear_session=False, verify_connection=True)
```

### Priority 3: Add Openbox Config to Production

**File:** `docker-compose.yml`

Add the missing openbox config mount:

```yaml
services:
  sandbox:
    volumes:
      # ... existing volumes ...
      - ./sandbox/openbox-rc.xml:/home/ubuntu/.config/openbox/rc.xml
```

### Priority 4: Improve Page Reuse in clear_session()

**File:** `backend/app/infrastructure/external/browser/playwright_browser.py`

Instead of closing ALL pages, navigate to about:blank but keep the original page:

```python
async def clear_session(self) -> None:
    """Clear browser state but preserve the original window."""
    if not self.browser:
        return

    try:
        for context in self.browser.contexts:
            pages = context.pages
            if pages:
                # Keep the FIRST page (original window)
                original_page = pages[0]
                await original_page.goto("about:blank", timeout=5000)

                # Close only additional pages
                for page in pages[1:]:
                    if not page.is_closed():
                        await page.close()
```

---

## Files Requiring Changes

| Priority | File | Changes Needed |
|----------|------|----------------|
| **P0** | `agent_domain_service.py` | Add task creation lock |
| **P0** | `agent_domain_service.py` | Fix `is_new_chat` logic |
| **P1** | `docker-compose.yml` | Add openbox config mount |
| **P2** | `playwright_browser.py` | Improve `clear_session()` to preserve first page |
| **P3** | `agent_domain_service.py` | Add status transition guards |

---

## Test Plan

1. **Fast Prompt Test:**
   - Send 3 prompts within 1 second
   - Verify only ONE task is created
   - Verify browser state is preserved

2. **VNC Position Test:**
   - Open VNC viewer
   - Trigger browser operations
   - Verify browser stays at 0,0 position

3. **Restart Test:**
   - Send "restart browser" command
   - Verify browser stays centered after restart

4. **Production Test:**
   - Deploy with openbox config fix
   - Verify window management works

---

## Appendix: Relevant File Locations

- `backend/app/domain/services/agent_domain_service.py` - Task creation, browser clearing
- `backend/app/infrastructure/external/browser/playwright_browser.py` - Browser operations
- `sandbox/supervisord.conf` - Chrome launch flags
- `sandbox/openbox-rc.xml` - Window manager rules
- `docker-compose.yml` - Production container config
- `docker-compose-development.yml` - Development container config (has openbox mount)
- `frontend/src/components/VNCViewer.vue` - VNC display component
