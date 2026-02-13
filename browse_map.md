# Browser Content Capture Architecture - Pythinker

**Last Updated**: 2026-02-13
**Purpose**: Complete documentation of how the Pythinker agent captures information from browsing pages

---

## Table of Contents

1. [Overview](#overview)
2. [Two-Tier Content Capture Strategy](#two-tier-content-capture-strategy)
3. [Page Content Extraction Mechanisms](#page-content-extraction-mechanisms)
4. [Browser Implementation: Playwright](#browser-implementation-playwright)
5. [Performance Safeguards](#performance-safeguards)
6. [Page Intent-Based Optimization](#page-intent-based-optimization)
7. [Anti-Bot Detection Features](#anti-bot-detection-features)
8. [Data Flow: Request → Agent](#data-flow-request--agent)
9. [Error Handling & Recovery](#error-handling--recovery)
10. [Performance Characteristics](#performance-characteristics)
11. [Key Files & Locations](#key-files--locations)

---

## Overview

Pythinker uses a **hybrid two-tier approach** for capturing web page content:

1. **Fast HTTP-based fetch** (100-500ms) - Primary path for simple content extraction
2. **Full browser navigation** (2-10s) - Fallback for interactive pages and JavaScript-heavy sites

This design prioritizes:
- **Speed**: Fast HTTP path for most requests
- **Reliability**: Circuit breaker, crash detection, automatic recovery
- **Stealth**: Anti-bot detection masking
- **Memory Efficiency**: Smart extraction limits and caching

---

## Two-Tier Content Capture Strategy

### Tier 1: Fast HTTP-Based Fetch (Primary Path)

**File**: `backend/app/domain/services/tools/browser.py`

**Tool**: `search()` - Primary browser tool for content extraction

**Speed**: ~100-500ms per page

#### Process Flow

```
User Request → HTTP GET (aiohttp) → HTML → html_to_text() → Clean text
```

#### Implementation Details

```python
async def search(self, url: str, focus: str | None = None) -> ToolResult:
    """Fast HTTP-based content fetching (no browser overhead)

    Strategy:
    1. Attempt lightweight HTTP GET with aiohttp
    2. Convert HTML to clean text without external deps
    3. Detect paywalls and access restrictions
    4. Extract focused content if specified
    5. Fall back to full browser navigation on failure
    """
```

#### Features

1. **HTTP Client Pool**
   - Shared `aiohttp.ClientSession` with connection pooling
   - Reduced timeouts: 15s total, 5s connect, 10s read
   - User-Agent header for realistic requests

2. **HTML → Text Conversion** (`html_to_text()` - lines 129-186)
   - Preserves headings as markdown (`# ## ###`)
   - Preserves links as `[text](url)`
   - Preserves list items with `-`
   - Converts tables to pipe-separated format
   - Removes scripts, styles, and HTML entities
   - **Limits**: 50,000 characters by default

3. **Paywall Detection**
   - Uses `PaywallDetector` to identify restricted content
   - Skips detection for known open-access domains (GitHub, Stack Overflow, etc.)
   - Returns `access_status`: `"full"`, `"partial"`, or `"paywall"`

4. **Focused Content Extraction**
   ```python
   def _extract_focused_content(self, text: str, focus: str | None) -> str:
       # Splits content into paragraphs
       # Scores by keyword matching and phrase presence
       # Returns high-scoring paragraphs first + context
   ```

5. **URL Caching**
   - LRU cache (5-min TTL, max 50 URLs) to avoid re-fetching
   - Tracks repeated visits and warns/rejects after 3 visits

---

### Tier 2: Full Browser Navigation (Fallback Path)

**File**: `backend/app/infrastructure/external/browser/playwright_browser.py`

**Tool**: `browser_navigate()` - Full browser automation with page extraction

**Speed**: ~2-10s per page

#### Process Flow

```python
async def navigate(self, url: str, auto_extract: bool = True) -> ToolResult:
    """Full browser navigation with automatic content extraction

    Process:
    1. Serial navigation lock (prevents concurrent page.goto() race conditions)
    2. Circuit breaker check (fail-fast if too many crashes)
    3. Page load wait (domcontentloaded or networkidle)
    4. Automatic smart scrolling for lazy-loaded content
    5. Parallel extraction of elements + content
    6. Return interactive elements list + full page text
    """
```

---

## Page Content Extraction Mechanisms

### A. Interactive Element Extraction

**Method**: `_extract_interactive_elements()` (lines 1908-2091)

**Purpose**: Find all clickable/interactive elements on the page for agent actions

#### JavaScript DOM Scanning Strategy

```javascript
// 1. Select Interactive Elements
document.querySelectorAll(
    'button, a[href], input:not([type="hidden"]), textarea, select, ' +
    '[role="button"], [role="link"], [onclick], [tabindex]:not([tabindex="-1"])'
)
```

#### Performance Optimization

**Limits**:
- **MAX_INTERACTIVE_ELEMENTS = 100** (prevents hangs on heavy pages)
- **5s timeout** with exponential backoff retries
- Falls back to coordinate-based clicking on timeout

**Fast Visibility Checks**:
```javascript
// Quick bounds check (fast)
if (rect.width < 1 || rect.height < 1) continue;
if (rect.bottom < 0 || rect.top > viewportHeight) continue;

// Hidden element check (fast path - avoids expensive getComputedStyle)
if (element.offsetParent === null && element.tagName !== 'BODY') {
    // Only expensive style check if potentially fixed/sticky
    const style = window.getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
}
```

#### Text Extraction with Context

- **For inputs/textareas**: Include associated label and placeholder
- **For buttons/links**: Extract `innerText`
- **Fallback chain**: `value` → `innerText` → `alt` → `title` → `placeholder` → `type`

#### Element Identification

1. Mark each element with `data-pythinker-id` attribute
2. Return formatted list: `"0:<button>Click Me</button>"`
3. Later lookups use selector strategy:
   - `[data-pythinker-id="pythinker-element-N"]` (primary)
   - Original selector from cache (fallback 1)
   - Text-based matching (fallback 2)
   - Refresh element list and retry (fallback 3)

#### Metrics Recorded

- `browser_element_extraction_total` - Success/timeout/error counts
- `browser_element_extraction_latency` - Extraction duration
- `browser_element_extraction_timeout_total` - Timeout attempts
- Cache hits/misses tracking

---

### B. Page Content Extraction

**Method**: `_extract_content()` (lines 1708-1792)

**Purpose**: Extract visible text content from the page

#### Two-Phase Strategy

**Phase 1: Semantic HTML Detection (Fast Path)**

```javascript
// Check for main content areas first
const mainSelectors = ['main', 'article', '[role="main"]',
                      '.content', '#content', '.post', '.entry'];

for (const selector of mainSelectors) {
    const mainContent = document.querySelector(selector);
    if (mainContent && mainContent.innerText?.length > 500) {
        return mainContent.innerText.slice(0, 30000);
    }
}
```

**Phase 2: TreeWalker Traversal (Fallback)**

```javascript
// More efficient than querySelectorAll for text extraction
const walker = document.createTreeWalker(
    document.body,
    NodeFilter.SHOW_TEXT,
    {
        acceptNode: function(node) {
            // Skip script, style, noscript
            const parent = node.parentElement;
            if (!parent) return NodeFilter.FILTER_REJECT;
            if (parent.tagName in ['SCRIPT', 'STYLE', 'NOSCRIPT']) {
                return NodeFilter.FILTER_REJECT;
            }
            return NodeFilter.FILTER_ACCEPT;
        }
    }
);

// Walk document collecting text nodes
// Limits to:
// - MAX_CHARS = 30,000
// - MAX_ELEMENTS = 200 text nodes
// - Viewport height + 2x for below-fold content
```

#### Extraction Limits

- **Timeout**: 3 seconds per extraction
- **Max Characters**: 30,000
- **Max Text Nodes**: 200
- **Viewport Range**: Current viewport + 2x below-fold

---

## Browser Implementation: Playwright

**File**: `backend/app/infrastructure/external/browser/playwright_browser.py`

### Connection Management

- **CDP Connection Pool**: `backend/app/infrastructure/external/browser/connection_pool.py`
  - Per-CDP-URL pooling
  - Health checking and automatic reconnection
  - Stale connection cleanup
  - Automatic recovery with retry logic

- **Window Positioning**: Critical for VNC display
  - Uses Chrome DevTools Protocol (CDP) `Browser.setWindowBounds`
  - Ensures window stays at (0,0) to match Xvfb display
  - Reuses existing windows to avoid positioning issues

### Browser Configuration

```python
# Default browser settings
DEFAULT_VIEWPORT = {"width": 1280, "height": 900}
DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36..."
DEFAULT_TIMEZONE = "America/New_York"

# Randomization for stealth mode
USER_AGENT_POOL = [5 variations]  # Chrome/Windows/macOS
VIEWPORT_POOL = [5 variations]    # 1280x900, 1024x768, etc.
TIMEZONE_POOL = [6 variations]    # NY, Chicago, LA, Denver, London, Berlin
```

### Network Optimization

**Resource Blocking** (optional performance feature):

```python
BLOCKABLE_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}
BLOCKED_URL_PATTERNS = [
    r".*\.doubleclick\.net.*",      # Google ads
    r".*google-analytics.*",         # Analytics
    r".*facebook\.net.*",            # Facebook tracking
    r".*tracking.*", ".*analytics.*" # Generic tracking
]
```

### Crash Detection & Recovery

**Circuit Breaker Pattern** (lines 399-431):

```python
# Tracks crash history with configurable window/threshold
self._crash_history: list[float] = []
self._crash_window_seconds: float = 300.0    # 5-min window
self._crash_threshold: int = 3               # Fail after 3 crashes
self._crash_cooldown_seconds: float = 60.0   # 1-min cooldown

# Fails fast if circuit opens
def _check_circuit_breaker(self) -> bool:
    if current_time < self._circuit_open_until:
        return False  # Circuit open, reject operations
    # Clean old crashes outside window
    self._crash_history = [ts for ts in self._crash_history if ts > cutoff]
    # Open circuit if threshold exceeded
    if len(self._crash_history) >= self._crash_threshold:
        self._circuit_open_until = current_time + self._crash_cooldown_seconds
        return False
    return True
```

**Crash Signatures** (lines 94-105):

```python
BROWSER_CRASH_SIGNATURES = [
    "Target closed",
    "Target crashed",
    "Target page, context or browser has been closed",
    "Browser has been closed",
    "Session closed",
    "Execution context was destroyed",
    "Protocol error",
    "Connection closed",
    "Page crashed"
]
```

### Page Load Waiting

```python
async def wait_for_page_load(self, timeout: int = 30000) -> bool:
    """Wait for page to be ready before extraction

    Waits for:
    1. DOMContentLoaded (faster)
    2. Page ready via JavaScript (interactive elements available)
    3. Network idle (optional, for full page load)
    """
```

---

## Performance Safeguards

### 1. Quick Page Complexity Check

```python
async def _quick_page_size_check(self) -> dict:
    """Detect heavy pages BEFORE expensive DOM operations

    Returns:
    - htmlSize: document.documentElement.innerHTML.length
    - domCount: document.querySelectorAll('*').length
    - isHeavy: boolean flag for heavy pages

    Timeout: 500ms (very quick)
    """
```

### 2. Memory Pressure Monitoring

**Via CDP Performance.getMetrics**:

```python
async def _check_memory_pressure(self) -> dict:
    """Monitor JS heap usage to detect memory pressure

    Pressure levels:
    - low: < 300MB
    - medium: 300-high_threshold
    - high: high_threshold-critical_threshold
    - critical: > critical_threshold OR > 10k DOM nodes

    Used to trigger lightweight extraction modes
    """
```

### 3. Wikipedia Special Handling

```python
async def _extract_wikipedia_summary(self) -> dict:
    """Extract lightweight summary instead of full Wikipedia page

    - Extracts only lead section (first 3 paragraphs)
    - Skips tables, references, navigation, sidebars
    - Prevents memory crashes on heavy Wikipedia pages
    """
```

---

## Page Intent-Based Optimization

**File**: `backend/app/domain/services/tools/browser.py` (lines 20-57)

Three browsing intents with different configurations:

```python
class BrowserIntent(str, Enum):
    NAVIGATIONAL = "navigational"    # General browsing, exploring
    INFORMATIONAL = "informational"  # Content extraction, research
    TRANSACTIONAL = "transactional"  # Form filling, purchases

BROWSER_INTENT_CONFIG = {
    BrowserIntent.NAVIGATIONAL: {
        "auto_scroll": True,
        "extract_interactive": True,
        "extract_content": True,
        "wait_for_network_idle": False,
        "max_content_length": 50000,
    },
    BrowserIntent.INFORMATIONAL: {
        "auto_scroll": True,
        "extract_interactive": False,      # Focus on content
        "extract_content": True,
        "wait_for_network_idle": True,     # Wait for all content
        "max_content_length": 100000,      # Allow more content
    },
    BrowserIntent.TRANSACTIONAL: {
        "auto_scroll": False,              # Don't scroll past form
        "extract_interactive": True,       # Need form elements
        "extract_content": False,          # Focus on interactions
        "wait_for_network_idle": True,
        "max_content_length": 20000,
    },
}
```

---

## Anti-Bot Detection Features

### Anti-Detection Script Injection

Injects JavaScript to mask automation signals:

```javascript
// Mask webdriver detection
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Mock plugins (empty indicates headless)
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
        {name: 'Chrome PDF Viewer', filename: '...'},
        {name: 'Native Client', filename: '...'}
    ]
});

// Mock languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});

// Override chrome.runtime
window.chrome.runtime = { PlatformOs: {...}, ... };
```

### Stealth Mode Features

- Random user agent rotation
- Random viewport size selection
- Random timezone assignment
- Human-like delays between actions (100-2000ms)
- Bypass of bot detection via init scripts

---

## Data Flow: Request → Agent

```
┌─────────────────────────────────────────────────────────────────┐
│ User Request: "Navigate to example.com"                         │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ BrowserTool.search() or browser_navigate()                      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
              ┌─────────────┴─────────────┐
              │                           │
        [Fast Path]                 [Fallback Path]
   HTTP GET (100-500ms)         Browser Navigate (2-10s)
              │                           │
   ┌──────────┴──────────┐    ┌──────────┴──────────┐
   │ html_to_text()      │    │ Playwright.navigate()│
   │ - Clean text        │    │                      │
   │ - Paywall check     │    │ ├─ Serial lock       │
   │ - Cache check       │    │ ├─ Circuit breaker   │
   └──────────┬──────────┘    │ ├─ Wait for load     │
              │               │ ├─ Check complexity  │
              │               │ └─ Parallel extract: │
              │               │    ├─ Elements        │
              │               │    └─ Content         │
              │               └──────────┬──────────┘
              │                          │
              └────────────┬─────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ ToolResult:                                                     │
│ {                                                               │
│   "interactive_elements": [                                     │
│     "0:<button>Login</button>",                                 │
│     "1:<a>Sign Up</a>",                                         │
│     "2:<input>Email</input>",                                   │
│     ...                                                         │
│   ],                                                            │
│   "content": "Welcome to Example.com. This is the main...",     │
│   "url": "https://example.com",                                 │
│   "title": "Example Domain",                                    │
│   "access_status": "full",                                      │
│   "cached": false                                               │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Agent Processing:                                               │
│                                                                 │
│ 1. Interactive elements → Tool action indices                   │
│    - Element "0" can be clicked with browser_click(0)          │
│    - Element "2" can be filled with browser_input(2, "text")   │
│                                                                 │
│ 2. Content → Context for decision-making                        │
│    - Analyze page content to understand current state          │
│    - Determine next action based on goal                       │
│                                                                 │
│ 3. Plan next action                                             │
│    - "I see a login button. I should click element 0."         │
│    - "I need to fill in the email field (element 2) first."    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Error Handling & Recovery

### Browser Retry Logic

- **Element extraction**: Up to 3 retries with exponential backoff (configurable)
- **Navigation**: Single attempt with timeout protection
- **Crash detection**: Automatic health checks before operations
- **VNC display fallback**: Non-blocking best-effort navigation

### Graceful Degradation

| Failure Scenario | Graceful Degradation |
|------------------|----------------------|
| Element extraction timeout | Fall back to coordinate-based clicking |
| Content extraction timeout | Return error message with partial content |
| Heavy page detection | Switch to lightweight extraction mode |
| Wikipedia page | Extract only lead section instead of full page |
| Circuit breaker opens | Reject operations, return cached error |
| Memory pressure critical | Skip content extraction, elements only |

### Circuit Breaker States

```
CLOSED (Normal) → [3 crashes in 5 min] → OPEN (Fail Fast)
                                              ↓
                                    [Wait 60s cooldown]
                                              ↓
                                        HALF-OPEN (Test)
                                              ↓
                        [Success] → CLOSED | [Fail] → OPEN
```

---

## Performance Characteristics

### Operation Timings

| Operation | Time Range | Method |
|-----------|-----------|--------|
| HTTP-based content fetch | 100-500ms | aiohttp GET + html_to_text |
| Browser navigation | 2-10s | Playwright navigate + wait |
| Element extraction | 100-500ms | DOM query + visibility checks |
| Content extraction | 500-3000ms | TreeWalker traversal |
| Cache hit | <10ms | Memory lookup (LRU) |
| Quick health check | <3s | JavaScript evaluation |
| Page complexity check | <500ms | DOM count query |

### Memory Optimization

- **Extraction cache** (10-15s TTL) prevents duplicate work
- **Parallel extraction** (`asyncio.gather`) maximizes throughput
- **Element limit** (100 interactive) prevents memory bloat
- **Content limit** (30,000 chars) prevents large allocations
- **Connection pooling** reduces overhead per request

### Metrics Tracked

**Prometheus Metrics**:
- `browser_element_extraction_total{status="success|timeout|error"}`
- `browser_element_extraction_latency` (histogram)
- `browser_element_extraction_timeout_total`
- `browser_cache_hit_total`
- `browser_cache_miss_total`
- `browser_crash_total`
- `browser_circuit_breaker_open_total`

---

## Key Files & Locations

### Core Components

| Component | File Path | Lines | Purpose |
|-----------|-----------|-------|---------|
| **Browser Protocol** | `backend/app/domain/external/browser.py` | All | Interface contract for browser implementations |
| **BrowserTool** | `backend/app/domain/services/tools/browser.py` | All | Fast HTTP-based content capture |
| **PlaywrightBrowser** | `backend/app/infrastructure/external/browser/playwright_browser.py` | All | Full browser automation implementation |
| **Connection Pool** | `backend/app/infrastructure/external/browser/connection_pool.py` | All | CDP connection management & retry logic |
| **BrowserAgent** | `backend/app/domain/services/tools/browser_agent.py` | All | Browser tool orchestration |

### Key Methods

| Method | File | Lines | Purpose |
|--------|------|-------|---------|
| `search()` | `browser.py` (tool) | ~100-250 | Fast HTTP content fetch |
| `navigate()` | `playwright_browser.py` | ~800-900 | Full browser navigation |
| `_extract_interactive_elements()` | `playwright_browser.py` | 1908-2091 | DOM element extraction |
| `_extract_content()` | `playwright_browser.py` | 1708-1792 | Page text extraction |
| `html_to_text()` | `browser.py` (tool) | 129-186 | HTML → clean text conversion |
| `_check_circuit_breaker()` | `playwright_browser.py` | 399-431 | Crash detection & fail-fast |
| `_check_memory_pressure()` | `playwright_browser.py` | ~2300 | Memory monitoring |
| `_extract_wikipedia_summary()` | `playwright_browser.py` | ~2400 | Wikipedia optimization |

### Supporting Files

| File | Purpose |
|------|---------|
| `backend/app/domain/models/tool_result.py` | ToolResult data model |
| `backend/app/domain/services/tools/paywall_detector.py` | Paywall detection logic |
| `backend/app/infrastructure/external/http_client_pool.py` | HTTP connection pooling |

---

## Debugging & Observability

### Monitoring Stack

When debugging browser issues, always check:

1. **Docker Logs**: `docker logs pythinker-backend-1 --tail 200`
2. **Grafana Dashboards**: http://localhost:3001
3. **Loki Logs**: Use Grafana Explore with LogQL
   ```
   {container_name="pythinker-backend-1"} |= "browser" |~ "error|crash|timeout"
   ```
4. **Prometheus Metrics**: http://localhost:9090
   ```
   rate(browser_crash_total[5m])
   rate(browser_element_extraction_timeout_total[5m])
   ```

### Common Debug Queries

**Find browser crashes in last hour**:
```
{container_name="pythinker-backend-1"} |= "browser" |= "crash" | json
```

**Track slow extractions**:
```
histogram_quantile(0.95, browser_element_extraction_latency)
```

**Monitor circuit breaker activations**:
```
rate(browser_circuit_breaker_open_total[10m])
```

---

## Future Enhancements

### Potential Improvements

1. **Smart Content Prioritization**
   - Machine learning-based content relevance scoring
   - Dynamic extraction depth based on task context

2. **Advanced Caching**
   - Redis-backed distributed cache
   - Semantic similarity-based cache hits

3. **Parallel Browser Pools**
   - Multiple browser instances for concurrent operations
   - Load balancing across sandbox containers

4. **Enhanced Stealth**
   - Canvas fingerprinting randomization
   - WebGL fingerprinting masking
   - Advanced timing attack prevention

5. **Content Understanding**
   - Semantic HTML structure analysis
   - Automatic schema.org extraction
   - Multi-modal content (images, videos) understanding

---

## Related Documentation

- **Browser Crash Prevention**: `docs/research/BROWSER_CRASH_PREVENTION_APPLIED.md`
- **SSE Timeout & UX Bugs**: `docs/fixes/SSE_TIMEOUT_AND_UX_BUGS.md`
- **Browser Retry Progress**: `docs/fixes/BROWSER_RETRY_PROGRESS_EVENTS.md`
- **VNC Reconnection**: `docs/plans/2026-02-13-vnc-reconnection-progress-design.md`
- **Session Persistence**: `docs/fixes/PAGE_REFRESH_SESSION_PERSISTENCE.md`

---

**Document Version**: 1.0
**Reviewed By**: Explore Agent (a44b2fa)
**Validation**: Context7 MCP - Playwright `/microsoft/playwright` (Score: 94.9/100)
