# Headless Browser Performance & Resource Optimization Research

**Date:** 2026-03-25
**Scope:** Playwright/Chromium headless optimization, Docker containers, CDP screencast, browser pooling, lightweight alternatives
**Sources:** 30+ articles, benchmarks, and technical discussions (2025-2026)

---

## Table of Contents

1. [Playwright/Chromium Headless Optimization Techniques](#1-playwrightchromium-headless-optimization-techniques)
2. [Reducing Chromium Memory Footprint in Docker](#2-reducing-chromium-memory-footprint-in-docker)
3. [Browser Pooling and Reuse Strategies](#3-browser-pooling-and-reuse-strategies)
4. [CDP Screencast Performance Optimization](#4-cdp-screencast-performance-optimization)
5. [X11/Xvfb Optimization for Virtual Displays](#5-x11xvfb-optimization-for-virtual-displays)
6. [Chromium Launch Flags for Minimal Resource Usage](#6-chromium-launch-flags-for-minimal-resource-usage)
7. [Browser Isolation: Contexts vs Containers](#7-browser-isolation-contexts-vs-containers)
8. [Playwright Persistent Contexts for Resource Saving](#8-playwright-persistent-contexts-for-resource-saving)
9. [Page Lifecycle Optimization](#9-page-lifecycle-optimization)
10. [Lightweight Alternatives to Full Browser](#10-lightweight-alternatives-to-full-browser)
11. [Recommendations for Pythinker](#11-recommendations-for-pythinker)

---

## 1. Playwright/Chromium Headless Optimization Techniques

### Headless Mode Evolution (Chrome 132+, January 2025)

Chrome 132 unified the two headless modes. The old headless (separate binary, limited features) is deprecated. `--headless` now launches "new headless" with full Chrome feature parity. Do NOT use `--headless=old` unless there is a specific legacy reason.

### Measured Performance Gains

| Mode | Peak Memory (Chromium) | Notes |
|------|----------------------|-------|
| Standard (headed) | 1,094 MB | Full UI rendering |
| Headless | 706 MB | **35% reduction** |
| Minimal (headless + flags + route blocking) | 690 MB | **37% reduction** |

Source: datawookie.dev Playwright Browser Footprint benchmarks (June 2025), measured with `memory_profiler`.

**Firefox comparison:** Standard 874 MB, headless 826 MB (only 5% savings — Firefox headless is less optimized than Chromium headless).

**WebKit comparison:** Standard 590 MB, headless 588 MB (negligible difference — WebKit is already lean).

### Key Insight

The biggest single win is simply going headless. Beyond that, additional flags and route blocking provide incremental ~2-5% savings each. The compounding effect matters at scale.

### Headless vs Headed Speed

- Headless mode is **10-30% faster** than headed mode due to skipping visual rendering, compositing, and GPU interaction.
- Benchmark: Playwright test execution averaged 1.33s headless vs 1.37s headed (4 seconds faster over large suites).
- At scale (100+ tests), headless saves **8-25 minutes** on authentication alone via persistent state.

---

## 2. Reducing Chromium Memory Footprint in Docker

### The /dev/shm Problem

Docker's default `/dev/shm` is 64 MB. Chrome uses shared memory extensively for IPC between renderer processes. Without `--disable-dev-shm-usage`, Chrome crashes with "session deleted because of page crash" errors.

**Solutions (pick one):**
- Flag: `--disable-dev-shm-usage` (forces Chrome to use `/tmp` instead)
- Docker: `--shm-size=2g` on `docker run`
- Compose: `shm_size: '2gb'` in service definition

### Memory Limits with cgroups

Docker resource constraints map to Linux cgroups:

```yaml
# docker-compose.yml
services:
  sandbox:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
        reservations:
          memory: 512M
```

**Tested production configurations:**
- 500 MB container: Works for single-tab DOM dumping with `--js-flags="--max_old_space_size=500"` to force V8 garbage collection below 500 MB. Ran stable for weeks.
- 2 GB container: Comfortable for multi-tab automation with `--single-process` flag.
- Chrome headless with cgroup memory limit of 1 GB: Typical production choice.

### V8 Heap Limit Flag

```
--js-flags="--max_old_space_size=500"
```

Forces V8's garbage collector to keep the heap below 500 MB. Reported to reduce Chrome memory from 250 MB to stable operation in 500 MB containers. Critical for preventing OOM kills.

### Multi-Stage Docker Builds

Slim production images reduce disk footprint:
- `chromedp/headless-shell:stable` — stripped Chromium binary, ~200 MB image
- Multi-stage builds with `debian:stable-slim` base + only essential libraries (libnss3, libfreetype6-dev, fonts-freefont-ttf, fontconfig, libharfbuzz-dev)

### Single-Process Mode

`--single-process` reduces process count but increases per-process memory. Testing showed mixed results:
- Fewer processes = less IPC overhead
- But single-process mode blows up memory to ~250 MB vs ~46 MB in multi-process for simple pages
- Better suited for containers with strict cgroup limits where process management overhead matters

---

## 3. Browser Pooling and Reuse Strategies

### Resource Pool Architecture

```
Pool Manager
  |-- Browser Pool (max 4 browsers)
  |     |-- Context Pool (max 8 per browser)
  |     |     |-- Page Pool (max 4 per context)
  |     |-- Idle Timeout (30s)
  |     |-- Usage Stats Tracking
```

### Key Patterns

**1. Browser Reuse (biggest win):**
- Launch cost: 2-5 seconds for new browser instance
- Context creation: ~50-100ms within existing browser
- Reusing browser instances **cut automation time by 60%** (community reports)

**2. Context Pooling:**
```python
# ResourcePool config
config = {
    'maxBrowsers': 4,
    'maxContextsPerBrowser': 8,
    'maxPagesPerContext': 4,
    'idleTimeout': 30000,  # 30 seconds
}
```

**3. Connection Pooling for MCP/CDP:**
- Reuse WebSocket connections to browser instances
- Enable connection pooling: dropped form automation from 4+ seconds to sub-second responses
- Key: persistent browser context eliminates startup penalty each time

### Anti-Pattern: Fresh Browser Per Request

The Puppeteer Memory Leak Journey (Medium) documented that creating/destroying browsers per request causes:
- Memory accumulation from incomplete cleanup
- 200 MB leaked per browser lifecycle
- Solution: manage incognito browser contexts within a single browser instance for clean state per request

### Idle Cleanup

```python
async def cleanup_idle_resources(self):
    now = time.time()
    for key, info in list(self.contexts.items()):
        if now - info['lastUsed'] > self.config['idleTimeout']:
            await info['resource'].close()
            self.contexts.pop(key)
```

---

## 4. CDP Screencast Performance Optimization

### How CDP Screencast Works

`Page.startScreencast` captures frames based on **rendering events, not time**. Chrome sends a frame when the UI changes. If nothing changes, no frames are sent. Each frame must be acknowledged (`Page.screencastFrameAck`) before the next is delivered.

### Critical Parameters

| Parameter | Optimized Value | Impact |
|-----------|----------------|--------|
| `format` | `jpeg` | ~5-10x smaller than PNG, faster encode/decode |
| `quality` | 40-60 | Below 40 = noticeable artifacts; above 60 = diminishing returns |
| `maxWidth` | Match viewport | Avoid unnecessary downscaling overhead |
| `maxHeight` | Match viewport | Avoid unnecessary downscaling overhead |
| `everyNthFrame` | 2-3 for monitoring, 1 for capture | Lower = more frames but higher CPU |

### Performance Bottlenecks

1. **ACK latency is the primary bottleneck.** Chrome will NOT send the next frame until the previous is ACKed. The faster you ACK and process, the more frames you receive. A slow consumer (e.g., writing to disk synchronously) gates the entire pipeline.

2. **JPEG vs PNG:** PNG at quality 100 is the worst case for screencast — huge payloads, slow encode. JPEG at quality 50-60 is the sweet spot for monitoring use cases.

3. **Resolution scaling:** A 1920x1080 screencast generates ~150-300 KB per JPEG frame at quality 60. Dropping to 960x540 cuts payload to ~40-80 KB (4x reduction) with acceptable quality for monitoring.

### Optimization Recommendations for Pythinker

```python
# Optimized screencast config
await cdp_session.send('Page.startScreencast', {
    'format': 'jpeg',
    'quality': 50,           # Was likely higher
    'maxWidth': 960,          # Half resolution for monitoring
    'maxHeight': 540,
    'everyNthFrame': 2,       # Skip every other frame
})

# Fast ACK pattern — ACK immediately, process async
async def on_screencast_frame(frame):
    # ACK first to unblock Chrome
    await cdp_session.send('Page.screencastFrameAck', {
        'sessionId': frame['sessionId']
    })
    # Then process frame asynchronously
    asyncio.create_task(process_frame(frame['data']))
```

### Frame Rate Insight (from Chromium team)

> "Currently headless chrome is still trying to render at 60 fps which is rather wasteful. Many pages do need a few frames (maybe 10-20 fps) to render properly (due to requestAnimationFrame and animation triggers) but we expect there are a lot of CPU savings to be had here."

For Pythinker's monitoring use case, 5-10 fps is sufficient. Setting `everyNthFrame: 3-6` can cut CPU by 50-80% for the screencast subsystem.

---

## 5. X11/Xvfb Optimization for Virtual Displays

### When Xvfb is Needed vs Not

**Use native headless (`--headless`) when:**
- Simple automation/scraping
- No dependency on window manager or GLX
- Docker containers without display requirements

**Use Xvfb when:**
- Application requires a window manager or desktop environment (Electron apps)
- GLX or window-manager dependent behaviors
- Testing tools that expect a `DISPLAY` environment variable
- Headful mode needed for anti-bot evasion

### Xvfb Configuration for Docker

```dockerfile
RUN apt-get update -qq && apt-get install -y --no-install-recommends xvfb
```

```bash
# Minimal Xvfb for automation
xvfb-run --auto-servernum -s "-ac -screen 0 1280x1024x24" chromium

# Memory-optimized (lower color depth)
xvfb-run --auto-servernum -s "-ac -screen 0 1280x1024x8" chromium
```

### Color Depth Impact

| Color Depth | Frame Buffer Memory | Use Case |
|-------------|-------------------|----------|
| 24-bit | ~3.75 MB per frame | Full color, visual accuracy |
| 16-bit | ~2.5 MB per frame | Good enough for most automation |
| 8-bit | ~1.25 MB per frame | Minimal, for non-visual tasks |

### Key Recommendation

**For Pythinker's sandbox: Avoid Xvfb entirely.** Chrome's native `--headless` mode eliminates the need for a virtual display server. Xvfb adds:
- Extra memory overhead (~50-100 MB)
- Process management complexity
- Screen buffer allocation
- No benefit when using CDP screencast (which captures from Chrome's internal rendering, not X11)

If headful mode is ever needed (e.g., anti-bot evasion), Xvfb at 1280x1024x16 is the recommended configuration.

---

## 6. Chromium Launch Flags for Minimal Resource Usage

### Tier 1: Essential Docker/Container Flags

```python
ESSENTIAL_FLAGS = [
    '--headless',                    # No GUI rendering
    '--no-sandbox',                  # Required in Docker (no kernel user namespaces)
    '--disable-dev-shm-usage',       # Avoid 64MB /dev/shm crash
    '--disable-gpu',                 # No GPU hardware in containers
]
```

### Tier 2: Resource Reduction Flags

```python
RESOURCE_FLAGS = [
    '--disable-background-networking',      # Stop non-essential network traffic
    '--disable-background-timer-throttling', # Skip JS timer throttling
    '--disable-client-side-phishing-detection',
    '--disable-extensions',                 # No extensions loaded
    '--disable-renderer-backgrounding',     # Don't throttle background renderers
    '--disable-software-rasterizer',        # Skip software rendering fallback
    '--disable-component-update',           # No Chrome component updates
    '--disable-domain-reliability',         # No domain reliability monitoring
    '--disable-infobars',                   # No info bars
    '--mute-audio',                         # No audio processing
    '--no-first-run',                       # Skip initial setup
]
```

### Tier 3: Memory-Specific Flags

```python
MEMORY_FLAGS = [
    '--js-flags=--max_old_space_size=512',  # Cap V8 heap at 512MB
    '--renderer-process-limit=2',           # Limit renderer processes
    '--disable-features=VizDisplayCompositor',  # Reduce compositor overhead
    '--disable-site-isolation-trials',      # Save 9-11% memory (CAUTION: breaks Cloudflare)
    '--single-process',                     # Single process mode (trade-off: higher per-process memory)
]
```

### Tier 4: Frame Rate Control (for scraping/automation, not visual testing)

```python
FRAMERATE_FLAGS = [
    '--disable-frame-rate-limit',           # Don't cap at 60fps
    '--run-all-compositor-stages-before-draw',
    # Note: Chromium team acknowledges 60fps headless rendering is wasteful
    # and was working on programmatic frame production control
]
```

### Combined Recommended Configuration for Pythinker Sandbox

```python
SANDBOX_CHROMIUM_ARGS = [
    # Essential
    '--headless',
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    # Resource reduction
    '--disable-background-networking',
    '--disable-background-timer-throttling',
    '--disable-client-side-phishing-detection',
    '--disable-extensions',
    '--disable-renderer-backgrounding',
    '--disable-software-rasterizer',
    '--disable-component-update',
    '--disable-domain-reliability',
    '--mute-audio',
    '--no-first-run',
    # Memory
    '--js-flags=--max_old_space_size=512',
    '--renderer-process-limit=4',
    # Display
    '--window-size=1280,720',
    '--hide-scrollbars',
]
```

### Caveat

Aggressive flags (especially `--disable-site-isolation-trials` and `--single-process`) can break Cloudflare challenges and some modern web applications. Test thoroughly against target sites.

---

## 7. Browser Isolation: Contexts vs Containers

### Architecture Comparison

| Dimension | Browser Context | Docker Container |
|-----------|----------------|-----------------|
| Startup time | ~50-100 ms | 2-5 seconds |
| Memory overhead | ~10-50 MB | 200-500 MB (Chrome + OS) |
| Isolation level | Session-level (cookies, storage, cache) | Process + filesystem + network |
| Parallel capacity | 2-3x more on same hardware | Limited by container overhead |
| Security | Same browser process | Full process/namespace isolation |
| State cleanup | Automatic on context.close() | Requires container destroy |

### Playwright Context Isolation Model

```
Browser (single Chromium process, ~500 MB)
  |-- Context A (isolated: cookies, storage, cache, permissions)
  |     |-- Page 1
  |     |-- Page 2
  |-- Context B (completely separate session)
  |     |-- Page 3
  |-- Context C
        |-- Page 4
```

Each context is equivalent to an incognito window. Contexts share the browser process but have completely isolated state.

### Benchmark: Contexts vs Containers at Scale

From testdino.com performance benchmarks (2026):
- Running 5,000 tests/day with containers (Selenium Grid): **32 runner-hours/day**
- Running 5,000 tests/day with contexts (Playwright): **16 runner-hours/day** (50% fewer CI minutes)
- Case study: 60% faster CI runs on 8 machines after migrating from Selenium to Playwright (context model)
- Playwright runs **2-3x more parallel tests on the same hardware** vs Selenium Grid

### When to Use Which

**Use Browser Contexts when:**
- Session isolation is sufficient (different cookies/storage per user)
- Maximum throughput is needed
- Resource constraints are tight
- Multiple user simulations in same workflow

**Use Docker Containers when:**
- Full process isolation required (untrusted code execution)
- Filesystem isolation needed (sandboxed file operations)
- Network namespace isolation required
- Pythinker's use case: Agent-controlled browser needs filesystem + network isolation

### Pythinker Implication

Pythinker already uses Docker containers for sandbox isolation (agent-controlled terminal + browser + files). This is the correct choice given the security model. However, within each sandbox container, using browser contexts (not multiple browsers) for parallel operations would save resources.

---

## 8. Playwright Persistent Contexts for Resource Saving

### What Persistent Contexts Save

Standard workflow: Launch browser -> Create context -> Login -> Do work -> Close everything -> Repeat

Persistent context workflow: Launch once -> Save state to disk -> Reload state instantly on next run

### Authentication State Persistence

```python
# Save authentication state
storage = await context.storage_state(path='auth.json')

# Reuse in new context (skips login)
context = await browser.new_context(storage_state='auth.json')
```

**Impact:** Authentication typically takes 5-15 seconds per test. Across 100 tests, that is 8-25 minutes saved.

### launchPersistentContext

```python
context = await playwright.chromium.launch_persistent_context(
    user_data_dir='./user-data',
    headless=True,
    # All cookies, localStorage, IndexedDB persisted to disk
)
```

**Benefits:**
- Browser profile (cache, cookies, service workers) survives restarts
- Eliminates cold-start penalty for repeated visits to same sites
- Disk-based persistence means state survives container restarts

### Resource-Optimized Context Configuration

```python
context = await browser.new_context(
    device_scale_factor=1,        # No HiDPI overhead
    is_mobile=True,               # Mobile pages render less content
    viewport={'width': 375, 'height': 667},  # Small viewport = less rendering
    ignore_https_errors=True,     # Skip TLS verification overhead
    java_script_enabled=True,     # Only disable if not needed
    permissions=[],               # Deny all permissions by default
    accept_downloads=False,       # No download handling overhead
)
```

### Warning

Persistent contexts can make anti-bot detection easier since browser fingerprints become predictable. For scraping at scale, rotate persistent profiles.

---

## 9. Page Lifecycle Optimization

### Resource Blocking (Biggest Single Win for Scraping)

```python
# Block unnecessary resources
async def block_resources(route, request):
    if request.resource_type in ['image', 'stylesheet', 'font', 'media']:
        await route.abort()
    else:
        await route.continue_()

await page.route('**/*', block_resources)
```

**Impact:** Pages become lighter, navigation finishes sooner. Blocking images, fonts, and CSS on thousands of pages saves minutes of cumulative load time.

**Selective blocking by domain (more surgical):**
```python
# Block known analytics and ad domains
BLOCKED_DOMAINS = [
    '*google-analytics.com*',
    '*googletagmanager.com*',
    '*facebook.net*',
    '*doubleclick.net*',
    '*hotjar.com*',
]
for domain in BLOCKED_DOMAINS:
    await page.route(domain, lambda route: route.abort())
```

### Wait Strategy Optimization

| Strategy | When to Use | Performance Impact |
|----------|------------|-------------------|
| `networkidle` | Full page render needed | Slowest (waits for ALL network to quiet) |
| `domcontentloaded` | DOM-only scraping | Moderate (skips async resources) |
| `commit` | Fastest possible | Fastest (first byte received) |
| `wait_for_selector` | Specific element needed | Targeted (best for dynamic content) |

```python
# Fastest: don't wait for full load
await page.goto(url, wait_until='domcontentloaded')

# Even faster: just wait for the element you need
await page.goto(url, wait_until='commit')
await page.wait_for_selector('.product-price', timeout=5000)
```

### Browser Cache Optimization

```python
# Enable browser cache for repeated visits to same domain
context = await browser.new_context(
    # Don't clear cache between pages in same context
)

# Or disable cache when freshness matters
await page.set_cache_enabled(False)
```

### Parallelization with Multiple Pages

```python
async def scrape_page(context, url):
    page = await context.new_page()
    await page.goto(url, wait_until='domcontentloaded')
    data = await page.evaluate('() => document.title')
    await page.close()
    return data

# Process URLs in parallel batches
tasks = [scrape_page(context, url) for url in urls[:10]]
results = await asyncio.gather(*tasks)
```

### HAR Recording for Replay

```python
# Record network activity
await context.route_from_har('recording.har', update=True)
await page.goto(url)

# Replay from HAR (no network needed)
await context.route_from_har('recording.har')
await page.goto(url)  # Served from HAR file
```

---

## 10. Lightweight Alternatives to Full Browser

### The Spectrum of Approaches

| Approach | Memory per Instance | Speed | JS Support | Anti-Bot |
|----------|-------------------|-------|------------|----------|
| HTTPX | ~5-10 MB | Fastest | None | Low |
| curl_cffi | ~5-10 MB | Fast | None | High (TLS impersonation) |
| Lightpanda | 24 MB | 11x Chrome | Full (V8) | Low |
| Chrome headless | 207-500 MB | Baseline | Full | Medium |
| Chrome headful + Xvfb | 500-1100 MB | Slowest | Full | Highest |

### Lightpanda: Purpose-Built Headless Browser

**Architecture:** Built from scratch in Zig (not a Chromium fork). Uses V8 for JavaScript execution. No graphical rendering engine (no Blink, no Skia, no font/image rendering). Implements CDP natively.

**Benchmarks (AWS EC2 m5.large, 933 real web pages):**

| Concurrency | Lightpanda Memory | Chrome Memory | Lightpanda Time | Chrome Time |
|-------------|-------------------|---------------|-----------------|-------------|
| 1 | 24 MB peak | 207 MB peak | 2.3s | 25.2s |
| 25 | 215 MB | 2 GB | 3.2s | 46.7s |
| 100 | 696 MB | 4.2 GB | 4.45s | 69 min 37s |

**Key numbers:**
- 11x faster execution
- 9x lower memory usage
- 30x faster startup (0.1s vs 3-4s)
- At 100 concurrent sessions: Chrome collapses (69 min), Lightpanda stable (4.45s)
- Cost impact: ~$220/month savings on AWS ($2,640/year)

**CDP Compatibility:** Drop-in replacement — change 3 lines of code (WebSocket endpoint). Puppeteer and Playwright connect via `connectOverCDP`.

**Limitations (Beta, as of 2026):**
- Not all Web APIs implemented
- Complex sites may fail or crash
- No visual rendering (by design) — cannot take screenshots
- Not suitable when full browser fidelity is required

### curl_cffi: HTTP-Level Browser Impersonation

- Impersonates Chrome/Safari TLS fingerprints (JA3, HTTP/2 handshake)
- 30-50% faster throughput than `requests` library
- Supports HTTP/2 and HTTP/3
- No JavaScript execution — pure HTTP
- Best for: APIs, static pages, sites with TLS fingerprint detection

### HTTPX: Modern Async HTTP Client

- Fully async with `asyncio`
- HTTP/2 support
- Connection pooling built-in
- Best for: High-volume static page scraping
- Limitation: Standard TLS fingerprint easily detected by WAFs

### selectolax: Hyper-Fast HTML Parser

- Parses HTML 10-100x faster than BeautifulSoup
- Based on Modest (C library) and lexbor
- Ideal paired with HTTPX for high-throughput extraction
- No JavaScript execution

### Decision Matrix for Pythinker

| Pythinker Use Case | Recommended Approach |
|-------------------|---------------------|
| Agent browsing (interactive) | Chrome headless (current) |
| Research auto-enrichment (fetch & extract) | HTTPX + selectolax (or Scrapling) |
| Heavy scraping at scale | Consider Lightpanda when stable |
| Simple API calls | HTTPX (already used via HTTPClientPool) |
| Anti-bot sites | curl_cffi for HTTP, Chrome headful for JS |

---

## 11. Recommendations for Pythinker

### Priority 1: Quick Wins (Low Effort, High Impact)

**A. Optimize Chromium launch flags in sandbox**
- Add the Tier 2 resource reduction flags (see Section 6)
- Add `--js-flags=--max_old_space_size=512` to cap V8 heap
- Expected savings: 100-200 MB per browser instance

**B. Optimize CDP screencast parameters**
- Switch to JPEG format at quality 50 (from likely higher)
- Reduce resolution to 960x540 for monitoring stream
- Set `everyNthFrame: 3` for monitoring (5-10 fps is sufficient)
- ACK frames immediately, process asynchronously
- Expected savings: 50-80% CPU reduction in screencast subsystem

**C. Add resource blocking for research/scraping**
- Block images, fonts, media, analytics when not needed for visual tasks
- Use `page.route()` with domain-based blocklist
- Expected savings: 30-50% faster page loads, significant bandwidth reduction

### Priority 2: Medium Effort, Significant Impact

**D. Browser context reuse within sandbox**
- Reuse the browser instance across multiple agent operations
- Create fresh contexts (not browsers) for isolation between tasks
- Expected savings: 2-5 second startup elimination per task

**E. Tiered scraping approach**
- Use HTTPX + selectolax for the auto-enrichment pipeline (`_auto_enrich_results()`)
- Only escalate to full browser when JavaScript rendering is required
- Expected savings: 90%+ memory and CPU for enrichment workload

**F. Docker memory constraints**
- Set `shm_size: '2gb'` in sandbox service
- Set `deploy.resources.limits.memory: 2G`
- Add cgroup-based resource limits to prevent OOM cascading

### Priority 3: Future Investigation

**G. Lightpanda evaluation**
- When it exits beta, evaluate for non-interactive scraping
- 9x memory reduction would allow 9x more concurrent sandbox operations
- CDP-compatible: would require minimal code changes

**H. Persistent browser profiles for repeated sites**
- For research pipelines that hit the same domains repeatedly
- Cache and cookie persistence reduces redundant resource loading

---

## Sources

- [Playwright Browser Footprint](https://datawookie.dev/blog/2025-06-06-playwright-browser-footprint/) — Memory benchmarks for Chromium/Firefox/WebKit
- [Chrome Flags for Test Automation 2026](https://bug0.com/blog/chrome-flags-2026) — Docker/CI flag guide
- [CDP Screencast Low FPS](https://stackoverflow.com/questions/71437739/page-startscreencast-chrome-devtools-protocol-low-fps-issue) — Screencast ACK bottleneck
- [Lightpanda Benchmarks](https://topaiproduct.com/2026/03/15/lightpanda-browser-loads-100-pages-in-2-3-seconds-chrome-needs-25/) — 100-page benchmark
- [Lightpanda Real-World Benchmarks](https://emelia.io/hub/lightpanda-headless-browser) — 933-page AWS EC2 benchmark at 25/100 concurrency
- [Playwright Performance Benchmark 2026](https://testdino.com/blog/performance-benchmarks/) — Context vs container comparison
- [Playwright Best Practices](https://playwright.dev/docs/best-practices) — Official optimization guide
- [Playwright Isolation](https://playwright.dev/docs/browser-contexts) — Context isolation model
- [Chrome Headless CPU/Memory](https://stackoverflow.com/questions/50701824/limit-chrome-headless-cpu-and-memory-usage) — cgroups, V8 flags, frame rate
- [Chromium headless-dev mailing list](https://groups.google.com/a/chromium.org/g/headless-dev/c/f_tQUs__Yqw) — Building for minimum CPU+memory
- [Docker /dev/shm Configuration](https://last9.io/blog/how-to-configure-dockers-shared-memory-size-dev-shm/) — Shared memory troubleshooting
- [Puppeteer Memory Leak Journey](https://medium.com/@matveev.dina/the-hidden-cost-of-headless-browsers-a-puppeteer-memory-leak-journey-027e41291367) — Browser lifecycle management
- [WebdriverIO Headless & Xvfb](https://webdriver.io/docs/headless-and-xvfb) — When to use Xvfb vs native headless
- [Headless vs Headful Benchmarks](https://anchorbrowser.io/blog/choosing-headful-over-headless-browsers) — CPU/memory/elapsed comparison
- [Headless vs Headful 2025](https://scrapingant.com/blog/headless-vs-headful-browsers-in-2025-detection-tradeoffs) — 2-15x speed improvement
- [Best Python Scraping Libraries 2026](https://www.olostep.com/blog/best-python-web-scraping-libraries) — HTTPX vs curl_cffi vs Playwright comparison
- [curl_cffi for Web Scraping](https://brightdata.com/blog/web-data/web-scraping-with-curl-cffi) — TLS impersonation guide
- [Chromium Command Line Switches](https://peter.sh/experiments/chromium-command-line-switches/) — Complete flag reference
- [Playwright Web Scraping Speed](https://www.scrapingbee.com/blog/playwright-web-scraping/) — Resource blocking patterns
- [Advanced Playwright Patterns](https://medium.com/@peyman.iravani/advanced-playwright-patterns-parallel-testing-and-resource-management-3e4e71e09801) — Resource pooling architecture
- [Speed Up Playwright Tests](https://currents.dev/posts/how-to-speed-up-playwright-tests) — Persistent auth, resource blocking
