# Design: Nuclear Chrome → Camoufox Migration

**Date:** 2026-02-13
**Status:** Approved
**Approach:** VNC-Primary, Nuclear CDP Removal

## Overview

Replace Chrome/Chromium with Camoufox (Firefox-based anti-detection browser) in the Docker sandbox. Remove all CDP (Chrome DevTools Protocol) dependencies. Make VNC the sole live view renderer. Use xdotool for window management and psutil for memory monitoring.

## Motivation

- **Lighter browser:** Camoufox ~200MB vs Chrome ~500MB+
- **Better crash prevention:** Firefox engine is more memory-efficient
- **Built-in anti-detection:** Fingerprint spoofing, WebRTC IP spoofing, human-like cursor
- **Simplification:** Remove ~1070 lines of CDP code, eliminate dual-renderer complexity
- **On-demand launch:** Browser starts with session, not always-running

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Live view | VNC-only | Already works as fallback, battle-tested, removes dual-renderer bugs |
| Installation | `pip install camoufox` | Auto-downloads binary, simplest approach, ~200MB |
| Window management | xdotool | Lightweight X11 tool, ~100KB, works with any browser |
| browser-use | Migrate to Playwright Firefox | Supports Firefox natively, cleanest approach |
| Timeline replay | No changes | Uses Playwright `page.screenshot()`, browser-agnostic |

## Architecture

### Before (Chrome + CDP)

```
┌─────────────────────────────────────────────────────────┐
│  Frontend                                                │
│  ┌──────────────────┐  ┌──────────────────────────────┐  │
│  │ SandboxViewer    │  │ VNCViewer (fallback)         │  │
│  │ (CDP Screencast) │  │                              │  │
│  └────────┬─────────┘  └──────────┬───────────────────┘  │
└───────────┼────────────────────────┼─────────────────────┘
            │                        │
            ▼                        ▼
    ┌───────────────┐        ┌───────────────┐
    │ CDP WebSocket │        │ VNC WebSocket │
    │ (screencast)  │        │ (noVNC)       │
    └───────┬───────┘        └───────┬───────┘
            │                        │
            ▼                        ▼
    ┌───────────────────────────────────────┐
    │  Sandbox Container                     │
    │  ┌─────────────┐  ┌────────────────┐  │
    │  │ Chrome      │  │ Xvfb + x11vnc │  │
    │  │ CDP:8222    │  │ VNC:5900      │  │
    │  │ socat:9222  │  │ WS:5901       │  │
    │  └─────────────┘  └────────────────┘  │
    └───────────────────────────────────────┘
```

### After (Camoufox + VNC-only)

```
┌─────────────────────────────────────────────────────────┐
│  Frontend                                                │
│  ┌──────────────────────────────────────────────────────┐│
│  │ LiveViewer → VNCViewer (sole renderer)               ││
│  └──────────────────────┬───────────────────────────────┘│
└─────────────────────────┼────────────────────────────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │ VNC WebSocket │
                  │ (noVNC)       │
                  └───────┬───────┘
                          │
                          ▼
    ┌───────────────────────────────────────┐
    │  Sandbox Container                     │
    │  ┌──────────────┐ ┌────────────────┐  │
    │  │ Camoufox     │ │ Xvfb + x11vnc │  │
    │  │ (on-demand)  │ │ VNC:5900      │  │
    │  │ via Playwright│ │ WS:5901       │  │
    │  └──────────────┘ └────────────────┘  │
    │  ┌──────────────┐                     │
    │  │ xdotool      │                     │
    │  │ (window mgmt)│                     │
    │  └──────────────┘                     │
    └───────────────────────────────────────┘
```

## Layer-by-Layer Changes

### Layer 1: Sandbox (Dockerfile + supervisord)

**Dockerfile:**
- Remove: Chrome for Testing download (~500MB)
- Remove: Playwright Chromium install
- Add: `pip install camoufox` (auto-downloads ~200MB Firefox binary)
- Add: `apt-get install xdotool`
- Keep: Xvfb, openbox, x11vnc, websockify, Python runtime

