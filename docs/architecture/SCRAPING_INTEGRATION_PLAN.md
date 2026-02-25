# Scrapling Integration Plan for Pythinker

> **Author:** Claude Code (Opus 4.6)
> **Date:** 2026-02-24
> **Status:** Proposal — Pending Review
> **Scope:** Backend integration of Scrapling library into Pythinker's agentic tool system
> **References:** [Scrapling GitHub](https://github.com/D4Vinci/Scrapling) · [Scrapling Docs](https://scrapling.readthedocs.io)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Analysis](#2-current-architecture-analysis)
3. [Library Comparison & Alternatives](#3-library-comparison--alternatives)
4. [Why Scrapling](#4-why-scrapling)
5. [Integration Architecture](#5-integration-architecture)
6. [Exact Integration Points in Agentic Flow](#6-exact-integration-points-in-agentic-flow)
7. [New Components (DDD-Compliant)](#7-new-components-ddd-compliant)
8. [Three-Tier Fetch Escalation Strategy](#8-three-tier-fetch-escalation-strategy)
9. [Configuration & Settings](#9-configuration--settings)
10. [Installation & Sandbox Considerations](#10-installation--sandbox-considerations)
11. [Maximizing Value from Scrapling](#11-maximizing-value-from-scrapling)
12. [Benefits to the Stack](#12-benefits-to-the-stack)
13. [Implementation Phases](#13-implementation-phases)
14. [Risk Assessment & Mitigations](#14-risk-assessment--mitigations)
15. [Testing Strategy](#15-testing-strategy)
16. [Open Questions](#16-open-questions)

---

## 1. Executive Summary

Pythinker's agent currently fetches web content through a two-layer system:

1. **`aiohttp` HTTP GET** — fast but naive (no TLS fingerprinting, regex HTML parser)
2. **Playwright via CDP** — full browser rendering (expensive, no stealth hardening)

**Problem:** Sites with anti-bot protection (Cloudflare, Turnstile, DataDome) block both layers.
The `aiohttp` layer exposes automation signatures (generic User-Agent, missing TLS fingerprints),
and vanilla Playwright leaks `navigator.webdriver=true` and other detectable signals.

**Solution:** Integrate [Scrapling](https://github.com/D4Vinci/Scrapling) (v0.4, 12.6k stars, BSD-3)
as a **three-tier fetch escalation system** that replaces `aiohttp` and enhances Playwright with
stealth capabilities — without disrupting the existing `browser-use` (`BrowserAgentTool`) or
`PlaywrightBrowser` (CDP connection pool) integrations.

**Key insight:** Scrapling doesn't replace Playwright or browser-use — it **fills the gap between them**.
It provides what Pythinker is missing: TLS fingerprint impersonation at the HTTP level, stealth-hardened
Playwright sessions, adaptive element tracking, proxy rotation, and a spider framework for research crawling.

---

## 2. Current Architecture Analysis

### 2.1 Existing Browser Stack

```
┌───────────────────────────────────────────────────────────────────┐
│                    CURRENT PYTHINKER BROWSER STACK                 │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Tool Layer (domain/services/tools/)                              │
│  ├── BrowserTool        — 13 agent-callable tools                 │
│  │   └── search()       — HTTP-first content fetch                │
│  ├── BrowserAgentTool   — Autonomous multi-step (browser-use)     │
│  ├── SearchTool         — API search + wide_research()            │
│  └── PlaywrightTool     — Sandbox-side script execution           │
│                                                                   │
│  Protocol Layer (domain/external/)                                │
│  └── Browser (Protocol) — 18 method interface                     │
│                                                                   │
│  Infrastructure Layer (infrastructure/external/browser/)           │
│  ├── PlaywrightBrowser  — CDP Playwright implementation           │
│  │   ├── Anti-detection: UA rotation (5 agents), timezone pool    │
│  │   ├── Circuit breaker: crash recovery, memory pressure         │
│  │   ├── Heavy page detection: DOM count, Wikipedia handler       │
│  │   └── Extraction cache: 15s TTL per-URL (configurable)         │
│  └── BrowserConnectionPool — Per-CDP-URL connection pooling       │
│      ├── Health checking: page.evaluate("() => true")             │
│      ├── Stale connection cleanup loop                            │
│      └── CDP sharing for browser-use                              │
│                                                                   │
│  Sandbox Layer (sandbox/)                                         │
│  ├── Chrome for Testing (v131, CDP port 9222)                     │
│  ├── CDP Screencast (live browser streaming)                      │
│  └── CDP Navigation (back/forward/reload)                         │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### 2.2 Current `BrowserTool.search()` Flow (The Primary Fetch Path)

**File:** `backend/app/domain/services/tools/browser.py:305-454`

```
Agent calls search(url, focus?)
    │
    ├── 1. TaskStateManager.record_url(url)
    ├── 2. URL visit counter (reject if 3+ visits)
    ├── 3. URL cache check (5min TTL, 50 entries)
    ├── 4. browser.cancel_background_browsing()
    ├── 5. asyncio.create_task(browser.navigate_for_display(url))  ← live preview
    │
    ├── 6. aiohttp.get(url)  ← WEAKNESS: no TLS fingerprinting
    │      │
    │      ├── html_to_text()  ← WEAKNESS: 57-line regex parser (fragile)
    │      │   • Strips <script>/<style>
    │      │   • Headings → Markdown #
    │      │   • Links → [text](url)
    │      │   • Lists → - items
    │      │   • Tables → pipe notation
    │      │   • Entity decoding (6 entities)
    │      │
    │      ├── PaywallDetector.detect(html, text, url)
    │      ├── _extract_focused_content(text, focus)
    │      └── Cache result → return ToolResult
    │
    └── 7. FALLBACK: browser_navigate(url)  ← WEAKNESS: no stealth mode
           └── PlaywrightBrowser.navigate()
               └── CDP Chromium (vanilla, detectable)
```

### 2.3 What `browser-use` Already Handles

**File:** `backend/app/domain/services/tools/browser_agent.py`

`BrowserAgentTool` wraps the `browser-use` library for **autonomous multi-step web tasks**.
It is fundamentally different from content fetching:

| Capability | BrowserAgentTool (browser-use) | BrowserTool.search() |
|---|---|---|
| **Purpose** | Multi-step autonomous browsing | Single-page content extraction |
| **Control** | LLM drives actions via natural language | Direct URL fetch |
| **Steps** | Up to 25 steps per task | 1 HTTP request + 1 fallback |
| **Session** | Shared CDP via connection pool | Shared CDP or aiohttp |
| **Stealth** | None (vanilla Playwright) | None (generic UA in aiohttp) |
| **Output** | Task completion result | Page text content |

**Critical observation:** Scrapling does NOT replace `browser-use`. They serve different purposes:
- `browser-use` = autonomous web agent (click, type, navigate multi-page flows)
- Scrapling = content fetching with stealth + structured extraction

They **complement** each other: Scrapling handles the 95% of cases where you need page content,
while browser-use handles the 5% requiring interactive multi-step automation.

### 2.4 What Playwright Already Handles

**File:** `backend/app/infrastructure/external/browser/playwright_browser.py`

`PlaywrightBrowser` is the **infrastructure implementation** of the `Browser` Protocol.
It connects to Chrome via CDP inside the sandbox and provides:

- Page navigation, DOM extraction, element interaction
- Anti-detection: UA rotation (5 agents), timezone pool (6 zones)
- Circuit breaker: crash recovery with 300s window, 3-crash threshold
- Memory pressure monitoring via `Performance.getMetrics`
- Heavy page detection and handling

**What Playwright is missing:**
- No TLS fingerprint impersonation (Chrome CDP reveals automation headers)
- No Cloudflare/Turnstile bypass capability
- No proxy rotation integration
- No adaptive element tracking (selectors break on site redesigns)
- No built-in stealth hardening (navigator.webdriver is exposed)

Scrapling's `StealthyFetcher` fills exactly these gaps by wrapping Playwright with stealth patches.

---

## 3. Library Comparison & Alternatives

### 3.1 Comprehensive Comparison Matrix

| Criterion | Scrapling | Crawl4AI | Crawlee (Apify) | browser-use | Playwright (raw) | Selenium |
|---|---|---|---|---|---|---|
| **GitHub Stars** | 12.6k | ~8k | ~6k | ~5k | 70k+ | 32k+ |
| **License** | BSD-3 | Apache-2 | Apache-2 | MIT | Apache-2 | Apache-2 |
| **Python** | ≥3.10 | ≥3.9 | ≥3.9 | ≥3.11 | ≥3.8 | ≥3.8 |
| **Anti-Bot Bypass** | ★★★★★ | ★★★★ | ★★★ | ★★★ | ★★ | ★★ |
| **TLS Fingerprinting** | ★★★★★ | ★ | ★ | ★ | ★ | ★ |
| **Stealth Mode** | StealthyFetcher | Undetected Browser | Via plugins | Cloud managed | Via plugins | UC mode |
| **HTTP-Only Fetcher** | ★★★★★ (curl_cffi) | ✗ (Playwright only) | BeautifulSoup crawler | ✗ | ✗ | ✗ |
| **Async Support** | Full (asyncio) | Full | Full (asyncio) | Yes | Yes | Limited |
| **Structured Extract** | CSS/XPath/Regex + Adaptor | Markdown/JSON export | BeautifulSoup/Parsel | NLP-based | Manual | Manual |
| **Adaptive Tracking** | ★★★★★ (similarity algo) | ✗ | ✗ | ✗ | ✗ | ✗ |
| **Proxy Rotation** | Built-in ProxyRotator | Via config | Built-in management | Cloud proxies | Manual | Manual |
| **Spider Framework** | Scrapy-like async Spider | ✗ | Crawler framework | ✗ | ✗ | ✗ |
| **Tab Pooling** | Built-in (max_pages) | Browser pools | Via pool config | ✗ | Manual | Manual |
| **MCP Server** | Built-in | ✗ | ✗ | ✗ | ✗ | ✗ |
| **Self-Hosted** | ★★★★★ (zero deps) | ★★★★ (Docker) | ★★★★ | ★★ (cloud) | ★★★★★ | ★★★★★ |
| **Resource Footprint** | Very Low (HTTP) / Med (browser) | Medium-High | Medium | High ($) | Medium | High |
| **Active Development** | v0.4 (2025) | Active | Active | Beta | Mature | Mature |

### 3.2 Alternative-Specific Analysis

#### Crawl4AI — Strong for LLM Content, Weak for General Scraping

**Pros:**
- Markdown/JSON output optimized for LLM consumption
- Undetected Browser mode for anti-bot bypass
- Self-hosting with Docker templates and memory thresholds
- LangChain integration examples exist

**Cons:**
- No lightweight HTTP fetcher — everything goes through Playwright (expensive)
- No TLS fingerprint impersonation at HTTP level
- No adaptive element tracking
- Heavier resource footprint (120-200MB per JS-heavy page)
- No Scrapy-like spider framework for batch crawling

**Verdict:** Good if the only need is "turn web pages into LLM-ready Markdown." But Pythinker
already converts HTML→text via `html_to_text()`, and the real need is stealth + efficiency.

#### Crawlee (Apify) — Best for Production Crawling, Overkill for Agent Browsing

**Pros:**
- `AutoscaledPool` with `ConcurrencySettings` (min/max/desired concurrency)
- Resource-aware scaling based on system metrics
- Proxy management with tiered fallbacks
- Both HTTP and browser crawlers

**Cons:**
- No built-in stealth mode (relies on Playwright plugins)
- No TLS fingerprint impersonation
- No adaptive element tracking
- Tied to Apify ecosystem (optional but encouraged)
- More suitable for batch crawling than interactive agent browsing

**Verdict:** Would be the pick if Pythinker's primary need was large-scale production crawling.
But the agent needs single-page stealth fetching first, with occasional research crawling.

#### browser-use — Already Integrated, Different Purpose

**Status:** Already in Pythinker as `BrowserAgentTool` (optional dependency).

**Pros:**
- Natural-language driven multi-step web automation
- LLM integration built-in (OpenAI, Google, Ollama)
- Managed cloud browser option

**Cons:**
- Not a content fetcher — it's an autonomous browser agent
- No TLS fingerprinting, no stealth mode at HTTP level
- Cloud dependency for managed features
- Beta status with limited anti-bot capability

**Verdict:** Stays as-is. Scrapling complements it, doesn't replace it.

#### Playwright (raw) — Already the Foundation

**Status:** Already in Pythinker as `PlaywrightBrowser` infrastructure.

Scrapling's `DynamicFetcher` and `StealthyFetcher` use Playwright internally.
The integration enhances Playwright with stealth capabilities rather than replacing it.

#### Selenium — Legacy, No Compelling Advantage

**Verdict:** Slower, more resource-intensive, weaker stealth than Playwright-based solutions.
No reason to introduce it when Playwright is already the foundation.

### 3.3 Final Recommendation

**Primary: Scrapling** — Best overall fit for Pythinker's architecture:
1. Three-tier fetching matches existing HTTP-first → browser-fallback pattern
2. Zero external service dependency (Self-Hosted First principle)
3. Lightweight HTTP tier avoids Playwright for 80% of fetches
4. Stealth hardening fills the anti-bot gap
5. Adaptive tracking is unique among all alternatives
6. Spider framework can optionally augment `wide_research()` with controlled concurrent crawling

**Secondary consideration: Crawl4AI** — If LLM-ready Markdown output becomes a priority,
Crawl4AI's extraction pipeline could be added alongside Scrapling for specific use cases.
However, this is not recommended for Phase 1.

---

## 4. Why Scrapling

### 4.1 Architectural Alignment

Pythinker already has a two-tier fetch strategy. Scrapling formalizes it into three tiers:

| Tier | Current (Pythinker) | Proposed (Scrapling) |
|---|---|---|
| **Tier 1: HTTP** | `aiohttp.get()` + regex `html_to_text()` | `Fetcher` with curl_cffi TLS fingerprinting + `Adaptor` CSS/XPath parser |
| **Tier 2: Browser** | `PlaywrightBrowser.navigate()` via CDP | `DynamicFetcher` (Playwright with JS rendering) |
| **Tier 3: Stealth** | ✗ (doesn't exist) | `StealthyFetcher` (hardened Playwright, Cloudflare bypass) |

### 4.2 Scrapling's Three Fetcher Tiers

```python
from scrapling.fetchers import Fetcher, StealthyFetcher, DynamicFetcher

# Tier 1: HTTP — Fast, lightweight, TLS-impersonated
page = Fetcher.get("https://example.com", impersonate="chrome")
# Uses curl_cffi for realistic TLS fingerprint, HTTP/3 support
# ~50ms, near-zero CPU/memory

# Tier 2: Dynamic — Full browser with JS rendering
page = DynamicFetcher.fetch("https://spa-site.com", headless=True)
# Playwright Chromium, client-side JS execution
# ~2s, moderate resources

# Tier 3: Stealthy — Anti-bot bypass
page = StealthyFetcher.fetch("https://protected-site.com", headless=True, network_idle=True)
# Hardened Playwright, Cloudflare/Turnstile bypass
# ~5s, stealth patches applied
```

### 4.3 Unique Capabilities Not Available in Alternatives

**Adaptive Element Tracking:**
```python
# First scrape: save element fingerprints
products = page.css('.product-card', auto_save=True)

# Later, after site redesign where class names changed:
products = page.css('.product-card', adaptive=True)
# Scrapling uses similarity algorithms to relocate the elements
```

**Async Sessions with Tab Pooling:**
```python
async with AsyncStealthySession(max_pages=3) as session:
    # Rotates across 3 browser tabs in a single Playwright instance
    tasks = [session.fetch(url) for url in urls]
    results = await asyncio.gather(*tasks)
    print(session.get_pool_stats())  # {"busy": 2, "free": 1, "error": 0}
```

**Spider Framework with Streaming:**
```python
class ResearchSpider(Spider):
    name = "research"
    start_urls = ["https://example.com"]

    def configure_sessions(self, manager):
        manager.add("fast", FetcherSession(impersonate="chrome"))
        manager.add("stealth", AsyncStealthySession(headless=True, lazy=True))

    async def parse(self, response):
        for link in response.css('a::attr(href)').getall():
            if "protected" in link:
                yield Request(link, sid="stealth")  # Route through stealth
            else:
                yield Request(link, sid="fast")  # Route through HTTP

# Stream results as they arrive
async for item in spider.stream():
    # Feed to LLM incrementally
    await process_item(item)
```

---

## 5. Integration Architecture

### 5.1 High-Level Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                     PROPOSED PYTHINKER BROWSER + SCRAPING STACK        │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  Agent (base.py) → tool dispatch via invoke_function()                 │
│                                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │  SearchTool   │  │ BrowserTool  │  │ ScrapingTool │  │BrowserAgt │  │
│  │  (search.py)  │  │ (browser.py) │  │   (NEW)      │  │   Tool    │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘  │
│         │                 │                  │                │         │
│  ═══════╪═════════════════╪══════════════════╪════════════════╪═══════  │
│         │                 │                  │                │         │
│         │          ┌──────┴───────┐   ┌──────┴───────┐       │         │
│         │          │ Scraper      │   │ Scraper      │       │         │
│         │          │ Protocol     │   │ Protocol     │       │         │
│         │          │ (domain)     │   │ (domain)     │       │         │
│         │          └──────┬───────┘   └──────┬───────┘       │         │
│         │                 │                  │                │         │
│  ═══════╪═════════════════╪══════════════════╪════════════════╪═══════  │
│         │                 │                  │                │         │
│         │          ┌──────┴──────────────────┴───────┐       │         │
│         │          │    ScraplingAdapter (infra)      │       │         │
│         │          │    ├── Tier 1: Fetcher (HTTP)    │       │         │
│         │          │    ├── Tier 2: DynamicFetcher    │       │         │
│         │          │    └── Tier 3: StealthyFetcher   │       │         │
│         │          └──────┬──────────────────────────┘       │         │
│         │                 │                                   │         │
│  ┌──────┴─────┐   ┌──────┴───────┐                    ┌──────┴──────┐  │
│  │  Search    │   │  Existing    │                    │  browser-   │  │
│  │  Engine    │   │  Playwright  │                    │  use Agent  │  │
│  │  APIs      │   │  Browser     │                    │  (CDP)      │  │
│  │  (Serper/  │   │  (CDP Pool)  │                    │             │  │
│  │  Tavily/   │   │              │                    │             │  │
│  │  DuckDuck) │   │              │                    │             │  │
│  └────────────┘   └──────┬───────┘                    └──────┬──────┘  │
│                          │                                   │         │
│  ════════════════════════╪═══════════════════════════════════╪═══════  │
│                          │                                   │         │
│                   ┌──────┴───────────────────────────────────┴──────┐  │
│                   │        Docker Sandbox Container                  │  │
│                   │        Chrome/Chromium · CDP:9222                │  │
│                   │        CDP Screencast · Live Preview             │  │
│                   └─────────────────────────────────────────────────┘  │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Coexistence with Existing Components

| Component | Status | Interaction with Scrapling |
|---|---|---|
| `PlaywrightBrowser` | **Unchanged** | Scrapling's `StealthyFetcher` uses its own Playwright instance; does NOT share CDP connection pool. `PlaywrightBrowser` remains the primary CDP interface for live preview, DOM extraction, and element interaction. |
| `BrowserConnectionPool` | **Unchanged** | No integration needed. Scrapling manages its own browser sessions via tab pooling (`max_pages`). |
| `BrowserAgentTool` (browser-use) | **Unchanged** | Continues to use shared CDP for autonomous multi-step tasks. Scrapling handles content fetching only. |
| `BrowserTool.search()` | **Modified** | Replaces `aiohttp.get()` + `html_to_text()` with `ScraplingAdapter` Tier 1 fetch. Fallback escalates through Tier 2 and Tier 3 before falling back to existing `browser_navigate()`. |
| `SearchTool.wide_research()` | **Enhanced** (Phase 4) | Optionally uses Scrapling Spider for concurrent research crawling with per-domain throttling and streaming. |
| `PlaywrightTool` | **Unchanged** | Sandbox-side script execution remains independent. |
| CDP Screencast | **Unchanged** | Live preview continues via existing CDP screencast. Scrapling's `navigate_for_display()` background task remains in `BrowserTool.search()`. |

---

## 6. Exact Integration Points in Agentic Flow

### 6.1 Tool Registration — Flow/Factory Construction Sites

**Files:**
- `backend/app/domain/services/flows/plan_act.py` — primary PlanAct flow (add `ScrapingTool` here)
- `backend/app/domain/services/flows/plan_act_graph.py` — graph-based flow variant
- `backend/app/domain/services/flows/tree_of_thoughts_flow.py` — ToT flow variant
- `backend/app/domain/services/orchestration/agent_factory.py` — **SwarmAgent** factory only (multi-agent orchestration subsystem; independent decision whether to expose `ScrapingTool` to swarm agents)

```python
# CURRENT (line 300-323):
tools = [
    ShellTool(sandbox),
    BrowserTool(browser),                        # ← Enhanced internally with Scrapling
    FileTool(sandbox, session_id=session_id),
    CodeExecutorTool(sandbox=sandbox, session_id=session_id),
    ChartTool(sandbox=sandbox, session_id=session_id),
    MessageTool(),
    IdleTool(),
    mcp_tool,
]

if search_engine:
    self._search_tool = SearchTool(search_engine, browser=browser)
    tools.append(self._search_tool)              # ← Enhanced in Phase 4

if cdp_url and browser_agent_enabled and BROWSER_USE_AVAILABLE and BrowserAgentTool:
    tools.append(BrowserAgentTool(cdp_url))      # ← Unchanged

# PROPOSED ADDITION (Phase 3):
# Inject Scraper from composition root; domain tools import only Scraper Protocol.
if settings.scraping_tool_enabled:
    scraper = scraper_provider()  # Infrastructure-bound factory in outer layer
    tools.append(ScrapingTool(scraper=scraper))   # ← NEW: structured extraction
```

### 6.2 `BrowserTool.search()` — The Primary Fetch Path (Phase 1-2)

**File:** `backend/app/domain/services/tools/browser.py:305-454`

**Current flow (lines 378-442):**
```python
# Line 379: aiohttp HTTP GET
session = await get_http_session()
async with session.get(url, allow_redirects=True) as response:
    # Line 384-385: regex HTML parser
    html = await response.text()
    text = html_to_text(html)
```

**Proposed flow (Phase 1):**
```python
# Replace aiohttp with Scrapling Fetcher
scraper = get_scraping_adapter()
result = await scraper.fetch(url)  # Tier 1: curl_cffi with TLS impersonation

if result.success:
    text = result.text  # Already parsed by Scrapling's Adaptor
    html = result.html  # Raw HTML for paywall detection
    # ... rest of existing logic (paywall detection, focus extraction, caching)
```

**Proposed flow (Phase 2 — escalation):**
```python
# Three-tier escalation
scraper = get_scraping_adapter()
result = await scraper.fetch_with_escalation(url)
# Internally:
#   Tier 1: AsyncFetcher.get(url, impersonate="chrome")      → if blocked...
#   Tier 2: DynamicFetcher.async_fetch(url, headless=True)   → if still blocked...
#   Tier 3: StealthyFetcher.async_fetch(url, headless=True, network_idle=True)
# Only after all 3 tiers fail: fall back to existing browser_navigate()
```

**What stays the same:**
- `navigate_for_display()` background task for live preview (line 376)
- URL visit counting and rejection (lines 329-344)
- URL cache check and population (lines 347-419)
- PaywallDetector integration (lines 388-405)
- `_extract_focused_content()` (line 409)
- Fallback to `browser_navigate()` (lines 452-454)

### 6.3 `SearchTool.wide_research()` — Research Crawling (Phase 4)

**File:** `backend/app/domain/services/tools/search.py`

**Current:** Uses `asyncio.Semaphore(5)` + manual URL dedup to run search variants concurrently.
Content fetching of individual results happens via `BrowserTool.search()` one URL at a time.

**Enhanced with optional Scrapling Spider stage (additive, not replacement):**
```python
# In SearchTool or a new ResearchCrawlTool:
async def _crawl_research_urls(self, urls: list[str]) -> list[dict]:
    """Crawl multiple URLs concurrently using Scrapling Spider."""
    spider = ResearchSpider(start_urls=urls)
    results = []
    async for item in spider.stream():
        results.append(item)
        if len(results) >= 20:  # Cap results
            break
    return results
```

**Benefits over current implementation (when enabled):**
- Built-in per-domain throttling (replaces manual semaphore)
- Automatic blocked request detection and retry
- Multi-session routing: fast HTTP for static, stealth for protected
- Pause/resume with checkpoints for long research tasks
- Streaming results to LLM as they arrive (vs waiting for all)

### 6.4 `BaseAgent` Tool Dispatch — No Changes Required

**File:** `backend/app/domain/services/agents/base.py`

The agent tool dispatch system (`get_tool()`, `invoke_function()`, `get_tools()`) is
generic and works via the `@tool` decorator. Scrapling integration is entirely internal
to `BrowserTool` and `ScrapingTool` — the agent sees the same tool interface.

### 6.5 `DynamicToolsetManager` — No Changes Required

The `DynamicToolsetManager` filters tools by semantic relevance. New `ScrapingTool` tools
will be automatically included/excluded based on task context. No changes needed.

---

## 7. New Components (DDD-Compliant)

### 7.1 File Structure

```
backend/app/
├── domain/
│   ├── external/
│   │   └── scraper.py                          # NEW: Scraper Protocol (interface)
│   └── services/
│       └── tools/
│           ├── browser.py                      # MODIFIED: Phase 1-2
│           ├── search.py                       # MODIFIED: Phase 4
│           └── scraping.py                     # NEW: Phase 3 — ScrapingTool
│
├── infrastructure/
│   └── external/
│       └── scraper/
│           ├── __init__.py                     # NEW
│           ├── scrapling_adapter.py            # NEW: Scrapling implementation
│           └── escalation.py                   # NEW: Three-tier escalation logic
│
├── core/
│   └── config_scraping.py                      # NEW: ScrapingSettingsMixin
│
└── tests/
    ├── domain/services/tools/
    │   └── test_scraping_tool.py               # NEW
    └── infrastructure/external/scraper/
        ├── test_scrapling_adapter.py           # NEW
        └── test_escalation.py                  # NEW
```

### 7.2 Scraper Protocol (Domain Layer)

**File:** `backend/app/domain/external/scraper.py`

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ScrapedContent:
    """Result of a scraping operation."""
    success: bool
    url: str
    text: str                          # Cleaned text content
    html: str | None = None            # Raw HTML (for paywall detection)
    title: str | None = None
    status_code: int | None = None
    tier_used: str | None = None       # "http", "dynamic", "stealthy"
    error: str | None = None
    metadata: dict | None = None       # Extra data (links, images, etc.)


@dataclass
class StructuredData:
    """Result of structured extraction."""
    success: bool
    url: str
    data: dict                         # Extracted structured data
    selectors_used: dict | None = None
    error: str | None = None


class Scraper(Protocol):
    """Scraper service gateway interface.

    Defines the contract for web scraping implementations.
    Supports tiered fetching, structured extraction, and escalation.
    """

    async def fetch(self, url: str, **kwargs) -> ScrapedContent:
        """Fetch page content using the most appropriate tier."""
        ...

    async def fetch_with_escalation(self, url: str, **kwargs) -> ScrapedContent:
        """Fetch with automatic tier escalation on failure."""
        ...

    async def extract_structured(
        self, url: str, selectors: dict[str, str], **kwargs
    ) -> StructuredData:
        """Extract structured data using CSS/XPath selectors."""
        ...

    async def fetch_batch(
        self, urls: list[str], concurrency: int = 5, **kwargs
    ) -> list[ScrapedContent]:
        """Fetch multiple URLs concurrently."""
        ...
```

**Design rationale:** The `Scraper` Protocol follows the exact same pattern as the existing
`Browser` Protocol (`domain/external/browser.py`). The domain layer depends only on this
abstraction — it never imports Scrapling directly.

### 7.3 ScraplingAdapter (Infrastructure Layer)

**File:** `backend/app/infrastructure/external/scraper/scrapling_adapter.py`

This is the primary backend adapter file that imports `scrapling` for Tier 1-3 fetch operations.
If the library is swapped, changes should remain localized to infrastructure adapter modules.

```python
from scrapling.fetchers import AsyncFetcher, StealthyFetcher, DynamicFetcher

class ScraplingAdapter:
    """Scrapling implementation of the Scraper Protocol."""

    def __init__(self, settings: ScrapingSettings):
        self._settings = settings
        self._proxy_rotator = None
        if settings.proxy_list:
            from scrapling import ProxyRotator
            self._proxy_rotator = ProxyRotator(
                proxies=settings.proxy_list,
                strategy=settings.proxy_strategy,
            )

    async def fetch(self, url: str, **kwargs) -> ScrapedContent:
        """Tier 1 fetch: HTTP with TLS impersonation."""
        try:
            page = await AsyncFetcher.get(
                url,
                impersonate=self._settings.default_impersonate,
                proxy=self._proxy_rotator.next() if self._proxy_rotator else None,
                timeout=self._settings.http_timeout,
            )
            return ScrapedContent(
                success=True,
                url=url,
                text=page.get_all_text(separator="\n\n"),
                html=page.html,
                title=page.css("title::text").get(),
                status_code=page.status,
                tier_used="http",
            )
        except Exception as e:
            return ScrapedContent(
                success=False, url=url, text="", error=str(e), tier_used="http"
            )

    async def fetch_with_escalation(self, url: str, **kwargs) -> ScrapedContent:
        """Three-tier escalation: HTTP → Dynamic → Stealthy."""
        # Tier 1: HTTP
        result = await self.fetch(url, **kwargs)
        if result.success and len(result.text) > 500:
            return result

        # Tier 2: Dynamic (Playwright with JS)
        if self._settings.escalation_enabled:
            result = await self._fetch_dynamic(url, **kwargs)
            if result.success and len(result.text) > 500:
                return result

        # Tier 3: Stealthy (anti-bot bypass)
        if self._settings.stealth_enabled:
            result = await self._fetch_stealthy(url, **kwargs)
            if result.success:
                return result

        return result  # Return last attempt's result (with error info)
```

### 7.4 ScrapingTool (Domain Tool Layer — Phase 3)

**File:** `backend/app/domain/services/tools/scraping.py`

```python
class ScrapingTool(BaseTool):
    """Structured web scraping tool for the agent."""

    name: str = "scraping"

    def __init__(self, scraper: Scraper, max_observe: int | None = None):
        super().__init__(max_observe=max_observe)
        self.scraper = scraper

    @tool(
        name="scrape_structured",
        description="Extract structured data from a webpage using CSS selectors.",
        parameters={
            "url": {"type": "string", "description": "URL to scrape"},
            "selectors": {
                "type": "object",
                "description": "Map of field names to CSS selectors",
            },
        },
        required=["url", "selectors"],
    )
    async def scrape_structured(self, url: str, selectors: dict) -> ToolResult:
        result = await self.scraper.extract_structured(url, selectors)
        if result.success:
            return ToolResult(success=True, data=result.data, message=f"Extracted {len(result.data)} fields")
        return ToolResult(success=False, message=result.error)

    @tool(
        name="scrape_batch",
        description="Fetch content from multiple URLs concurrently.",
        parameters={
            "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to fetch"},
            "focus": {"type": "string", "description": "Optional focus area for content extraction"},
        },
        required=["urls"],
    )
    async def scrape_batch(self, urls: list[str], focus: str | None = None) -> ToolResult:
        results = await self.scraper.fetch_batch(urls, concurrency=5)
        # ... format and return aggregated results
```

### 7.5 Configuration Mixin

**File:** `backend/app/core/config_scraping.py`

```python
class ScrapingSettingsMixin:
    """Scrapling integration configuration."""

    # Feature flag
    scraping_tool_enabled: bool = False           # Enable ScrapingTool in agent toolset
    scraping_enhanced_fetch: bool = True           # Use Scrapling in BrowserTool.search()

    # Tier escalation
    scraping_escalation_enabled: bool = True       # Auto-escalate HTTP → Dynamic → Stealthy
    scraping_stealth_enabled: bool = True           # Enable StealthyFetcher tier

    # HTTP Fetcher (Tier 1)
    scraping_default_impersonate: str = "chrome"   # Browser to impersonate (chrome/firefox/edge)
    scraping_http_timeout: int = 15                 # HTTP fetch timeout (seconds)

    # Browser Fetcher (Tier 2-3)
    scraping_max_browser_tabs: int = 3              # Tab pool size for browser sessions
    scraping_headless: bool = True                  # Run browsers headless

    # Proxy rotation
    scraping_proxy_enabled: bool = False
    scraping_proxy_list: str = ""                   # Comma-separated proxy URLs
    scraping_proxy_strategy: str = "cyclic"         # cyclic or custom

    # Adaptive tracking
    scraping_adaptive_tracking: bool = False         # Store element fingerprints

    # Content thresholds
    scraping_min_content_length: int = 500           # Minimum text length to accept
    scraping_max_content_length: int = 100000        # Maximum text length to return
```

---

## 8. Three-Tier Fetch Escalation Strategy

### 8.1 Decision Flow

```
                         URL Request
                             │
                             ▼
                    ┌────────────────┐
                    │   URL Cache?   │──── HIT ────→ Return cached content
                    └───────┬────────┘
                            │ MISS
                            ▼
               ┌─────────────────────────┐
               │ TIER 1: Scrapling       │   ~50ms │ ~0 MB RAM
               │ Fetcher (HTTP)          │
               │ ─────────────────────── │
               │ • curl_cffi HTTP client │
               │ • TLS fingerprint:      │
               │   Chrome/Firefox/Edge   │
               │ • HTTP/3 support        │
               │ • Adaptor CSS/XPath     │
               │   parsing               │
               └────────┬────────────────┘
                        │
                  ┌─────┴─────┐
                  │ Success?  │──── YES (text > 500 chars) ────→ Return content
                  └─────┬─────┘
                        │ NO (blocked / JS-required / empty)
                        ▼
               ┌─────────────────────────┐
               │ TIER 2: Scrapling       │   ~2s │ ~150 MB RAM
               │ DynamicFetcher          │
               │ ─────────────────────── │
               │ • Playwright Chromium   │
               │ • Full JS execution     │
               │ • SPA rendering         │
               │ • network_idle wait     │
               └────────┬────────────────┘
                        │
                  ┌─────┴─────┐
                  │ Success?  │──── YES ────→ Return content
                  └─────┬─────┘
                        │ NO (anti-bot block / Cloudflare)
                        ▼
               ┌─────────────────────────┐
               │ TIER 3: Scrapling       │   ~5s │ ~200 MB RAM
               │ StealthyFetcher         │
               │ ─────────────────────── │
               │ • Hardened Playwright   │
               │ • Cloudflare bypass     │
               │ • Turnstile handling    │
               │ • Stealth patches       │
               │ • navigator.webdriver   │
               │   removed               │
               └────────┬────────────────┘
                        │
                  ┌─────┴─────┐
                  │ Success?  │──── YES ────→ Return content
                  └─────┬─────┘
                        │ NO (all tiers failed)
                        ▼
               ┌─────────────────────────┐
               │ FALLBACK: Existing      │
               │ PlaywrightBrowser       │
               │ via browser_navigate()  │
               │ ─────────────────────── │
               │ • CDP connection pool   │
               │ • Live preview display  │
               │ • DOM extraction        │
               └─────────────────────────┘
```

### 8.2 Escalation Triggers

| Trigger | Tier 1 → 2 | Tier 2 → 3 | Tier 3 → Fallback |
|---|---|---|---|
| HTTP 403 Forbidden | Yes | — | — |
| HTTP 429 Rate Limited | Yes (after retry) | — | — |
| Empty/short content (<500 chars) | Yes | Yes | Yes |
| JavaScript-required page | Yes | — | — |
| Cloudflare challenge detected | — | Yes | — |
| CAPTCHA in response | — | Yes | — |
| Timeout exceeded | — | — | Yes |
| Connection refused | — | — | Yes |

### 8.3 Resource Impact Per Tier

| Tier | Target Latency (initial hypothesis) | Memory (per request, to benchmark) | CPU | Suggested Concurrency Guardrail | Cost |
|---|---|---|---|---|---|
| Tier 1: HTTP Fetcher | p95 < 300ms | low | Low | Start at 50, tune with load test | Free |
| Tier 2: DynamicFetcher | p95 < 4s | medium | Moderate | Start at 3 per worker | Free |
| Tier 3: StealthyFetcher | p95 < 8s | medium-high | Moderate-High | Start at 2 per worker | Free |
| Fallback: PlaywrightBrowser | p95 < 6s | shared (CDP pool) | Moderate | Existing shared-page limits | Free |

**Rollout note:** Tier distribution should be measured in production-like load tests and exported
as metrics before setting hard expectations.

---

## 9. Configuration & Settings

### 9.1 `.env` Additions

```bash
# ─── Scrapling Integration ─────────────────────────────────────
# Feature flags
SCRAPING_TOOL_ENABLED=false                # Enable dedicated ScrapingTool (Phase 3)
SCRAPING_ENHANCED_FETCH=true               # Use Scrapling in BrowserTool.search() (Phase 1)

# Tier escalation
SCRAPING_ESCALATION_ENABLED=true           # Auto-escalate through tiers
SCRAPING_STEALTH_ENABLED=true              # Enable StealthyFetcher (Tier 3)

# HTTP Fetcher (Tier 1)
SCRAPING_DEFAULT_IMPERSONATE=chrome        # TLS fingerprint: chrome, firefox, edge
SCRAPING_HTTP_TIMEOUT=15                   # HTTP timeout in seconds

# Browser Fetcher (Tier 2-3)
SCRAPING_MAX_BROWSER_TABS=3                # Browser tab pool size
SCRAPING_HEADLESS=true                     # Run browsers headless

# Proxy rotation (optional)
SCRAPING_PROXY_ENABLED=false
SCRAPING_PROXY_LIST=                       # Comma-separated: http://proxy1:8080,http://proxy2:8080
SCRAPING_PROXY_STRATEGY=cyclic             # cyclic or custom

# Adaptive element tracking (Phase 5)
SCRAPING_ADAPTIVE_TRACKING=false           # Store element fingerprints in memory/Qdrant

# Content thresholds
SCRAPING_MIN_CONTENT_LENGTH=500            # Minimum text to accept before escalating
SCRAPING_MAX_CONTENT_LENGTH=100000         # Maximum text to return
```

### 9.2 Settings Mixin Integration

**File:** `backend/app/core/config.py` — Add `ScrapingSettingsMixin` to `Settings` class:

```python
from app.core.config_scraping import ScrapingSettingsMixin

class Settings(
    # ... existing mixins ...
    ScrapingSettingsMixin,       # NEW
    BaseSettings,
):
    ...
```

---

## 10. Installation & Sandbox Considerations

### 10.1 Backend Dependencies

**File:** `backend/requirements.txt` (primary runtime dependency file in this repo)

```
# Scrapling core (Fetcher + Adaptor parser)
scrapling>=0.4

# Optional: Browser fetchers (DynamicFetcher, StealthyFetcher)
# Only needed if Tier 2-3 escalation runs from backend (vs sandbox)
# scrapling[fetchers]>=0.4
```

**Minimal install (recommended for Phase 1):**
```bash
pip install scrapling  # Core HTTP fetcher only (~10MB, no Playwright)
```

**Full install (Phase 2+):**
```bash
pip install "scrapling[fetchers]"  # + Playwright browser fetchers
```

### 10.2 Sandbox Considerations

The Docker sandbox already has Chrome for Testing + Playwright installed.
Two deployment strategies:

**Strategy A: Backend-Only (Recommended for Phase 1-2)**
- Install `scrapling` in the backend Python environment
- Tier 1 (HTTP) runs from the backend (no sandbox needed)
- Tier 2-3 (browser) run from the backend using Scrapling's own Playwright instance
- CDP live preview continues via existing `navigate_for_display()` background task

**Pros:** No sandbox changes required. Scrapling manages its own browser.
**Cons:** Tier 2-3 browsers run outside sandbox isolation.

**Strategy B: Hybrid (Recommended for Phase 3+)**
- Tier 1 (HTTP) runs from the backend
- Tier 2-3 (browser) run inside the sandbox via Scrapling installed in sandbox

Requires adding to `sandbox/requirements.runtime.txt`:
```
scrapling[fetchers]==0.4
```

And a new sandbox API endpoint for browser-tier fetching:
```python
# sandbox/app/api/v1/scraping.py
from fastapi import APIRouter

router = APIRouter()

@router.post("/scraping/stealthy")
async def scrape_stealthy(url: str, headless: bool = True):
    page = await StealthyFetcher.async_fetch(url, headless=headless, network_idle=True)
    return {"text": page.get_all_text(), "html": page.html, "status": page.status}
```

Then include this router from `sandbox/app/api/router.py`, so the final path is
`/api/v1/scraping/stealthy` behind existing `/api/*` auth middleware.

### 10.3 Playwright Coexistence

Scrapling's `DynamicFetcher`/`StealthyFetcher` launch their **own** Playwright browser instance.
They do NOT use the existing CDP connection pool (`BrowserConnectionPool`).

This means:
- No conflict with existing `PlaywrightBrowser` CDP sessions
- No conflict with `browser-use` CDP sharing
- Additional memory usage when Tier 2-3 are active (~150-200MB per session)
- On the 4GB VRAM RTX 3050 Ti system, monitor total memory when multiple browser sessions are active

**Resource management:** Scrapling sessions should be created on-demand and cleaned up
immediately after use. Do NOT keep persistent Scrapling browser sessions.

---

## 11. Maximizing Value from Scrapling

### 11.1 Strategy A: Three-Tier Escalation (Phase 1-2, Highest Value)

The single most impactful integration. Treat numbers below as **validation targets**, not guaranteed outcomes.

With Scrapling tiering enabled:
- Most URLs should resolve at Tier 1 without spawning browser fetchers
- JS-heavy URLs should escalate to Tier 2 when content thresholds fail
- Anti-bot URLs should escalate to Tier 3 when challenge signals are detected
- Existing `browser_navigate()` remains final safety fallback

**Benchmark gate before rollout:** run A/B load tests on a representative URL corpus and only
enable by default after meeting target SLOs (blocked-rate reduction, p95 latency, memory ceiling).

### 11.2 Strategy B: Replace `html_to_text()` with Scrapling Adaptor (Phase 1)

The current `html_to_text()` function (`browser.py:129-185`) is a 57-line regex parser that:
- Handles only 6 HTML entities (`&nbsp;`, `&amp;`, `&lt;`, `&gt;`, `&quot;`, `&#39;`)
- Uses regex to strip scripts/styles (can fail on malformed HTML)
- Converts headings, links, lists, tables to pseudo-Markdown

Scrapling's `Adaptor` class provides:
- Full CSS selector support (`.class`, `#id`, `tag`, attribute selectors)
- XPath selector support
- Text extraction with `get_all_text()`, `css(...).get()`, `.text` properties
- Proper HTML entity handling
- Regex-based text search within elements
- Auto selector generation for robustness

**Estimated impact:** Eliminates ~57 lines of fragile regex code. Better parsing of
malformed HTML. Enables structured extraction for Phase 3.

### 11.3 Strategy C: Proxy Rotation for Anti-Bot (Optional)

Scrapling's `ProxyRotator` integrates with Pythinker's existing `APIKeyPool` pattern:

```python
# Dual rotation: API keys + proxies
from scrapling import ProxyRotator

rotator = ProxyRotator(
    proxies=["http://proxy1:8080", "http://proxy2:8080", "socks5://proxy3:1080"],
    strategy="cyclic",
)

# Both rotate independently:
# - APIKeyPool rotates search engine API keys on 429s
# - ProxyRotator rotates exit IPs on blocks
```

### 11.4 Strategy D: Adaptive Element Tracking + Memory (Phase 5)

Store element fingerprints in Pythinker's Qdrant vector store:

```python
# First visit: save fingerprints
page = await scraper.fetch("https://example.com/products")
products = page.css('.product-card', auto_save=True)

# Store fingerprints in Qdrant (user_knowledge collection)
await memory_service.store_memory(
    user_id=user_id,
    content=f"Element fingerprints for {url}: {products.get_fingerprints()}",
    memory_type=MemoryType.TOOL_ARTIFACT,
    metadata={"url": url, "selectors": [".product-card"]},
)

# Later session: adaptive retrieval
fingerprints = await memory_service.search_similar(user_id, query=f"selectors for {url}")
products = page.css('.product-card', adaptive=True)  # Uses similarity matching
```

### 11.5 Strategy E: Spider-Based Research (Phase 4)

For `wide_research()`, add an optional Spider-backed crawling stage after search result collection
(do not replace existing search orchestration initially):

**Current limitations of `wide_research()`:**
- Manual `asyncio.Semaphore(5)` for concurrency limiting
- No per-domain throttling (can hammer a single domain)
- No pause/resume for long research sessions
- No automatic blocked request detection
- Results returned only after all fetches complete

**Scrapling Spider solves all of these:**
- Built-in per-domain throttling with configurable delays
- Pause/resume with file-based checkpoints
- Blocked request detection with customizable retry logic
- `async for item in spider.stream()` for incremental results
- Multi-session routing (HTTP for static, stealth for protected)

---

## 12. Benefits to the Stack

### 12.1 Quantitative Benefits

| Metric | Baseline (measure first) | Target after rollout | Validation method |
|---|---|---|---|
| Blocked request rate | Current baseline from logs | >=30% relative reduction | URL corpus replay + per-tier counters |
| p95 fetch latency | Current p95 by domain class | >=20% relative reduction | A/B benchmark on same URL set |
| HTML extraction quality | Current parser output quality | Fewer truncation/garbling defects | Golden-page regression fixtures |
| TLS fingerprint realism | Generic HTTP client headers/TLS | Browser impersonation where configured | Controlled anti-bot test endpoints |
| Anti-bot pass-through | Current fallback-only behavior | Higher success after tier escalation | Tiered retry telemetry |
| Concurrent fetch capacity | Current safe concurrency | Higher safe throughput at same error budget | Load test with error-budget guardrails |
| Lines of brittle parsing code | Current `html_to_text` footprint | Reduced custom parsing maintenance | Code diff + fallback retained |
| External service dependency | None | None | Dependency audit |

### 12.2 Qualitative Benefits

1. **Agent effectiveness improves** — Fewer "unable to access this page" failures means
   the agent can complete more tasks without human intervention.

2. **Research quality can improve** — optional Spider stage for top-K URLs adds
   per-domain throttling and incremental crawl results without changing search-provider behavior.

3. **Maintenance burden decreases** — Replacing `html_to_text()` regex with Scrapling's
   battle-tested parser eliminates a fragile code path.

4. **Future capabilities unlocked** — Adaptive element tracking, structured extraction,
   and tab pooling open new tool capabilities for the agent.

5. **Self-Hosted First preserved** — Zero external service dependencies.

6. **Resource efficiency target** — maximize Tier 1 resolution rate to minimize browser-tier
   usage; validate memory/latency ceilings before enabling aggressive concurrency.

---

## 13. Implementation Phases

### Phase 1: HTTP Tier Enhancement (2-3 days)

**Goal:** Replace `aiohttp` + `html_to_text()` with Scrapling `Fetcher` in `BrowserTool.search()`

**Files to modify:**
- `backend/app/domain/services/tools/browser.py` — Replace lines 378-385 (aiohttp GET + regex parse)
- `backend/app/core/config_scraping.py` — NEW: ScrapingSettingsMixin
- `backend/app/core/config.py` — Add ScrapingSettingsMixin to Settings

**Files to create:**
- `backend/app/domain/external/scraper.py` — Scraper Protocol
- `backend/app/infrastructure/external/scraper/__init__.py`
- `backend/app/infrastructure/external/scraper/scrapling_adapter.py` — Tier 1 only
- `backend/tests/infrastructure/external/scraper/test_scrapling_adapter.py`

**Dependencies:**
```bash
pip install scrapling  # Core only, ~10MB
```

**What stays unchanged:**
- `PlaywrightBrowser`, `BrowserConnectionPool`, `BrowserAgentTool`
- `navigate_for_display()` live preview
- `PaywallDetector` (receives HTML from Scrapling instead of aiohttp)
- `_extract_focused_content()` (receives text from Scrapling Adaptor)
- URL caching, visit counting, fallback to `browser_navigate()`

**Acceptance criteria:**
- `BrowserTool.search()` uses Scrapling `Fetcher` for HTTP requests
- TLS fingerprint impersonation active (configurable via `SCRAPING_DEFAULT_IMPERSONATE`)
- `html_to_text()` function still exists but is only used as fallback
- All existing tests pass
- New tests for `ScraplingAdapter.fetch()`

---

### Phase 2: Three-Tier Escalation (2-3 days)

**Goal:** Add automatic tier escalation: HTTP → Dynamic → Stealthy

**Files to modify:**
- `backend/app/infrastructure/external/scraper/scrapling_adapter.py` — Add Tier 2-3

**Files to create:**
- `backend/app/infrastructure/external/scraper/escalation.py` — Escalation logic
- `backend/tests/infrastructure/external/scraper/test_escalation.py`

**Dependencies:**
```bash
pip install "scrapling[fetchers]"  # Adds Playwright-based fetchers
```

**Key design decisions:**
- Scrapling's browser fetchers launch their **own** Playwright instance
- They do NOT share the existing CDP connection pool
- Sessions are created on-demand, cleaned up after use
- `navigate_for_display()` still runs for live preview (unchanged)
- Memory monitoring needed when Tier 2-3 active alongside CDP browser

**Acceptance criteria:**
- Automatic escalation on HTTP blocks (403, empty content, JS-required)
- Cloudflare/Turnstile-protected pages resolve at Tier 3
- Graceful degradation: if Scrapling browser fails, falls back to existing `browser_navigate()`
- Prometheus metrics for tier usage: `pythinker_scraping_tier_total{tier="http|dynamic|stealthy"}`

---

### Phase 3: ScrapingTool — Structured Extraction (2-3 days)

**Goal:** Add new `ScrapingTool` with structured extraction tools for the agent

**Files to create:**
- `backend/app/domain/services/tools/scraping.py` — ScrapingTool with 2 tools
- `backend/tests/domain/services/tools/test_scraping_tool.py`

**Files to modify:**
- `backend/app/domain/services/flows/plan_act.py` — Register ScrapingTool
- `backend/app/domain/services/flows/plan_act_graph.py` — Keep constructor wiring compatible
- `backend/app/domain/services/flows/tree_of_thoughts_flow.py` — Keep constructor wiring compatible
- `backend/app/domain/services/orchestration/agent_factory.py` — Keep constructor wiring compatible

**New agent tools:**
| Tool | Purpose |
|---|---|
| `scrape_structured` | Extract data using CSS/XPath selectors → JSON |
| `scrape_batch` | Fetch multiple URLs concurrently |

**Acceptance criteria:**
- Agent can call `scrape_structured(url, {"prices": ".price", "titles": "h2"})` → JSON
- Agent can batch-fetch 5-10 URLs concurrently
- Tool visible in agent's tool list when `SCRAPING_TOOL_ENABLED=true`
- All existing tools continue working unchanged

---

### Phase 4: Spider-Based Research Crawling (3-4 days)

**Goal:** Add optional Spider-backed crawl enrichment to `wide_research()`

**Files to modify:**
- `backend/app/domain/services/tools/search.py` — Add spider-based URL crawling

**Files to create:**
- `backend/app/infrastructure/external/scraper/research_spider.py` — ResearchSpider
- `backend/tests/infrastructure/external/scraper/test_research_spider.py`

**Key features:**
- Multi-session routing (fast HTTP + stealth browser)
- Per-domain throttling (no manual semaphore)
- Streaming results via `async for item in spider.stream()`
- Blocked request detection with automatic retry
- Configurable concurrency limits

**Acceptance criteria:**
- `wide_research()` preserves current search-provider flow and output contract
- `wide_research()` can optionally use Spider for top-K URL content fetching
- Per-domain throttling prevents hammering single domains
- Results stream back incrementally (not all-or-nothing)
- Existing search API integration unchanged

---

### Phase 5: Adaptive Tracking + Memory Integration (2-3 days)

**Goal:** Store element fingerprints in Qdrant for cross-session reuse

**Files to modify:**
- `backend/app/infrastructure/external/scraper/scrapling_adapter.py` — Save fingerprints
- `backend/app/domain/services/tools/scraping.py` — Adaptive extraction tool

**Integration with existing memory system:**
- Store fingerprints in `user_knowledge` Qdrant collection
- Use `MemoryType.TOOL_ARTIFACT` for element fingerprint storage
- Retrieve fingerprints on subsequent visits to same domain

**Acceptance criteria:**
- Element fingerprints stored in Qdrant on first scrape
- Subsequent scrapes of same site use adaptive mode
- Works across sessions (persistent in Qdrant)
- Feature flag: `SCRAPING_ADAPTIVE_TRACKING=true`

---

### Phase Summary

| Phase | Scope | Effort | Value | Dependencies |
|---|---|---|---|---|
| **Phase 1** | HTTP tier (Fetcher) | 2-3 days | ★★★★★ | `scrapling` core |
| **Phase 2** | Tier escalation | 2-3 days | ★★★★★ | `scrapling[fetchers]` |
| **Phase 3** | ScrapingTool | 2-3 days | ★★★ | Phase 1 |
| **Phase 4** | Spider research | 3-4 days | ★★★★ | Phase 1-2 |
| **Phase 5** | Adaptive + memory | 2-3 days | ★★★ | Phase 1, Qdrant |
| **Total** | | **11-16 days** | | Each phase independently deployable |

---

## 14. Risk Assessment & Mitigations

### 14.1 Technical Risks

| Risk | Severity | Probability | Mitigation |
|---|---|---|---|
| Scrapling Playwright conflicts with existing CDP | High | Low | Scrapling uses own Playwright instance, not shared CDP. Verified: no connection pool sharing. |
| Memory pressure from multiple browser instances | Medium | Medium | Tier 2-3 sessions created on-demand, cleaned up after use. Monitor with existing `Performance.getMetrics` checks. 4GB VRAM system needs careful monitoring. |
| Scrapling library/API instability across releases | Medium | Medium | Pin exact version in requirements, add adapter contract tests, and keep existing browser fallback path available behind feature flags. |
| TLS fingerprinting detected by advanced anti-bot | Low | Medium | curl_cffi fingerprints are regularly updated. ProxyRotator adds another evasion layer. Accept that some sites will always be unscrapable. |
| `html_to_text()` removal breaks edge cases | Low | Low | Keep `html_to_text()` as fallback path. Scrapling Adaptor handles superset of cases. |

### 14.2 Operational Risks

| Risk | Severity | Mitigation |
|---|---|---|
| New dependency adds install complexity | Low | `scrapling` core is lightweight (~10MB). `[fetchers]` extra only needed for Phase 2+. |
| Team unfamiliarity with Scrapling API | Low | API is Scrapy-like (familiar to Python scraping community). Well-documented. |
| Sandbox rebuild required for Strategy B | Medium | Phase 1-2 use Strategy A (backend-only). Sandbox changes deferred to Phase 3+. |

---

## 15. Testing Strategy

### 15.1 Unit Tests

```python
# tests/infrastructure/external/scraper/test_scrapling_adapter.py

class TestScraplingAdapter:
    """Test Scrapling adapter with mocked fetchers."""

    async def test_fetch_tier1_success(self, mock_fetcher):
        """Tier 1 HTTP fetch returns content."""

    async def test_fetch_tier1_blocked_escalates(self, mock_fetcher):
        """Tier 1 block triggers Tier 2 escalation."""

    async def test_fetch_all_tiers_fail_returns_error(self):
        """All tiers failing returns error with last attempt info."""

    async def test_proxy_rotation_applied(self, mock_rotator):
        """Proxy rotator provides next proxy per request."""

    async def test_impersonation_setting_passed(self):
        """Default impersonation from config is passed to Fetcher."""


# tests/domain/services/tools/test_scraping_tool.py

class TestScrapingTool:
    """Test ScrapingTool agent interface."""

    async def test_scrape_structured_returns_json(self, mock_scraper):
        """Structured extraction returns field→values dict."""

    async def test_scrape_batch_concurrent(self, mock_scraper):
        """Batch fetch runs URLs concurrently."""

    async def test_tool_schema_correct(self):
        """Tool schemas match expected format for LLM."""
```

### 15.2 Integration Tests

```python
# tests/integration/test_scrapling_integration.py

class TestScraplingIntegration:
    """Integration tests against real websites (marked slow)."""

    @pytest.mark.slow
    async def test_fetch_static_page(self):
        """Fetch a known static page via Tier 1."""

    @pytest.mark.slow
    async def test_fetch_js_page_escalates(self):
        """JS-required page escalates to Tier 2."""

    @pytest.mark.slow
    async def test_browser_tool_search_uses_scrapling(self):
        """BrowserTool.search() uses Scrapling when enabled."""
```

### 15.3 Existing Test Compatibility

All existing tests must continue passing:
```bash
cd backend && pytest tests/ -p no:cov -o addopts=
```

Particularly:
- `tests/domain/services/tools/test_browser_tool.py`
- `tests/domain/services/tools/test_search_tool.py`
- Any tests that mock `aiohttp` responses (need adapter for Scrapling)

---

## 16. Open Questions

1. **Sandbox vs Backend for Tier 2-3:** Should Scrapling's browser-based fetchers run in
   the backend (simpler, less isolated) or inside the sandbox (more secure, requires rebuild)?
   Recommendation: Backend for Phase 1-2, Sandbox for Phase 3+.

2. **`html_to_text()` deprecation timeline:** Should the regex parser be removed entirely
   once Scrapling is stable, or kept as a permanent fallback? Recommendation: Keep for 2 releases.

3. **Proxy provider:** If proxy rotation is enabled, which proxy provider to use?
   Options: free proxy lists (unreliable), residential proxy service (cost), no proxies (default).
   Recommendation: Default to no proxies. Make it configurable for users who have proxy services.

4. **CDP live preview with Scrapling fetches:** When Scrapling's `StealthyFetcher` renders
   a page, the user can't see it in live preview (it's a separate browser instance).
   Should we add a follow-up `navigate_for_display()` call after successful Scrapling fetch?
   Recommendation: Yes, same pattern as current `search()` method.

5. **Scrapling MCP Server:** Scrapling includes a built-in MCP server. Should we expose it
   alongside Pythinker's existing MCP integration? Recommendation: Evaluate after Phase 2.
   May provide value for direct AI-assisted scraping workflows.

6. **Memory impact on 4GB VRAM system:** Running existing Chrome (CDP) + Scrapling's
   StealthyFetcher (separate Playwright) simultaneously. Need benchmarking to verify
   total memory stays within safe limits. Recommendation: Phase 2 includes memory
   benchmarking before production deployment.

---

## Appendix A: Scrapling API Quick Reference

```python
# ── Fetchers ──────────────────────────────────────
from scrapling.fetchers import (
    Fetcher,            # HTTP (curl_cffi, TLS impersonation)
    AsyncFetcher,       # Async HTTP
    DynamicFetcher,     # Playwright Chromium
    StealthyFetcher,    # Hardened Playwright (anti-bot)
)

# ── Sessions (persistent state) ──────────────────
from scrapling.fetchers import (
    FetcherSession,          # HTTP session (cookies, login state)
    AsyncStealthySession,    # Async stealthy session (tab pool)
    AsyncDynamicSession,     # Async dynamic session (tab pool)
)

# ── Spider Framework ─────────────────────────────
from scrapling.spiders import Spider, Request, Response

# ── Proxy Rotation ───────────────────────────────
from scrapling import ProxyRotator

# ── Adaptor (Parser) ─────────────────────────────
# Returned by all fetchers:
page = Fetcher.get(url)
page.css('.class')               # CSS selector → list of elements
page.css('.class').first         # First match selector
page.css('.class').get()         # First match serialized/text value
page.css('.class::text')         # Text content
page.css('.class::attr(href)')   # Attribute value
page.xpath('//div[@class]')      # XPath selector
page.get_all_text()              # All text content
page.re(r'pattern')              # Regex search
page.find_all(text='keyword')    # Text search
page.html                        # Raw HTML
page.status                      # HTTP status code
```

## Appendix B: Related Pythinker Architecture Docs

- `docs/architecture/BROWSER_ARCHITECTURE.md` — Current browser stack
- `docs/architecture/HTTP_CLIENT_POOLING.md` — HTTPClientPool usage
- `docs/architecture/MULTI_API_KEY_MANAGEMENT.md` — APIKeyPool pattern
- `docs/architecture/AUTOMATIC_BROWSER_BEHAVIOR.md` — Auto-browse behavior
- `DEEPCODE_INTEGRATION_COMPLETE.md` — DeepCode reliability enhancements
