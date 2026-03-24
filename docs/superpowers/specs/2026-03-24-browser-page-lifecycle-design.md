# Browser Page Lifecycle Management

**Date:** 2026-03-24
**Status:** Approved
**Scope:** Sandbox resource optimization — browser renderer process accumulation

## Problem

During active agent sessions, Chromium accumulates renderer processes that are never released:

- **12 renderer processes** consuming **~3 GiB RAM** observed in a single research task
- `navigate_for_display()` reuses the same Playwright page, but Chromium spawns new renderer processes for each cross-origin navigation (DMV sites, study guides, etc.)
- Old renderers linger because Chrome's internal GC is lazy — no signal to release them
- `_browse_top_results()` visits 5 URLs then leaves the last page loaded with all accumulated renderers
- `clear_session()` exists but only runs on session init, not during active browsing
- `--renderer-process-limit=1` limits renderers per BrowsingInstance, not total count
- MongoDB dev container at 28.8% of 512 MiB limit with WiredTiger cache set too high

## Solution

Full page lifecycle overhaul with 6 changes across 6 existing files. No new files.

### 1. Configuration Settings

**File:** `backend/app/core/config_sandbox.py` — `BrowserSettingsMixin`

| Setting | Type | Default | Env Var |
|---------|------|---------|---------|
| `browser_max_pages` | `int` | `3` | `BROWSER_MAX_PAGES` |
| `browser_page_idle_ttl_seconds` | `int` | `120` | `BROWSER_PAGE_IDLE_TTL_SECONDS` |
| `browser_page_idle_check_interval_seconds` | `int` | `30` | `BROWSER_PAGE_IDLE_CHECK_INTERVAL_SECONDS` |
| `browser_preview_cleanup_enabled` | `bool` | `True` | `BROWSER_PREVIEW_CLEANUP_ENABLED` |
| `browser_page_eviction_enabled` | `bool` | `True` | `BROWSER_PAGE_EVICTION_ENABLED` |

**Rationale:**
- `max_pages=3`: 1 active + 2 buffer. Caps memory at ~500-900 MiB instead of unbounded.
- `idle_ttl=120s`: Long enough for user inspection, short enough to reclaim within 2 min.
- `idle_check=30s`: Mirrors sandbox `CHROME_IDLE_CHECK_INTERVAL` pattern.
- All toggleable for safe rollout.

### 2. Prometheus Metrics

**File:** `backend/app/core/prometheus_metrics.py`

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `pythinker_browser_pages_open` | Gauge | — | Current open page count |
| `pythinker_browser_page_evictions_total` | Counter | `reason` | Eviction count by cause |
| `pythinker_browser_preview_cleanups_total` | Counter | — | Post-preview cleanup count |

Helper functions: `record_page_eviction(reason)`, `set_open_page_count(count)`.

### 3. Page Lifecycle Manager (in PlaywrightBrowser)

**File:** `backend/app/infrastructure/external/browser/playwright_browser.py`

**TrackedPage dataclass:**
```python
@dataclass
class TrackedPage:
    page: Page
    created_at: float        # time.monotonic()
    last_active_at: float    # updated on navigate/interact
    origin: str              # last navigated origin (for logging)
```

**New instance variables in `__init__`:**
- `_page_tracker: dict[int, TrackedPage]` — keyed by `id(page)`
- `_page_idle_check_task: asyncio.Task | None`
- Config references from settings

**New methods:**
- `_track_page(page, origin)` — register page in tracker
- `_touch_page(page, origin)` — update last_active_at timestamp
- `_untrack_page(page)` — remove from tracker
- `_evict_excess_pages()` — close oldest non-active pages when count > max
- `_evict_page(tracked, reason)` — navigate to about:blank, close, untrack, record metric
- `_start_page_idle_checker()` — launch background idle-check loop
- `_page_idle_check_loop()` — periodic loop that evicts pages beyond idle TTL

