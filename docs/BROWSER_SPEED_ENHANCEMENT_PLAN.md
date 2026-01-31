# Browser View Speed Enhancement Plan

## ✅ IMPLEMENTED (2026-01-30)

**Status:** Phase 1 & 2 implemented and tested. All 458 backend tests pass.

**Changes made to `backend/app/infrastructure/external/browser/playwright_browser.py`:**
- Added `_evaluate_with_timeout()` helper with Promise.race timeout wrapper (5s default)
- Added `_get_page_complexity()` for heavy page detection (>3000 elements)
- Replaced `_extract_content()` - removed LLM call, uses TreeWalker with element limits
- Replaced `_extract_interactive_elements()` - 100 element max, faster visibility checks
- Updated `view_page()` - parallel extraction with asyncio.gather, 10s TTL cache
- Added constants: `MAX_INTERACTIVE_ELEMENTS=100`, `JS_EVAL_TIMEOUT_MS=5000`, etc.

---

## Executive Summary

Based on research from latest Playwright best practices, Browser-Use library, and LLM agent optimization techniques, this plan outlines improvements to reduce `browser_view` execution time from **2-4 minutes to under 5 seconds**.

## Current Problem Analysis

| URL Type | Current Time | Target |
|----------|--------------|--------|
| Documentation sites (claude.com) | 239 seconds | <5s |
| Blog/Article pages | 113 seconds | <5s |
| Simple pages | 32 seconds | <3s |

**Root Causes Identified:**
1. `_extract_interactive_elements()` - JavaScript loops over thousands of DOM elements
2. `_extract_content()` - Heavy DOM traversal and text extraction
3. No timeouts on `page.evaluate()` calls
4. No element count limits
5. Waiting for full page load when not needed

---

## Phase 1: Quick Wins (1-2 hours)

### P1.1: Add JavaScript Execution Timeouts

**Problem:** `page.evaluate()` can hang indefinitely on heavy pages.

**Solution:** Wrap all JavaScript evaluations with Promise.race timeout:

```python
async def _evaluate_with_timeout(self, script: str, timeout_ms: int = 5000):
    """Execute JavaScript with timeout protection."""
    timeout_script = f"""
    Promise.race([
        (async () => {{ {script} }})(),
        new Promise((_, reject) =>
            setTimeout(() => reject(new Error('JS timeout')), {timeout_ms})
        )
    ])
    """
    try:
        return await self.page.evaluate(timeout_script)
    except Exception as e:
        logger.warning(f"JS evaluation timeout/error: {e}")
        return None
```

### P1.2: Limit Interactive Element Count

**Problem:** Pages with 1000+ interactive elements cause slowdowns.

**Solution:** Cap elements at 100-150 max:

```javascript
// In _extract_interactive_elements
const MAX_ELEMENTS = 100;
const elements = document.querySelectorAll('button, a, input, ...');
// Only process first MAX_ELEMENTS
for (let i = 0; i < Math.min(elements.length, MAX_ELEMENTS); i++) {
    // ...existing logic...
}
```

### P1.3: Use `domcontentloaded` Instead of `load`

**Problem:** Waiting for full `load` event includes images, fonts, ads.

**Solution:** Already using `domcontentloaded` - verify it's consistent everywhere.

---

## Phase 2: Performance Optimizations (2-4 hours)

### P2.1: Batch DOM Queries

**Problem:** Multiple `querySelectorAll` calls are expensive.

**Solution:** Single query with combined selectors:

```javascript
// Before (multiple queries)
const buttons = document.querySelectorAll('button');
const links = document.querySelectorAll('a');
const inputs = document.querySelectorAll('input');

// After (single query)
const interactive = document.querySelectorAll(
    'button, a[href], input:not([type="hidden"]), textarea, select, [role="button"], [onclick]'
);
```

### P2.2: Early Bailout for Heavy Pages

**Problem:** No way to detect and abort on extremely heavy pages.

**Solution:** Add pre-flight check:

```python
async def _check_page_complexity(self) -> dict:
    """Quick complexity check before full extraction."""
    stats = await self.page.evaluate("""() => ({
        elementCount: document.querySelectorAll('*').length,
        scriptCount: document.scripts.length,
        iframeCount: document.querySelectorAll('iframe').length
    })""")
    return stats

async def view_page(self, wait_for_load: bool = True) -> ToolResult:
    # Quick complexity check
    complexity = await self._check_page_complexity()
    if complexity['elementCount'] > 5000:
        # Use lightweight extraction
        return await self._view_page_lightweight()
```

### P2.3: Skip `browser_view` After Navigation

**Problem:** `browser_navigate` already extracts elements, then agent calls `browser_view` again.

**Solution:** Cache extraction results and detect duplicate calls:

```python
class PlaywrightBrowser:
    def __init__(self):
        self._last_extraction_url = None
        self._last_extraction_time = 0
        self._extraction_cache = None

    async def view_page(self, wait_for_load: bool = True) -> ToolResult:
        # Return cached if same URL and within 10 seconds
        if (self.page.url == self._last_extraction_url and
            time.time() - self._last_extraction_time < 10):
            return self._extraction_cache
```

### P2.4: Lazy Element Attribute Extraction

**Problem:** Extracting all attributes for every element is expensive.

**Solution:** Only extract essential attributes:

```javascript
// Only get what's needed
const essentialData = {
    tag: element.tagName.toLowerCase(),
    text: element.innerText?.slice(0, 100) || '',
    // Skip: computedStyle, full attributes, etc.
};
```

