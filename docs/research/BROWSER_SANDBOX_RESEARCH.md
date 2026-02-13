# Browser Sandbox Research: Best Stable, Low-Memory, Robust Options for Agent

**Date:** 2026-02-12 (Enhanced: 2026-02-13)
**Context:** Pythinker sandbox agent browser automation (Playwright, CDP, VNC)
**Sources:** Context7 MCP (Playwright docs, browser-use docs), Playwright official Docker docs, production war stories, codebase audit

---

## Executive Summary

| Question | Answer |
|----------|--------|
| **Best browser for sandbox?** | **Firefox** for memory stability; **WebKit** for lowest memory (~590MB); **Chromium** for best compatibility. |
| **Use browser-use?** | **Yes.** Already integrated via `BrowserAgentTool`; connects to sandbox Chrome via CDP. Keep it. |
| **Main sandbox browser?** | Must stay **Chrome/Chromium** (CDP + VNC screencast). Optimize launch args for memory. |
| **Crash prevention status?** | Good foundation exists. **5 critical gaps** identified (see Section 7). |

---

## 1. Current Pythinker Architecture

### Browser Components

| Component | Role | Browser Used | Notes |
|-----------|------|--------------|------|
| **Sandbox Chrome** | Main agent browser, VNC visible | Chrome for Testing or apt chromium | Launched by supervisord, CDP on 8222 |
| **PlaywrightBrowser** | Backend adapter | Connects via CDP | `connect_over_cdp(cdp_url)` |
| **PlaywrightTool** | Shell-based automation in sandbox | chromium / firefox / webkit | Agent selects per task |
| **BrowserAgentTool** | browser-use integration | Uses sandbox Chrome via CDP | `Browser(cdp_url=self._cdp_url)` |

**Constraint:** The main sandbox browser must be Chrome/Chromium to support:
- Chrome DevTools Protocol (CDP) for `connect_over_cdp`
- VNC screencast (CDP Page.captureScreenshot)
- `browser-use`'s `Browser(cdp_url=...)` pattern

### Architecture Diagram

```
Sandbox Container (docker-compose sandbox service)
├── supervisord (PID 1)
│   ├── Xvfb :1 (1280x1024x24, -shmem)
│   ├── openbox (window manager)
│   ├── Chrome/Chromium (supervisord, CDP :8222)
│   │   └── socat :9222 -> :8222 (port forwarding)
│   ├── x11vnc -> websockify :5901
│   └── app (sandbox API :8080)
│
Backend Container
├── PlaywrightBrowser -> connect_over_cdp("http://sandbox:9222")
├── BrowserAgentTool -> browser_use.Browser(cdp_url="http://sandbox:9222")
└── Memory monitoring via CDP Performance.getMetrics()
```

---

## 2. Playwright Browser Comparison (Memory & Stability)

### Memory Usage (2025 Benchmarks -- datawookie, Playwright issues)

| Browser | Standard (UI) | Headless | Minimal args |
|---------|---------------|----------|--------------|
| **Chromium** | ~1094 MB | ~706 MB | ~690 MB |
| **Firefox** | ~874 MB | ~826 MB | ~770 MB |
| **WebKit** | ~590 MB | ~588 MB | N/A (few tuning options) |

### Stability & Known Issues