**supervisord.conf:**
- Remove: `[program:chrome]` (50+ Chrome launch flags)
- Remove: `[program:socat]` (CDP port forwarding 9222→8222)
- Keep: xvfb, openbox, xrandr_setup, x11vnc, websockify, sandbox API

**Camoufox launch model:**
- Chrome was always-running via supervisord
- Camoufox launches on-demand when session starts via Playwright
- Uses existing Xvfb display `:1`
- No idle memory consumption

```python
from camoufox.async_api import AsyncCamoufox

async with AsyncCamoufox(
    headless=False,
    humanize=True,
    os="linux",
    config={"navigator.hardwareConcurrency": 4},
) as browser:
    page = await browser.new_page()
```

**Ports removed:** 8222 (CDP internal), 9222 (CDP external)
**Ports kept:** 5900 (VNC), 5901 (websockify), 8080 (sandbox API), 8082 (framework API)

### Layer 2: Backend

**playwright_browser.py:**
- Remove: All 8 `new_cdp_session()` call sites
- Remove: `_get_memory_pressure()` using CDP `Performance.getMetrics`
- Add: `psutil`-based process memory monitoring
- Remove: `_force_window_position()` using CDP `Browser.setWindowBounds`
- Add: xdotool-based window positioning via `asyncio.create_subprocess_exec`
- Remove: `Page.bringToFront` CDP fallbacks
- Add: `xdotool windowactivate` for window activation
- Remove: Chrome user agent rotation pool (Camoufox handles natively)
- Remove: Viewport/timezone rotation pools (Camoufox handles natively)

**Window positioning (xdotool):**
```python
async def _force_window_position(self, x=0, y=0, width=1280, height=1024):
    proc = await asyncio.create_subprocess_exec(
        "xdotool", "search", "--class", "camoufox",
        stdout=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    for wid in stdout.decode().strip().split('\n'):
        if wid:
            await asyncio.create_subprocess_exec(
                "xdotool", "windowmove", wid, str(x), str(y))
            await asyncio.create_subprocess_exec(
                "xdotool", "windowsize", wid, str(width), str(height))
```

**Memory monitoring (psutil):**
```python
import psutil

def _get_memory_pressure(self):
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        if 'firefox' in proc.info['name'].lower():
            rss_mb = proc.info['memory_info'].rss / (1024 * 1024)
            if rss_mb > 1500: return 'critical'
            if rss_mb > 1000: return 'high'
            if rss_mb > 500: return 'medium'
            return 'low'
```

**connection_pool.py:**
- Remove: CDP URL-based pooling
- Replace: Camoufox browser instance pooling
- Health: Playwright connection ping instead of `/json/version`

**browseruse_browser.py:**
- Remove: `BrowserSession(cdp_url=...)` → Playwright Firefox connection
- Remove: Raw WebSocket CDP window positioning → xdotool
- Update: Viewport config for Firefox

**sandbox_manager.py:**
- Remove: CDP health check (`/json/version` on port 9222)
- Replace: Sandbox API health endpoint or Playwright connection check

**playwright_tool.py:**
- Remove: 13 Chrome stealth args (Camoufox handles anti-detection natively)
- Keep: Playwright screenshot/navigation API (unchanged for Firefox)

**session_routes.py:**
- Remove: Screencast WebSocket proxy endpoint
- Remove: Screencast signed-url generation
- Keep: VNC WebSocket proxy, VNC signed-url, input WebSocket proxy

### Layer 3: Frontend

**LiveViewer.vue:**
- Remove: Dual-renderer logic (CDP vs VNC selection)
- Remove: `VITE_LIVE_RENDERER` env var handling
- Remove: CDP blocking TTL and fallback cascade
- Simplify: Direct VNC connection only
- Keep: Reconnection logic, reconnectAttempt indicators