**Integration points (6):**
1. `__init__` — initialize tracker, config, idle-check task ref
2. `_new_page_with_bounds()` — `_track_page()` after creation, `_evict_excess_pages()`
3. `_ensure_page()` — `_touch_page()` on resolved page, start idle checker if not running
4. `navigate_for_display()` — `_touch_page()` after successful navigation
5. `clear_session()` — reset tracker to preserved first page only
6. `cleanup()` — cancel idle-check task, clear tracker

**Eviction strategy:**
1. Never evict `self.page` (active page)
2. Sort remaining by `last_active_at` ascending
3. Close until `len(pages) <= max_pages`
4. Navigate to `about:blank` before close (releases renderer gracefully)

**Idle-check loop:**
- Runs every `browser_page_idle_check_interval_seconds`
- Skips active page
- Removes already-closed pages from tracker
- Evicts pages where `(now - last_active_at) > idle_ttl`

### 4. Post-Preview Renderer Cleanup

**File:** `backend/app/domain/services/tools/search.py` — `_browse_top_results()`

After the URL loop completes (before except blocks), if `browser_preview_cleanup_enabled`:
- Navigate active page to `about:blank` via `navigate_for_display()`
- This signals Chrome to release all cross-origin renderer processes accumulated during preview
- Use `asyncio.wait_for` with 5s timeout
- Non-critical: wrapped in try/except, failure just logs debug

### 5. MongoDB Dev Cache Tuning

**File:** `docker-compose.yml`

Change `--wiredTigerCacheSizeGB` from `0.25` to `0.125`.

Gives WiredTiger 128 MiB for cache, leaving ~384 MiB for connections, cursors, journal buffers in the 512 MiB container.

### 6. Environment Documentation

**File:** `.env.example`

Add commented-out entries for all 5 new settings with defaults and descriptions.

## Architecture Flow

```
Search Tool                     PlaywrightBrowser
-----                           -----------------
_browse_top_results()           __init__()
  |-- navigate_for_display() -> _touch_page()
  |-- navigate_for_display() -> _touch_page()
  |-- ...                       _evict_excess_pages() <-- _ensure_page()
  '-- POST-PREVIEW CLEANUP --> navigate("about:blank")
                                |
                                |-- _page_idle_check_loop() [background]
                                |     '-- _evict_page(reason="idle_ttl")
                                |
                                |-- _evict_excess_pages()
                                |     '-- _evict_page(reason="max_pages")
                                |
                                '-- Prometheus metrics --> Gauge: pages_open
                                                          Counter: evictions_total
```

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Sandbox RAM (research task) | ~3 GiB (12 renderers) | ~500-900 MiB (max 3 pages) |
| Renderer process count | Unbounded (12+ observed) | Capped at max_pages (3) |
| Post-preview memory | Retained until session end | Released within 5s |
| Idle page memory | Never released | Released after 120s |
| MongoDB dev headroom | ~256 MiB free | ~384 MiB free |

## Files Changed

1. `backend/app/core/config_sandbox.py` — 5 new settings in BrowserSettingsMixin
2. `backend/app/core/prometheus_metrics.py` — 3 new metrics + 2 helper functions
3. `backend/app/infrastructure/external/browser/playwright_browser.py` — TrackedPage, lifecycle methods, 6 integration points
4. `backend/app/domain/services/tools/search.py` — post-preview about:blank cleanup
5. `docker-compose.yml` — MongoDB wiredTigerCacheSizeGB 0.25 -> 0.125
6. `.env.example` — document new settings

No new files created.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Evicting a page the user is viewing in live preview | Never evict `self.page`; 120s TTL gives viewing time |
| Race condition between idle checker and foreground navigation | Eviction acquires `_navigation_lock`; uses `page.is_closed()` guard |
| about:blank navigation failing | Non-critical path, wrapped in try/except, logged as debug |
| Feature causing regressions | All toggleable via `browser_page_eviction_enabled` and `browser_preview_cleanup_enabled` |