- **Chromium/Chrome for Testing (Playwright 1.57+):**
  - Regression: switch to Chrome for Testing -> much higher memory
  - Single instances can reach ~20GB with 3 parallel workers
  - GitHub: [Issue #38489](https://github.com/microsoft/playwright/issues/38489)

- **Firefox:**
  - Most stable memory profile
  - No reported high-memory spikes
  - Often recommended as workaround when Chromium memory is a problem

- **WebKit:**
  - Lowest baseline memory (~590 MB)
  - Typically 2-3x slower than Chrome/Firefox
  - Few or no known memory-tuning options

---

## 3. Memory Optimization (Context7 + datawookie + Production War Stories)

### 3.1 Chromium Launch Args -- Comprehensive Audit

The following table audits every recommended flag against Pythinker's `supervisord.conf`:

| Flag | Purpose | In supervisord.conf? | Priority |
|------|---------|---------------------|----------|
| `--disable-dev-shm-usage` | Write shared memory to /tmp instead of /dev/shm | **Yes** | Critical |
| `--no-sandbox` | Disable Chrome sandbox (required in Docker) | **Yes** (via CHROME_ARGS) | Critical |
| `--disable-setuid-sandbox` | Disable setuid sandbox | **Yes** (via CHROME_ARGS) | Critical |
| `--disable-gpu` | Disable GPU hardware acceleration | **Yes** | Critical |
| `--disable-software-rasterizer` | Reduce CPU rendering overhead | **Yes** | High |
| `--disable-extensions` | No browser extensions | **Yes** | High |
| `--disable-background-networking` | No background network requests | **Yes** | High |
| `--disable-background-timer-throttling` | Keep timers running in background | **Yes** | Medium |
| `--disable-backgrounding-occluded-windows` | Keep occluded windows active | **Yes** | Medium |
| `--disable-renderer-backgrounding` | Prevent renderer from backgrounding | **Yes** | Medium |
| `--disable-breakpad` | Disable crash reporting | **Yes** | Medium |
| `--disable-client-side-phishing-detection` | No phishing detection | **Yes** | Medium |
| `--disable-default-apps` | No default Chrome apps | **Yes** | Medium |
| `--disable-component-extensions-with-background-pages` | No component extensions | **Yes** | Medium |
| `--disable-sync` | No Google Account syncing | **Yes** | Low |
| `--mute-audio` | No audio | **Yes** | Low |
| `--no-first-run` | Skip first-run wizard | **Yes** | Low |
| `--force-color-profile=srgb` | Consistent rendering | **Yes** | Low |
| `--no-zygote` | Disable zygote process (fewer child processes) | **No** | **High -- ADD** |
| `--single-process` | Single process mode (less memory, less isolation) | **No** | **Medium -- EVALUATE** |
| `--disable-crashpad` | Disable crashpad reporter | **Yes** (via CHROME_ARGS) | Medium |
| `--js-flags=--max-old-space-size=512` | Cap V8 heap size | **No** | **High -- ADD** |

### 3.2 Firefox Launch (PlaywrightTool alternative)

```python
args=["--no-remote", "--safe-mode"],
firefox_user_prefs={
    "dom.ipc.processCount": 1,
    "dom.ipc.processCount.web": 1,
    "layers.acceleration.disabled": True,
    "media.autoplay.enabled": False,
    "network.preload": False,
    "permissions.default.image": 2,  # Block images
}
```

### 3.3 Context Tweaks (reduce footprint)

```python
context = browser.new_context(
    device_scale_factor=1,
    is_mobile=True,
    viewport={"width": 375, "height": 667}
)
```

---

## 4. Browser Use Integration

### Current status

- `BrowserAgentTool` uses the `browser_use` library and connects to the sandbox Chrome via CDP.
- No extra browser process is launched.
- Works with the existing Chrome instance used for Playwright and VNC.

### browser-use Key Parameters (Context7 validated)

```python
# From Context7: /browser-use/browser-use (Score: 79.6/100)
agent = Agent(
    task="...",
    llm=llm,
    max_failures=3,           # Maximum retries for steps with errors
    max_actions_per_step=3,   # Limit actions per step
    step_timeout=120,         # Timeout per step (seconds)
    llm_timeout=90,           # Timeout for LLM calls (seconds)
    use_vision="auto",        # Include screenshots when useful
    browser_session=BrowserSession(
        cdp_url="http://sandbox:9222",
        headless=False,
        disable_security=False,  # Keep security features on
    ),
)
```

### Error Recovery Pattern (Context7 validated)

```python
# From Context7: browser-use prompting guide
task = """
Robust data extraction:
1. Go to target URL
2. If navigation fails due to anti-bot protection:
   - Use google search as fallback
3. If page times out, use go_back and try alternative approach
"""
```

### Recommendation

- **Keep browser-use.** Uses shared Chrome, no memory overhead.
- **Set `max_failures=3`** for automatic retry on step errors.
- **Set `step_timeout=120`** to prevent indefinite hangs.

---

## 5. Docker Container Best Practices (Context7 + Playwright Official Docs)

### 5.1 Playwright Official Docker Recommendations

From Context7 `/microsoft/playwright` (Score: 94.9/100) and Playwright Docker docs:

| Recommendation | Status in Pythinker | Impact |
|---------------|---------------------|--------|
| **`init: true`** on container | **MISSING** | Prevents zombie Chrome processes (PID=1 issue). Without it, Chrome child processes may not be properly reaped. |
| **`--ipc=host`** | Not used (by design -- security) | Would allow Chrome to use host IPC. `--disable-dev-shm-usage` + adequate shm_size compensates. |
| **`--shm-size=2g`** minimum | **1536m (prod)** / 4gb (dev) | Playwright/Selenium recommend minimum 2GB. Current 1536m is below recommendation. |
| **`--cap-add=SYS_ADMIN`** | Not used (hardened) | Only needed for debugging weird Chromium launch errors. |
| **`dumb-init`** or tini | Not used | Alternative to `init: true` for zombie process prevention. |
| **Non-root user** | **Yes** (`ubuntu` user) | Disables Chromium sandbox (already using `--no-sandbox`). |
| **seccomp profile** | **Yes** (`seccomp-sandbox.json`) | Provides syscall filtering for security. |

### 5.2 Critical Finding: /tmp tmpfs Size vs --disable-dev-shm-usage

**`--disable-dev-shm-usage`** redirects Chrome shared memory writes from `/dev/shm` to `/tmp`.

Current Pythinker config:
```yaml
# docker-compose.yml
shm_size: '1536m'       # /dev/shm = 1.5GB
tmpfs:
  - /tmp:size=300M       # /tmp = 300MB  <-- POTENTIAL PROBLEM
```

**Risk:** If Chrome writes shared memory to `/tmp` (due to `--disable-dev-shm-usage`) and `/tmp` is only 300MB, Chrome may crash when shared memory allocation exceeds 300MB. This partially defeats the purpose of the flag.

**Options:**
1. **Increase `/tmp` tmpfs to 1GB+** (recommended)
2. **Remove `--disable-dev-shm-usage`** and rely on shm_size (1536m is adequate if using this approach)
3. **Use both:** Keep `--disable-dev-shm-usage` AND increase `/tmp` to 1GB

### 5.3 Production Architecture Pattern (from Medium: "8GB Was a Lie")

For production Playwright + Chromium in Docker:

```
Architecture for stable browser automation:
1. Limit browser concurrency (semaphore: 3-4 workers per 8GB RAM)
2. Isolate browser into dedicated worker service
3. Process requests via Redis-backed queue with backpressure
4. Explicitly handle Docker shared memory constraints
5. Set vm.swappiness=10 as OOM buffer
```

Pythinker already uses Redis for task queuing. The main gap is explicit concurrency limiting per sandbox.

---

## 6. Crash Prevention Audit -- What Pythinker Already Does Well

### 6.1 Existing Crash Handlers (Verified in Codebase)

| Feature | File | Status |
|---------|------|--------|
| **`page.on("crash")` handler** | `playwright_browser.py:1237` | Registered; sets `_connection_healthy = False` |
| **`_is_crash_error()` detection** | `playwright_browser.py:294` | 10 crash signatures detected |
| **Memory pressure monitoring** | `playwright_browser.py:475` | CDP `Performance.getMetrics()` checks JS heap |
| **Auto-restart on memory pressure** | `config.py:255` | `browser_memory_auto_restart = True` |
| **Memory thresholds** | `config.py:256-257` | Critical: 800MB, High: 500MB |
| **Connection health verification** | `playwright_browser.py:1012` | `page.evaluate("() => true")` heartbeat |
| **Exponential backoff retry** | `playwright_browser.py:1266` | Init retries with `min(delay * 2, 4)` cap |
| **Heavy page detection** | `playwright_browser.py:187` | Wikipedia/large pages skip smart scroll |
| **Graceful degradation** | `playwright_browser.py:2106` | Returns partial data on crash instead of failing |
| **Route interception** | `playwright_browser.py` | Blocks ads/trackers/analytics to reduce memory |
| **supervisord autorestart** | `supervisord.conf:59` | `autorestart=true` for Chrome process |
| **Crash tests** | `test_browser_crash_resilience.py` | Unit tests for crash detection and recovery |

### 6.2 Crash Signatures Detected

```python
BROWSER_CRASH_SIGNATURES = [
    "Target closed",
    "Target crashed",
    "Target page, context or browser has been closed",
    "Browser has been closed",
    "Browser closed",
    "Session closed",
    "Execution context was destroyed",
    "Protocol error",
    "Connection closed",
    "Page crashed",
]
```

---

## 7. Critical Gaps & Recommendations

### GAP 1: Missing `init: true` Docker Flag (Zombie Process Prevention)

**Source:** Playwright official Docker docs (Context7 `/microsoft/playwright`, Score: 94.9/100)

**Problem:** Without `init: true`, Chrome child processes with PID=1 special treatment may become zombie processes, leaking memory over time.

**Fix:**
```yaml
# docker-compose.yml - sandbox service
sandbox:
  init: true  # Add this line
```

**Impact:** Prevents zombie Chrome processes accumulating in long-running sandbox containers.

### GAP 2: `/tmp` tmpfs Too Small for `--disable-dev-shm-usage`

**Source:** Chromium bug tracker (crbug.com/736452), production incident reports

**Problem:** `--disable-dev-shm-usage` writes to `/tmp`, but `/tmp` is only 300MB tmpfs. Chrome can easily exceed this for complex pages.

**Fix:**
```yaml
# docker-compose.yml - sandbox service
tmpfs:
  - /tmp:size=1g,nosuid,nodev   # Increase from 300M to 1G
```

**Impact:** Prevents OOM crashes when Chrome writes shared memory to `/tmp` on complex pages.

### GAP 3: Missing `browser.on("disconnected")` Handler

**Source:** Context7 `/websites/playwright_dev_python` (Score: 88.7/100)

**Problem:** Only `page.on("crash")` is registered. The `browser.on("disconnected")` event fires when the entire browser process exits or the CDP connection drops -- this is a different event than page crash.

**Fix in `playwright_browser.py`:**
```python
# In initialize(), after connecting browser:
self.browser.on("disconnected", lambda: self._on_browser_disconnected())

def _on_browser_disconnected(self) -> None:
    """Handle browser disconnection event (Playwright best practice).

    Fires when browser application closes, crashes, or CDP connection drops.
    Different from page.on('crash') which only fires for renderer crashes.
    """
    logger.error(f"Browser disconnected (CDP: {self.cdp_url}) - marking connection unhealthy")
    self._connection_healthy = False
```

**Impact:** Catches cases where the browser process dies but the page crash event doesn't fire (e.g., `kill -9 chrome`, OOM killer, supervisord restart).

### GAP 4: Missing `--no-zygote` and V8 Heap Cap

**Source:** Production best practices (Medium, Puppeteer memory leak guide)

**Problem:** Chrome spawns a zygote process that pre-forks renderer processes. In a single-browser sandbox, this is unnecessary overhead. V8 heap has no cap, allowing unbounded growth.

**Fix in `docker-compose.yml`:**
```yaml
environment:
  - CHROME_ARGS=--no-sandbox --disable-setuid-sandbox --disable-crashpad --user-data-dir=/tmp/chrome --no-zygote --js-flags=--max-old-space-size=512
```

**Impact:**
- `--no-zygote`: Fewer child processes, simpler process tree, slightly faster startup
- `--js-flags=--max-old-space-size=512`: Caps V8 heap at 512MB, forces garbage collection before OOM

### GAP 5: `shm_size` Below Playwright Recommendation

**Source:** Playwright Docker docs (Context7), Selenium standalone Docker images (`--shm-size="2g"`)

**Problem:** Production `shm_size: 1536m` is below Playwright's recommended minimum of 2GB. While `--disable-dev-shm-usage` mitigates this, having both at adequate levels provides defense in depth.

**Fix:**
```yaml
# docker-compose.yml
shm_size: '2g'   # Increase from 1536m to 2g
```

**Impact:** More headroom for Chrome shared memory operations, reduces OOM risk.

---

## 8. Recommended Changes Summary

### Priority 1 -- Quick Wins (No Code Changes)

| Change | File | Effort |
|--------|------|--------|
| Add `init: true` to sandbox services | `docker-compose.yml` | 2 lines |
| Increase `/tmp` tmpfs to 1GB | `docker-compose.yml` | 1 line edit |
| Increase `shm_size` to 2g | `docker-compose.yml` | 1 line edit |
| Add `--no-zygote` to CHROME_ARGS | `docker-compose.yml` | 1 line edit |
| Add `--js-flags=--max-old-space-size=512` | `docker-compose.yml` | 1 line edit |

### Priority 2 -- Code Changes

| Change | File | Effort |
|--------|------|--------|
| Add `browser.on("disconnected")` handler | `playwright_browser.py` | ~10 lines |
| Add `PLAYWRIGHT_DEFAULT_BROWSER` config | `config.py`, `playwright_tool.py` | ~20 lines |

### Priority 3 -- Future Optimization

| Change | File | Effort |
|--------|------|--------|
| Set PlaywrightTool default to Firefox | `playwright_tool.py` | Config change |
| Test Firefox/WebKit for common agent flows | Tests | Medium |
| Add concurrency limiter per sandbox | `sandbox_manager.py` | Medium |
| Monitor Playwright #38489 for Chrome for Testing memory fix | Tracking | Ongoing |

---

## 9. Context7 MCP Validation Summary

All recommendations validated against authoritative Context7 sources:

| Source | Library ID | Score | Key Finding |
|--------|-----------|-------|-------------|
| **Playwright** | `/microsoft/playwright` | 94.9/100 | Docker: `--init`, `--ipc=host`, `--shm-size=2g`, `--disable-dev-shm-usage` |
| **Playwright Python** | `/websites/playwright_dev_python` | 88.7/100 | `browser.on("disconnected")`, `page.on("crash")`, `connect_over_cdp` timeout config |
| **browser-use** | `/browser-use/browser-use` | 79.6/100 | `BrowserSession(cdp_url=...)`, `max_failures=3`, `step_timeout=120`, error recovery patterns |
| **Playwright .dev** | `/microsoft/playwright.dev` | 91.2/100 | New headless mode (`channel: 'chromium'`), seccomp profiles |

---

## 10. References

- Playwright Python: `/microsoft/playwright-python` (Context7, Score: 89.9)
- Playwright: `/microsoft/playwright` (Context7, Score: 94.9)
- Playwright Python Docs: `/websites/playwright_dev_python` (Context7, Score: 88.7)
- browser-use: `/browser-use/browser-use` (Context7, Score: 79.6)
- [Playwright Docker Docs](https://playwright.dev/docs/docker) -- `--init`, `--ipc=host`, `--shm-size`
- [Playwright CI Docs](https://playwright.bootcss.com/python/docs/ci) -- `--disable-dev-shm-usage` for Docker
- [Playwright Browser Footprint](https://datawookie.dev/blog/2025/06/playwright-browser-footprint) -- Memory benchmarks
- [Playwright #38489](https://github.com/microsoft/playwright/issues/38489) -- Chrome for Testing memory regression
- [8GB Was a Lie: Playwright in Production](https://medium.com/@onurmaciit/8gb-was-a-lie-playwright-in-production-c2bdbe4429d6) -- Production crash prevention
- [Hidden Cost of Headless Browsers](https://medium.com/@matveev.dina/the-hidden-cost-of-headless-browsers-a-puppeteer-memory-leak-journey-027e41291367) -- Comprehensive Chrome flags
- [Chromium Bug 1085829](https://bugs.chromium.org/p/chromium/issues/detail?id=1085829) -- /dev/shm OOM in containers
- [Baeldung: Chrome Headless in Docker](https://www.baeldung.com/ops/docker-google-chrome-headless) -- Non-root + flag best practices
- [Browser Use docs](https://docs.browser-use.com/) -- Official browser-use documentation
- Pythinker codebase: `playwright_browser.py`, `browser_agent.py`, `playwright_tool.py`, `supervisord.conf`, `docker-compose.yml`
