# Sandbox & Playwright Professional Design Enhancement Report

**Date**: 2026-02-12  
**Scope**: Sandbox Docker image, Playwright tooling, browser design, professional enhancements  
**Context7 Validation**: Playwright Python `/microsoft/playwright-python`, Playwright `/microsoft/playwright`, Docker `/websites/docker`

---

## Executive Summary

This report provides a **professional design enhancement** plan for the Pythinker sandbox and Playwright/browser stack, extending the existing [SANDBOX_DEEP_SCAN_REPORT.md](./SANDBOX_DEEP_SCAN_REPORT.md). It incorporates:

- **Context7 MCP** documentation (Playwright, Docker)
- **Chrome for Testing** version pinning for reproducible builds
- **Professional design** patterns for browser automation

| Category | Enhancement | Priority |
|----------|-------------|----------|
| **Browser Version** | Chrome 128.0.6613.137 (Official Build) via Chrome for Testing | High |
| **Playwright Design** | `channel` / `executablePath` support for custom Chrome | High |
| **Sandbox** | Multi-stage Dockerfile, Chrome for Testing install | Medium |
| **User Agent** | Align UA with pinned Chrome version (128) | Medium |
| **Professional UX** | Viewport, timezone, fingerprint consistency | Medium |

---

## 1. Chrome Version: 128.0.6613.137 (Official Build)

### 1.1 Requirement

Target version: **Chrome 128.0.6613.137 (Official Build) on Ubuntu 22.04 (64-bit)**.

### 1.2 Chrome for Testing Availability

**Verified**: Version `128.0.6613.137` is available in [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/).

| Platform | URL |
|----------|-----|
| linux64 | `https://storage.googleapis.com/chrome-for-testing-public/128.0.6613.137/linux64/chrome-linux64.zip` |
| mac-arm64 | `https://storage.googleapis.com/chrome-for-testing-public/128.0.6613.137/mac-arm64/chrome-mac-arm64.zip` |
| mac-x64 | `https://storage.googleapis.com/chrome-for-testing-public/128.0.6613.137/mac-x64/chrome-mac-x64.zip` |
| win64 | `https://storage.googleapis.com/chrome-for-testing-public/128.0.6613.137/win64/chrome-win64.zip` |

### 1.3 Context7 Playwright Options