**SandboxViewer.vue:**
- Delete entirely (CDP screencast canvas viewer)

**VNCViewer.vue:**
- No changes (already fully functional)

**Remove CDP artifacts:**
- Signed-url for `target=screencast`
- Screencast quality/fps props
- `streamingPresentation.ts` CDP constants
- CDP-related API response types

**Unchanged:**
- Mini VNC preview (already works via VNC)
- Post-session timeline replay (`useScreenshotReplay`, `page.screenshot()`)
- noVNC library integration
- Input forwarding

### Layer 4: Docker Compose (3 files)

**Remove from sandbox services:**
- `CHROME_ARGS` environment variable
- `BROWSER_PATH` environment variable
- CDP port references

**Add:**
- `DISPLAY=:1` (ensure Camoufox uses Xvfb)

**Adjust:**
- `shm_size: '2g'` → `'1g'` (Firefox uses less shared memory)
- Memory limit: `2G` → `1.5G` (lighter browser)

**Keep:**
- `init: true`, tmpfs mounts, VNC ports, sandbox API port, resource limits

### Sandbox API

**Remove:**
- `cdp_screencast.py` service (~250 lines)
- Screencast API routes (`/screencast/stream`, `/screencast/frame`)

**Update:**
- Health check: Remove CDP port check
- Keep: Input forwarding, health endpoint

## Migration Summary

| Component | Action | Lines Removed | Lines Added |
|-----------|--------|:---:|:---:|
| Dockerfile | Replace Chrome with camoufox + xdotool | ~60 | ~15 |
| supervisord.conf | Remove chrome + socat programs | ~35 | 0 |
| cdp_screencast.py | Delete entirely | ~250 | 0 |
| screencast API routes | Delete | ~80 | 0 |
| playwright_browser.py | Remove CDP, add xdotool/psutil | ~200 | ~80 |
| browseruse_browser.py | Remove CDP, use Playwright Firefox | ~50 | ~30 |
| connection_pool.py | Remove CDP URL pooling | ~30 | ~15 |
| sandbox_manager.py | Remove CDP health check | ~20 | ~10 |
| playwright_tool.py | Remove Chrome stealth args | ~30 | ~5 |
| session_routes.py | Remove screencast proxy | ~80 | 0 |
| LiveViewer.vue | Remove dual-renderer, VNC-only | ~100 | ~20 |
| SandboxViewer.vue | Delete entirely | ~300 | 0 |
| docker-compose files (3) | Remove Chrome env vars | ~15 | ~5 |
| **TOTAL** | | **~1250** | **~180** |

**Net result: ~1070 lines removed.**

## What Stays Unchanged

- VNCViewer.vue (already works)
- Screenshot replay (`useScreenshotReplay`, browser-agnostic)
- Timeline scrubbing UI
- Mini VNC preview
- Input forwarding (mouse/keyboard via sandbox API)
- noVNC library integration
- Session lifecycle (start/stop/resume)
- MongoDB event storage
- Redis task management

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| VNC latency (50-200ms vs CDP 10-50ms) | Acceptable for dev stage; optimize x11vnc settings if needed |
| Camoufox pip package stability | Pin version, test in CI |
| xdotool window detection | Use `--class` or `--pid` for reliable targeting |
| browser-use Firefox compat | Test core flows; Playwright Firefox is well-supported |
| Camoufox binary size on ARM64 | Verify arm64 binary availability in pip package |

## Testing Strategy

1. Sandbox builds and starts cleanly
2. Camoufox launches via Playwright in Xvfb
3. VNC shows browser content correctly
4. xdotool positions windows at (0,0)
5. Page navigation works (goto, click, type)
6. Screenshots captured correctly (timeline replay)
7. Mini VNC preview works
8. Input forwarding works (interactive takeover)
9. Browser-use integration works with Firefox
10. Memory monitoring reports correct values
11. Container resource usage is lower than Chrome
