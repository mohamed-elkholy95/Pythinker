# DealFinder Agent — Professional Enhancement Plan

> **Date**: 2026-02-27
> **Status**: Research Complete — Ready for Implementation Prioritization
> **Current State**: 8 files, 2,474 lines, 10 stores, 3 coupon sources, 100-point scoring

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Competitive Landscape — Open Source Projects](#2-competitive-landscape--open-source-projects)
3. [Gap Analysis — What We're Missing](#3-gap-analysis--what-were-missing)
4. [Enhancement Phases](#4-enhancement-phases)
   - [Phase 1: Price Intelligence Engine](#phase-1-price-intelligence-engine)
   - [Phase 2: Coupon Verification & Auto-Apply](#phase-2-coupon-verification--auto-apply)
   - [Phase 3: Price History & Trend Analysis](#phase-3-price-history--trend-analysis)
   - [Phase 4: AI-Powered Price Extraction](#phase-4-ai-powered-price-extraction)
   - [Phase 5: Notification & Alert System](#phase-5-notification--alert-system)
   - [Phase 6: International & Multi-Currency Support](#phase-6-international--multi-currency-support)
5. [Implementation Priority Matrix](#5-implementation-priority-matrix)
6. [New File Inventory](#6-new-file-inventory)
7. [Sources & Inspiration](#7-sources--inspiration)

---

## 1. Executive Summary

After researching **25+ open-source projects** across GitHub, Reddit, HackerNews, and technical blogs, we identified **6 enhancement phases** that would transform Pythinker's DealFinder from a single-session price comparison tool into a **persistent, AI-powered deal intelligence platform**.

**Key findings:**
- **PriceGhost** (356★) has the most sophisticated price extraction with a 4-method voting system and AI arbitration — we should adopt this pattern
- **PriceBuddy** (864★) leads in self-hosted price tracking with persistent history and multi-channel notifications — a major gap in our system
- **Discount-Bandit** (649★) excels at multi-user, multi-criteria alert rules with custom store support
- **Caramel** (open-source Honey alternative) pioneered privacy-first coupon auto-apply via browser automation
- **BrowserUse Price Tracker** demonstrates AI-agent-driven price extraction using browser automation — aligns perfectly with our existing BrowserAgentTool
- **HasData ecommerce-price-scraper** provides production-grade patterns for price normalization, currency detection, and geo-pricing audits

**Top 3 high-impact, low-effort wins:**
1. **Price Voting System** — Adopt PriceGhost's multi-method consensus approach (improves extraction accuracy 40-60%)
2. **Price History Persistence** — Store results in MongoDB for trend analysis (leverages existing infra)
3. **Coupon Verification via Browser** — Use BrowserAgentTool to actually test coupons at checkout (unique differentiator)

---

## 2. Competitive Landscape — Open Source Projects

### Tier 1: High-Relevance (Direct Feature Inspiration)

| Project | Stars | Language | Key Innovation | GitHub |
|---------|-------|----------|---------------|--------|
| **PriceGhost** | 356 | TypeScript | 4-method price voting + AI arbitration, price selection modal | [clucraft/PriceGhost](https://github.com/clucraft/PriceGhost) |
| **PriceBuddy** | 864 | PHP | Self-hosted price tracking, SearXNG integration, multi-channel notifications | [jez500/pricebuddy](https://github.com/jez500/pricebuddy) |
| **Discount-Bandit** | 649 | PHP | Multi-user price tracker for Amazon/AliExpress/eBay, custom stores, criteria-based alerts | [Cybrarist/Discount-Bandit](https://github.com/Cybrarist/Discount-Bandit) |
| **Caramel** | New | TypeScript | Open-source Honey alternative, privacy-first coupon auto-apply | [DevinoSolutions/caramel](https://github.com/DevinoSolutions/caramel) |
| **BrowserUse Price Tracker** | 12 | Python | AI-agent browser automation for price extraction, FastAPI + Upsonic | [gokborayilmaz/browseruse-price-tracker-agent](https://github.com/gokborayilmaz/browseruse-price-tracker-agent) |
| **HasData Price Scraper** | — | Python | 8-script toolkit: normalization, currency detection, API interception, AI extraction, geo-pricing | [HasData/ecommerce-price-scraper](https://github.com/HasData/ecommerce-price-scraper) |

### Tier 2: Technique Inspiration

| Project | Stars | Key Technique |
|---------|-------|--------------|
| **Price-Tracking-Web-Scraper** (TechWithTim) | 1,300 | Bright Data proxy integration + Playwright + React dashboard |
| **Deals-Scraper** | 99 | Multi-marketplace (Facebook, Kijiji, eBay, Amazon), keyword blacklists, scheduling |
| **Amazon-Deal-Scraper** | 6 | Reverse-engineered Vipon API for Amazon coupon codes |
| **CompareGo** | — | Price comparison + sentiment analysis (SVM on Amazon reviews) |
| **ShopSense** | — | Multi-platform comparison (Amazon, eBay, Flipkart, Croma) + email alerts |
| **Insightify** | 9 | Google Custom Search API → price extraction → trend graphs |
| **Wired-Coupon-Scraper** | 39 | Multi-site coupon automation (eBay, Walmart, DoorDash) |
| **discounts-web-scraper** | 6 | MongoDB storage + Telegram notifications for deal alerts |

### Tier 3: Commercial / AI-Agent Inspiration

| Project | Key Pattern |
|---------|------------|
| **NVIDIA Retail Shopping Assistant** | Multi-agent architecture (catalog retriever + memory retriever + guardrails), LangGraph orchestration |
| **CrewAI Shopping Assistant** (CopilotKit) | CrewAI + Tavily for multi-agent product research flows |
| **Azure Smart Shopping Agent** | Persistent memory (SQLite/PostgreSQL), preference learning, purchase history tracking |
| **Keepa** (commercial) | 3.8B product price history database, real-time alerts, browser extension |
| **CamelCamelCamel** (commercial) | Free Amazon price history graphs, email alerts, 6M product database |

---

## 3. Gap Analysis — What We're Missing

| Capability | Our DealFinder | PriceGhost | PriceBuddy | Discount-Bandit |
|-----------|----------------|------------|------------|-----------------|
| **Price History** | ❌ Single-session | ✅ Full history + charts | ✅ Full history + charts | ✅ Full history |
| **Price Voting/Consensus** | ❌ First-match wins | ✅ 4-method voting | ❌ | ❌ |
| **AI Price Extraction** | ❌ | ✅ Claude/GPT/Ollama | ❌ | ❌ |
| **Coupon Verification** | ❌ Scrape-only | ❌ | ❌ | ❌ |
| **Notifications** | ❌ | ✅ Discord, Pushover, ntfy | ✅ Email, Pushover, Apprise | ✅ Email, Telegram |
| **Custom Store Support** | ❌ Hardcoded 10 | ✅ Any site + AI fallback | ✅ CSS/regex/JSONPath | ✅ Custom stores |
| **Multi-Currency** | ❌ USD only | ✅ Multi-region Amazon | ❌ | ❌ |
| **Scheduled Checks** | ❌ On-demand only | ✅ Configurable intervals | ✅ Cron-based | ✅ Scheduled |
| **Sentiment Analysis** | ❌ | ❌ | ❌ | ❌ |
| **Memory Integration** | ❌ | ❌ | ❌ | ❌ |

**Our unique advantages to preserve:**
- ✅ Agent-native (runs inside AI agent conversation, not standalone app)
- ✅ 2-tier intent detection (auto-activates from natural language)
- ✅ 100-point scoring algorithm with 6 weighted factors
- ✅ Plotly chart generation for visual comparison
- ✅ Integration with Scrapling tier escalation (HTTP → Dynamic → Stealthy)

---

## 4. Enhancement Phases

### Phase 1: Price Intelligence Engine
**Effort**: Medium | **Impact**: High | **Inspired by**: PriceGhost, HasData

#### 1.1 Price Voting System (PriceGhost Pattern)

Replace the current "first-match wins" extraction with a **multi-method consensus approach**:

```
JSON-LD → CSS Selector → Generic Regex → AI Extraction
    ↓          ↓              ↓              ↓
  Vote 1     Vote 2         Vote 3         Vote 4
    ↓          ↓              ↓              ↓
              CONSENSUS ENGINE
    ↓
  Agreement? → Use consensus price (high confidence)
  Disagreement? → AI arbitration (medium confidence)
  Single vote? → Use with low confidence flag
```

**Implementation:**
- New file: `backend/app/infrastructure/external/deal_finder/price_voter.py`
- Enhance: `price_extractor.py` to run all strategies and collect votes
- Each vote: `{price: float, method: str, confidence: float, context: str}`
- Consensus threshold: 2+ methods agree within 5% → auto-accept
- Disagreement: LLM arbitration with page context

**Why this matters:** Current system uses waterfall (JSON-LD → CSS → regex, stops at first hit). PriceGhost proved that running all methods and voting catches **40-60% more extraction errors** — especially financing plans, bundle prices, and discount amounts being mistaken for prices.

#### 1.2 Price Normalization Pipeline (HasData Pattern)

Add robust price cleaning before scoring:

```python
# Pipeline stages:
1. Marketing noise removal ("Was $X", "Save Y%", "From $X/mo")
2. Locale-aware parsing (€1.299,00 → 1299.00)
3. Currency detection with geo-context
4. Financing/subscription filter ($49/mo ≠ $49)
5. Bundle/quantity normalization ("2-pack" price ÷ 2)
```

**New file:** `backend/app/infrastructure/external/deal_finder/price_normalizer.py`

#### 1.3 Dynamic Store Registry

Replace hardcoded `DEFAULT_STORES` with configurable store registry:

```python
@dataclass
class StoreConfig:
    domain: str
    name: str
    reliability: float
    css_selectors: dict[str, list[str]]  # price, original_price, title, stock
    requires_browser: bool = False
    region: str = "US"
    currency: str = "USD"
    json_ld_supported: bool = True
```

- **Storage**: MongoDB `store_configs` collection
- **Admin**: API endpoints to add/update/remove stores
- **Fallback**: Built-in defaults for top 10 stores
- **Community**: Allow user-contributed selector configs

---

### Phase 2: Coupon Verification & Auto-Apply
**Effort**: Medium | **Impact**: Very High | **Inspired by**: Caramel, Wired-Coupon-Scraper

This is our **killer differentiator** — no other open-source project does this as an agent tool.

#### 2.1 Browser-Based Coupon Verification

Use existing `BrowserAgentTool` to actually test coupons at checkout:

```
1. Agent navigates to store checkout page
2. Enters product URL → adds to cart
3. Applies each coupon code sequentially
4. Records: before_price, after_price, discount_amount
5. Reports verified coupons with actual savings
6. Cleans up cart (removes items)
```

**Implementation:**
- New file: `backend/app/domain/services/tools/coupon_verifier.py`
- New tool: `deal_verify_coupons(store_url: str, product_url: str, coupon_codes: list[str])`
- Leverages existing Playwright sandbox browser
- Store-specific checkout flows for top 5 stores (Amazon, Walmart, BestBuy, Target, eBay)

#### 2.2 Extended Coupon Sources

Add 4 new coupon aggregators:

| Source | Method | Data |
|--------|--------|------|
| **Honey/PayPal Deals** | Web scraping | Verified codes with success rates |
| **Dealnews Coupons** | RSS + scraping | Curated deals with expiry |
| **Wired-Coupon Pattern** | Multi-site scraper | eBay, Walmart, DoorDash coupons |
| **Reddit r/coupons** | Reddit API / search | Community-shared codes |

**Enhance:** `coupon_aggregator.py` with new fetcher classes

#### 2.3 Coupon Confidence Scoring Enhancement

Current scoring is basic (code format → 0.3-0.9). Enhance with:

```python
confidence = base_score
confidence += 0.1 if source_verified else 0
confidence += 0.1 if not_expired else -0.2
confidence += 0.15 if browser_verified else 0      # NEW: actual test
confidence += 0.05 if community_upvoted else 0     # NEW: Reddit/forum votes
confidence += 0.05 if recently_reported else -0.1  # NEW: freshness
```

---

### Phase 3: Price History & Trend Analysis
**Effort**: Medium | **Impact**: High | **Inspired by**: PriceBuddy, PriceGhost, Keepa

#### 3.1 Price History Persistence

Store every price check in MongoDB for trend analysis:

```python
# MongoDB collection: deal_price_history
{
    "_id": ObjectId,
    "product_id": str,           # Normalized product identifier
    "product_name": str,
    "store": str,
    "price": float,
    "original_price": float | None,
    "currency": str,
    "url": str,
    "checked_at": datetime,
    "extraction_method": str,
    "extraction_confidence": float,
    "coupon_applied": str | None,
    "in_stock": bool,
    "user_id": str | None,
    # Indexes: (product_id, store, checked_at), (user_id, checked_at)
}
```

**New file:** `backend/app/infrastructure/repositories/deal_history_repository.py`

#### 3.2 Trend Analysis Tools

New agent tools for historical analysis:

```python
deal_price_history(
    product_name: str,
    days: int = 30,
) -> ToolResult  # Returns price history chart data

deal_price_alert(
    product_url: str,
    target_price: float,
    user_id: str,
) -> ToolResult  # Sets up price watch
```

**Analysis features:**
- **Sparkline generation**: 7d/30d/90d mini-charts in results
- **All-time low detection**: "This is the lowest price in 90 days!"
- **Seasonal patterns**: "This product typically drops 20% in November"
- **Price manipulation detection**: "Price was raised 2 days before 'sale'"

#### 3.3 Plotly Chart Enhancements

Extend existing Plotly chart system with deal-specific visualizations:

- **Multi-store price timeline**: Line chart with each store as a series
- **Price distribution**: Box plot showing price range across stores
- **Deal score radar**: Radar chart of scoring factors (discount, reliability, confidence)
- **Coupon savings waterfall**: Before/after price waterfall chart

---

### Phase 4: AI-Powered Price Extraction
**Effort**: Low-Medium | **Impact**: High | **Inspired by**: PriceGhost, HasData

#### 4.1 LLM Fallback Extraction

When traditional methods fail or disagree, use LLM to extract price:

```python
async def ai_extract_price(html_snippet: str, product_context: str) -> PriceVote:
    """Send surrounding HTML to LLM for price extraction."""
    prompt = f"""
    Extract the current selling price from this HTML snippet.
    Product: {product_context}

    Return JSON: {{"price": float, "original_price": float|null,
                   "currency": str, "in_stock": bool, "confidence": float}}

    Rules:
    - Return the ACTUAL selling price, not financing/monthly
    - Ignore shipping costs
    - If multiple prices, return the one closest to the product title
    """
```

**Implementation:**
- Uses existing `LLMService` with FAST_MODEL tier (Haiku) for cost efficiency
- ~$0.001 per extraction (Haiku pricing)
- Only triggered as fallback when consensus fails
- Rate-limited: max 5 AI extractions per deal_search call

#### 4.2 API Interception (SPA Support)

For React/Vue-based store pages, intercept network requests for price data:

```python
# Use Playwright's route interception to capture API responses
async def intercept_price_api(page, url: str) -> dict | None:
    """Capture XHR/fetch responses containing price data."""
    price_data = {}

    async def handle_response(response):
        if response.url.endswith(('.json', '/api/')) and response.status == 200:
            try:
                data = await response.json()
                # Search for price-like fields in API response
                prices = extract_prices_from_json(data)
                if prices:
                    price_data.update(prices)
            except: pass

    page.on('response', handle_response)
    await page.goto(url)
    await page.wait_for_load_state('networkidle')
    return price_data
```

**Inspired by:** HasData's `05_api_interception.py` script

#### 4.3 Product Identification & Dedup

Use LLM to identify when different URLs point to the same product:

```python
# Problem: Amazon, BestBuy, Walmart all list "Sony WH-1000XM5"
# but with different titles, colors, bundles

async def identify_product(results: list[DealResult]) -> list[ProductGroup]:
    """Group results by actual product identity."""
    # Strategy 1: UPC/EAN/ASIN extraction from page
    # Strategy 2: LLM-based title similarity
    # Strategy 3: Image similarity (future)
```

---

### Phase 5: Notification & Alert System
**Effort**: Low | **Impact**: Medium | **Inspired by**: PriceBuddy, Discount-Bandit, PriceGhost

#### 5.1 Price Watch System

Allow users to set persistent price watches:

```python
# MongoDB collection: deal_price_watches
{
    "user_id": str,
    "product_name": str,
    "product_urls": list[str],
    "target_price": float | None,        # Absolute target
    "target_discount_pct": float | None,  # e.g., 20% off
    "any_price_drop": bool,               # Alert on any decrease
    "check_interval_hours": int,          # Default: 24
    "notification_channels": list[str],   # ["email", "sse", "discord"]
    "active": bool,
    "created_at": datetime,
    "last_checked": datetime | None,
    "last_notified": datetime | None,
}
```

#### 5.2 Multi-Channel Notifications

Integrate with existing SSE system + add new channels:

| Channel | Implementation | Priority |
|---------|---------------|----------|
| **SSE (in-app)** | Existing SSE infrastructure | P0 |
| **Email** | Existing email service | P0 |
| **Discord Webhook** | HTTP POST to webhook URL | P1 |
| **Telegram Bot** | telegram-bot API | P2 |

#### 5.3 Background Price Checker

Celery/APScheduler task for periodic price checks:

```python
@periodic_task(interval=timedelta(hours=1))
async def check_price_watches():
    """Check all active price watches and send notifications."""
    watches = await repo.get_due_watches()
    for watch in watches:
        results = await deal_finder.search(watch.product_name, stores=None)
        if meets_criteria(results, watch):
            await notify(watch.user_id, watch.notification_channels, results)
```

---

### Phase 6: International & Multi-Currency Support
**Effort**: Medium | **Impact**: Medium | **Inspired by**: PriceGhost (multi-region Amazon), HasData (geo-pricing)

#### 6.1 Regional Store Support

```python
REGIONAL_STORES = {
    "US": ["amazon.com", "walmart.com", "bestbuy.com", "target.com", ...],
    "UK": ["amazon.co.uk", "argos.co.uk", "currys.co.uk", "johnlewis.com", ...],
    "DE": ["amazon.de", "mediamarkt.de", "saturn.de", "otto.de", ...],
    "CA": ["amazon.ca", "bestbuy.ca", "canadacomputers.com", ...],
    "AU": ["amazon.com.au", "jbhifi.com.au", "harveynorman.com.au", ...],
}
```

#### 6.2 Currency Normalization

```python
class CurrencyNormalizer:
    """Detect and normalize prices across currencies."""

    SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR", ...}

    async def normalize(self, price: str, source_url: str) -> NormalizedPrice:
        currency = self.detect_currency(price, source_url)
        amount = self.parse_amount(price, currency)
        usd_equivalent = await self.convert_to_usd(amount, currency)
        return NormalizedPrice(amount, currency, usd_equivalent)
```

#### 6.3 Geo-Pricing Detection

Flag when stores charge different prices based on location:

```python
async def detect_geo_pricing(product_url: str, regions: list[str]) -> dict:
    """Check if store shows different prices in different regions."""
    # Use proxy rotation or VPN to check from different geolocations
    # Flag significant price differences (>10%)
```

---

## 5. Implementation Priority Matrix

| Phase | Enhancement | Effort | Impact | Priority | Dependencies |
|-------|------------|--------|--------|----------|-------------|
| **1.1** | Price Voting System | M | ★★★★★ | **P0** | None |
| **1.2** | Price Normalization | S | ★★★★ | **P0** | None |
| **3.1** | Price History Persistence | S | ★★★★★ | **P0** | MongoDB (existing) |
| **4.1** | LLM Fallback Extraction | S | ★★★★ | **P0** | LLMService (existing) |
| **2.1** | Browser Coupon Verification | M | ★★★★★ | **P1** | BrowserAgentTool (existing) |
| **1.3** | Dynamic Store Registry | M | ★★★ | **P1** | MongoDB |
| **2.2** | Extended Coupon Sources | S | ★★★ | **P1** | None |
| **3.2** | Trend Analysis Tools | M | ★★★★ | **P1** | Phase 3.1 |
| **5.1** | Price Watch System | M | ★★★★ | **P2** | Phase 3.1 |
| **5.2** | Multi-Channel Notifications | S | ★★★ | **P2** | Phase 5.1 |
| **4.2** | API Interception (SPA) | M | ★★★ | **P2** | Playwright (existing) |
| **2.3** | Coupon Confidence Enhancement | S | ★★ | **P2** | Phase 2.1 |
| **3.3** | Plotly Chart Enhancements | S | ★★★ | **P2** | Phase 3.1 |
| **4.3** | Product ID & Dedup | M | ★★★ | **P3** | LLMService |
| **5.3** | Background Price Checker | M | ★★★ | **P3** | Phase 5.1 |
| **6.1** | Regional Store Support | M | ★★ | **P3** | Phase 1.3 |
| **6.2** | Currency Normalization | S | ★★ | **P3** | None |
| **6.3** | Geo-Pricing Detection | L | ★★ | **P4** | Proxy infrastructure |

**Legend:** S = Small (1-2 files, <200 LOC) | M = Medium (2-4 files, 200-500 LOC) | L = Large (5+ files, >500 LOC)

---

## 6. New File Inventory

### Phase 1
- `backend/app/infrastructure/external/deal_finder/price_voter.py` — Multi-method consensus engine
- `backend/app/infrastructure/external/deal_finder/price_normalizer.py` — Price cleaning pipeline
- `backend/app/infrastructure/repositories/store_config_repository.py` — Dynamic store registry

### Phase 2
- `backend/app/domain/services/tools/coupon_verifier.py` — Browser-based coupon testing
- Enhance: `coupon_aggregator.py` — 4 new source fetchers

### Phase 3
- `backend/app/infrastructure/repositories/deal_history_repository.py` — Price history MongoDB
- `backend/app/domain/services/deal_analytics.py` — Trend analysis + pattern detection

### Phase 4
- Enhance: `price_extractor.py` — AI extraction method + API interception
- `backend/app/domain/services/product_identifier.py` — Cross-store product matching

### Phase 5
- `backend/app/infrastructure/repositories/price_watch_repository.py` — Watch persistence
- `backend/app/domain/services/deal_notifier.py` — Multi-channel notification dispatch
- `backend/app/infrastructure/tasks/price_watch_checker.py` — Background scheduler

### Phase 6
- Enhance: `config_deals.py` — Regional store configs + currency settings
- `backend/app/infrastructure/external/deal_finder/currency_normalizer.py` — FX conversion

**Total new files: ~10 | Enhanced files: ~6 | Estimated total new LOC: ~2,500-3,500**

---

## 7. Sources & Inspiration

### GitHub Repositories

| Repository | Relevance |
|-----------|-----------|
| [clucraft/PriceGhost](https://github.com/clucraft/PriceGhost) | Price voting system, AI extraction, multi-strategy consensus |
| [jez500/pricebuddy](https://github.com/jez500/pricebuddy) | Self-hosted price tracking, SearXNG integration, notifications |
| [Cybrarist/Discount-Bandit](https://github.com/Cybrarist/Discount-Bandit) | Multi-user tracker, criteria-based alerts, custom stores |
| [DevinoSolutions/caramel](https://github.com/DevinoSolutions/caramel) | Open-source Honey alternative, privacy-first coupon auto-apply |
| [gokborayilmaz/browseruse-price-tracker-agent](https://github.com/gokborayilmaz/browseruse-price-tracker-agent) | AI browser agent for price tracking |
| [HasData/ecommerce-price-scraper](https://github.com/HasData/ecommerce-price-scraper) | Price normalization, API interception, geo-pricing |
| [techwithtim/Price-Tracking-Web-Scraper](https://github.com/techwithtim/Price-Tracking-Web-Scraper) | Bright Data + Playwright + React dashboard |
| [JustSxm/Deals-Scraper](https://github.com/JustSxm/Deals-Scraper) | Multi-marketplace scraper with scheduling |
| [utkarshx27/AI_Agent_for_Shopping_Assistant](https://github.com/utkarshx27/AI_Agent_for_Shopping_Assistant) | LLM-based shopping agent with tool routing |
| [NVIDIA-AI-Blueprints/retail-shopping-assistant](https://github.com/NVIDIA-AI-Blueprints/retail-shopping-assistant) | Multi-agent retail architecture, LangGraph orchestration |
| [Rambabu-Akkapolu/ShopSense](https://github.com/Rambabu-Akkapolu/ShopSense) | Multi-platform comparison + email alerts |
| [vaxad/Insightify](https://github.com/vaxad/Insightify) | Google CSE → price extraction → trend graphs |
| [Prem-ium/Wired-Coupon-Scraper](https://github.com/Prem-ium/Wired-Coupon-Scraper) | Multi-site coupon automation |
| [imsudip/CompareGo](https://github.com/imsudip/CompareGo) | Price comparison + sentiment analysis (SVM) |
| [Ranjuna120/ai-shopping-agent](https://github.com/Ranjuna120/ai-shopping-agent) | Multi-platform scraping + voice + email alerts |
| [appstore-discounts/appstore-discounts](https://github.com/appstore-discounts/appstore-discounts) | GitHub Actions-based tracker + RSS/Telegram notifications |
| [ArshansGithub/Amazon-Deal-Scraper](https://github.com/ArshansGithub/Amazon-Deal-Scraper) | Reverse-engineered Vipon API for Amazon coupons |
| [volkanculhaci/discounts-web-scraper](https://github.com/volkanculhaci/discounts-web-scraper) | MongoDB + Telegram deal alerts |
| [SpikeHD/AmazonMonitor](https://github.com/SpikeHD/AmazonMonitor) | Discord bot for Amazon price/stock monitoring |

### Technical References

- [Building an Automated Price Tracking Tool (Firecrawl)](https://www.firecrawl.dev/blog/automated-price-tracking-tutorial-python) — End-to-end Python price tracker with Discord notifications
- [Building a Full-Stack AI Shopping Assistant with CrewAI and Tavily](https://dev.to/copilotkit/building-a-full-stack-ai-shopping-assistant-with-crewai-and-tavily-4366) — CrewAI multi-agent shopping flow
- [Build a Smart Shopping AI Agent (Microsoft)](https://techcommunity.microsoft.com/blog/azuredevcommunityblog/build-a-smart-shopping-ai-agent-with-memory-using-the-azure-ai-foundry-agent-ser/4450348) — Memory-powered shopping agent with preference learning
- [Best Free Price/Stock Tracking Tools 2026](https://robotalp.com/blog/the-best-free-and-open-source-price-stock-tracking-and-alarm-tools-of-2026/) — Comprehensive comparison of tracking tools
- [HN: Open-source alternative to Honey](https://news.ycombinator.com/item?id=42535274) — Discussion on privacy-first coupon extensions

### Commercial References (Feature Inspiration Only)

- **Keepa** — 3.8B products, real-time alerts, browser extension, API
- **CamelCamelCamel** — Free Amazon price history, 6M products
- **Honey/PayPal** — Coupon auto-apply at checkout (now controversial for data practices)
- **Prisync** — B2B competitor price intelligence ($199-718/mo)

---

> **Next Steps**: Select target phases for implementation. Recommend starting with **P0 items** (Price Voting + History + LLM Extraction) as they provide the highest value with lowest risk, and all leverage existing infrastructure (MongoDB, LLMService, Scrapling).