From Playwright docs ([params.md](https://github.com/microsoft/playwright/blob/main/docs/src/api/params.md)):

- **`executablePath`**: Path to custom browser executable (use Chrome for Testing binary)
- **`channel`**: Use `"chrome"`, `"chrome-beta"`, `"chrome-dev"`, `"chrome-canary"` for system Chrome

For **version pinning**, use `executablePath` pointing to Chrome for Testing.

### 1.4 Implementation Path

1. **Sandbox Dockerfile**: Optionally install Chrome for Testing 128.0.6613.137 (linux64) instead of PPA Chromium
2. **Supervisord**: Launch Chrome for Testing binary (e.g. `/opt/chrome-for-testing/chrome`) instead of `chromium`
3. **Config**: Add `browser_chrome_executable_path` for overrides
4. **Playwright tool**: Support `executablePath` when launching browsers (for script-based tools)

---

## 2. Current Architecture vs. Target

### 2.1 Current

| Component | Current | Notes |
|-----------|---------|------|
| Sandbox browser | PPA Chromium 144.x | xtradeb/apps, `/usr/bin/chromium` |
| Playwright (sandbox) | `playwright install chromium` | Bundled Chromium in sandbox |
| Backend browser | CDP connect to sandbox Chrome | `PlaywrightBrowser.connect_over_cdp` |
| User agent | Chrome/120.0.0.0 | Stale vs. Chromium 144 |
| Playwright tool | Scripts use `p.chromium.launch()` | Uses Playwright’s Chromium |

### 2.2 Target

| Component | Target | Notes |
|-----------|--------|------|
| Sandbox browser | Chrome for Testing 128.0.6613.137 | linux64, Ubuntu 22.04 |
| Playwright (sandbox) | `executablePath` to Chrome for Testing | Or keep Chromium for script-only tools |
| Backend browser | CDP connect to Chrome 128 | Unchanged, connects to sandbox Chrome |
| User agent | Chrome/128.0.6613.137 | Matches pinned version |
| Playwright tool | `executablePath` when available | Consistent with sandbox Chrome |

---

## 3. Professional Design Enhancements (Context7 Validated)

### 3.1 User Agent Alignment

**Rule**: User agent must match the actual browser version to avoid fingerprint inconsistencies.

```python
# PlaywrightTool.USER_AGENTS / playwright_browser.py USER_AGENT_POOL
# Update Chrome entries to:
"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.6613.137 Safari/537.36"
"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.6613.137 Safari/537.36"
"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.6613.137 Safari/537.36"
```

### 3.2 Viewport Consistency (VNC Display)

Current Xvfb: `1280x1024`. Browser window: `--window-size=1280,1024`.  
Viewports in `VIEWPORT_POOL` / `playwright_browser.VIEWPORT_POOL` must stay ≤ display size to avoid clipping:

```python
# All viewports ≤ 1280×1024
VIEWPORT_POOL = [
    {"width": 1280, "height": 900},   # Primary
    {"width": 1280, "height": 800},
    {"width": 1280, "height": 720},
    {"width": 1024, "height": 768},
    {"width": 1200, "height": 800},
]
```

### 3.3 Playwright Launch Options (Context7)

From Playwright Python docs:

```python
# Custom executable (Chrome for Testing)
browser = await p.chromium.launch(
    executable_path="/opt/chrome-for-testing/chrome",
    headless=True,
    args=["--remote-debugging-port=9222", ...]
)

# Or use channel for system Chrome (when installed)
browser = await p.chromium.launch(channel="chrome", headless=True)
```

### 3.4 Anti-Detection (Stealth)

Existing setup is sound:

- `--disable-blink-features=AutomationControlled`
- `playwright-stealth` for script-based tools
- `navigator.webdriver` override
- User agent rotation (with version alignment)

### 3.5 Chrome Launch Flags (Production)

Recommended flags for headless / VNC in containers:

```
--disable-blink-features=AutomationControlled
--disable-dev-shm-usage
--no-sandbox
--disable-setuid-sandbox
--disable-gpu
--disable-accelerated-2d-canvas
--no-first-run
--remote-debugging-address=0.0.0.0
--remote-debugging-port=8222
```

---

## 4. Implementation Checklist

### 4.1 Sandbox Dockerfile

- [ ] Add Chrome for Testing 128.0.6613.137 install (linux64)
- [ ] Extract to `/opt/chrome-for-testing`
- [ ] Add `CHROME_FOR_TESTING_PATH` env
- [ ] Keep PPA Chromium as fallback or remove if Chrome for Testing is primary

### 4.2 Supervisord

- [ ] Use Chrome for Testing binary: `exec /opt/chrome-for-testing/chrome ...`
- [ ] Ensure `--remote-debugging-port=8222` (socat 9222→8222)

### 4.3 Config

- [ ] Add `browser_chrome_executable_path: str | None = None`
- [ ] Add `browser_chrome_version: str = "128.0.6613.137"` for UA/config docs

### 4.4 User Agent & Playwright Tools

- [ ] Update `USER_AGENT_POOL` / `PlaywrightTool.USER_AGENTS` to Chrome 128
- [ ] Add `executablePath` support in Playwright tool scripts when config is set

### 4.5 PlaywrightBrowser (Backend)

- [ ] Keep `connect_over_cdp` — no change; CDP target is sandbox Chrome
- [ ] Optionally add UA override from config for consistency

---

## 5. Context7 References

| Topic | Library ID | Key Guidance |
|-------|------------|--------------|
| Playwright Python | /microsoft/playwright-python | `launch()`, `executable_path`, async API |
| Playwright | /microsoft/playwright | `channel`, `executablePath`, custom browsers |
| Chrome for Testing | googlechromelabs.github.io/chrome-for-testing | Versioned Chrome builds |
| Docker | /websites/docker | Multi-stage, non-root, security |

---

## 6. Security Notes

- Chrome for Testing binaries are from Google’s official storage
- Run as `ubuntu` (non-root)
- `--no-sandbox` is required in containers; isolation is from Docker
- Restrict or remove `NOPASSWD` sudo for `ubuntu` (see SANDBOX_DEEP_SCAN_REPORT)

---

*Report generated with Context7 MCP validation and Chrome for Testing version check.*