---

## Phase 3: Architecture Improvements (4-8 hours)

### P3.1: Parallel Extraction Pipeline

**Problem:** Sequential extraction of elements and content.

**Solution:** Use `Promise.all` for parallel extraction:

```python
async def view_page(self, wait_for_load: bool = True) -> ToolResult:
    # Run extractions in parallel
    elements_task = asyncio.create_task(self._extract_interactive_elements())
    content_task = asyncio.create_task(self._extract_content_lightweight())

    elements, content = await asyncio.gather(
        elements_task, content_task,
        return_exceptions=True
    )
```

### P3.2: Incremental/Viewport-Only Extraction

**Problem:** Extracting content for entire page when only viewport matters.

**Solution:** Only extract what's visible:

```javascript
// Only elements in viewport
const viewportHeight = window.innerHeight;
const viewportWidth = window.innerWidth;

elements.forEach(el => {
    const rect = el.getBoundingClientRect();
    // Skip if not in viewport
    if (rect.bottom < 0 || rect.top > viewportHeight) return;
    if (rect.right < 0 || rect.left > viewportWidth) return;
    // ... process element
});
```

### P3.3: Web Worker for Heavy Extraction

**Problem:** Heavy JavaScript blocks the main thread.

**Solution:** Offload to Web Worker (complex, lower priority):

```javascript
// Consider for very heavy pages
const worker = new Worker('extraction-worker.js');
worker.postMessage({ type: 'extract' });
```

---

## Phase 4: Smart Caching & Preloading (2-4 hours)

### P4.1: Content-Aware Caching

**Problem:** Same pages extracted multiple times.

**Solution:** Hash-based content caching:

```python
import hashlib

class ExtractionCache:
    def __init__(self, ttl_seconds=60):
        self._cache = {}
        self._ttl = ttl_seconds

    def get_key(self, url: str, viewport: tuple) -> str:
        return hashlib.md5(f"{url}:{viewport}".encode()).hexdigest()

    def get(self, url: str, viewport: tuple):
        key = self.get_key(url, viewport)
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry['time'] < self._ttl:
                return entry['data']
        return None
```

### P4.2: Speculative Pre-extraction

**Problem:** Agent waits for extraction after clicking links.

**Solution:** Pre-extract hovered/likely-next links:

```python
async def preload_link(self, index: int):
    """Speculatively load link content in background."""
    # When agent hovers or considers a link, start loading
    asyncio.create_task(self._background_extract(index))
```

---

## Phase 5: LLM Integration Optimizations (2-4 hours)

### P5.1: Structured Output for Faster Parsing

**Problem:** Large text content passed to LLM.

**Solution:** Return structured JSON instead of text:

```python
return ToolResult(
    success=True,
    data={
        "elements": elements[:50],  # Limit to top 50
        "content_summary": content[:2000],  # Truncate
        "page_type": detected_type,  # "article", "search", "form", etc.
        "key_actions": ["login", "search", "navigate"],  # Suggested actions
    }
)
```

### P5.2: Page Type Detection for Smart Extraction

**Problem:** Same extraction logic for all page types.

**Solution:** Detect page type and use appropriate extractor:

```python
async def _detect_page_type(self) -> str:
    """Detect page type for optimized extraction."""
    indicators = await self.page.evaluate("""() => ({
        hasSearchForm: !!document.querySelector('input[type="search"], form[role="search"]'),
        hasArticle: !!document.querySelector('article, [role="article"]'),
        hasLogin: !!document.querySelector('input[type="password"]'),
        hasList: document.querySelectorAll('ul li, ol li').length > 10,
    })""")

    if indicators['hasSearchForm']: return 'search'
    if indicators['hasArticle']: return 'article'
    if indicators['hasLogin']: return 'login'
    return 'generic'
```

---

## Implementation Priority

| Phase | Estimated Impact | Effort | Priority |
|-------|------------------|--------|----------|
| P1: Quick Wins | 50% reduction | 1-2h | **HIGH** |
| P2: Performance Opts | 30% reduction | 2-4h | **HIGH** |
| P3: Architecture | 40% reduction | 4-8h | MEDIUM |
| P4: Caching | 20% reduction | 2-4h | MEDIUM |
| P5: LLM Integration | 15% reduction | 2-4h | LOW |

---

## Success Metrics

| Metric | Current | Target | Method |
|--------|---------|--------|--------|
| `browser_view` avg time | 120s | <5s | Tool profiler |
| Elements extracted | Unlimited | Max 100 | Count cap |
| JS evaluation timeout | None | 5s | Timeout wrapper |
| Cache hit rate | 0% | >50% | Cache instrumentation |

---

## References

1. [Playwright Web Scraping Best Practices](https://www.scrapingbee.com/blog/playwright-web-scraping/) - Use `domcontentloaded`, block resources
2. [Browser-Use Library](https://github.com/browser-use/browser-use) - 6x faster with optimized LLM gateway
3. [OpenAI Latency Optimization](https://platform.openai.com/docs/guides/latency-optimization) - Parallelize, combine steps
4. [17 Strategies to Fix Agent Latency](https://medium.com/google-cloud/the-art-of-fast-agents-14-strategies-to-fix-latency-07a1e1dfebf9) - Output limits, JSON schemas
5. [Playwright Evaluate Best Practices](https://www.browserstack.com/guide/playwright-evaluate) - Keep evaluate() lightweight
