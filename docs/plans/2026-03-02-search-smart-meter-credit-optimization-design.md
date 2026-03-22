# Search Smart Meter: Credit-Optimized Search System Redesign

**Date:** 2026-03-02
**Status:** Approved
**Approach:** A + C hybrid (Smart Meter + Multi-Provider Spread)

## Problem

With all search providers on free tiers (Tavily 1000, Serper 2500, Brave 2000, Exa 1000, Jina ~500, DuckDuckGo/Bing unlimited), the current system:

1. **Burns credits blindly** — no awareness of per-provider quotas or monthly budgets
2. **Uses advanced depth universally** — Tavily `advanced` costs 2 credits when `basic` (1 credit) suffices for most queries
3. **wide_research is overkill** — 3 queries x 2 variants = 6+ API calls even for simple lookups
4. **Dedup is weak** — string normalization misses paraphrased duplicates
5. **Static fallback chain** — hammers first provider until exhaustion instead of spreading load
6. **Live view shows only 5 results** — hardcoded `[:5]` in `base.py` wastes the 20 results already fetched
7. **No user visibility** — users can't see which provider answered or how many credits were consumed

### Credit Math (Current)

| Tool | Sub-searches | Credits (Tavily advanced) |
|------|-------------|--------------------------|
| `info_search_web` | 1 | 2 |
| `expanded_search` | up to 3 variants | up to 6 |
| `wide_research(3 queries)` | 3 x 2 variants = 6 | 12 |

A typical research task (3 search steps) burns ~36 credits. With 1000 Tavily credits, that's ~28 tasks/month.

### Credit Math (Target)

| Tool | Sub-searches | Credits (basic + smart routing) |
|------|-------------|-------------------------------|
| QUICK lookup | 1 | 1 (basic) or 0 (free scraper) |
| STANDARD search | 1 | 1 (basic) or 2 (advanced, if warranted) |
| DEEP research | 2-3 | 2-3 (basic) or 4-6 (advanced) |

Target: 60-70% credit reduction. Same workload = ~100-150 credits instead of ~500.

## Architecture

### Data Flow

```
Agent calls search tool
    |
    v
SearchQuotaManager.route(query, context)
    |-- 1. QueryIntentClassifier.classify(query) -> QUICK | STANDARD | DEEP
    |-- 2. EnhancedDedup.is_duplicate(query) -> skip if duplicate
    |-- 3. CostAwareRouter.select_provider(intent, quotas, health)
    |-- 4. Depth selection: basic by default, upgrade only if intent + budget warrant
    |-- 5. Execute search via selected provider
    |-- 6. Quality check: if 5+ results, early stop (don't try next provider)
    |-- 7. Record usage -> Redis quota counters
    |
    v
ToolResult (with provider/depth/credits metadata for live view)
```

## Component Design

### 1. SearchQuotaManager (Singleton)

**File:** `backend/app/domain/services/search/quota_manager.py`

Orchestrator that wires together intent classification, dedup, routing, and quota tracking.

```python
class SearchQuotaManager:
    """Central search orchestrator that minimizes credit consumption
    while maintaining result quality.

    Responsibilities:
    - Classify query intent (QUICK/STANDARD/DEEP)
    - Check semantic dedup before executing
    - Route to cheapest healthy provider with remaining quota
    - Select search depth based on intent + remaining budget
    - Track per-provider monthly usage
    - Auto-degrade when budget runs low
    """

    def __init__(
        self,
        redis_client: Any | None,
        intent_classifier: QueryIntentClassifier,
        cost_router: CostAwareSearchRouter,
        dedup: EnhancedDedup,
    ): ...

    async def route(
        self,
        query: str,
        search_engine: SearchEngine,  # fallback engine (existing)
        context: SearchContext | None = None,
    ) -> ToolResult[SearchResults]: ...

    async def get_quota_status(self) -> dict[str, QuotaStatus]: ...
```

**Singleton pattern:** `get_search_quota_manager()` factory, consistent with existing `get_*()` patterns.

**Redis keys:**
- `search_quota:{provider}:{YYYY-MM}` — monthly credit counter (hash: used, limit)
- TTL: 32 days (auto-expire after month ends)
- Graceful fallback: in-memory `defaultdict(int)` when Redis unavailable

### 2. QueryIntentClassifier (Rule-Based)

**File:** `backend/app/domain/services/search/intent_classifier.py`

No LLM calls — pure pattern matching for <1ms classification.

```python
class SearchIntent(str, Enum):
    QUICK = "quick"        # 1 API call, basic depth, 10 results
    STANDARD = "standard"  # 1 API call, advanced depth, 20 results
    DEEP = "deep"          # wide_research, advanced depth

class QueryIntentClassifier:
    """Rule-based query intent classification.

    Classifies queries into QUICK/STANDARD/DEEP tiers
    to determine appropriate search depth and credit allocation.
    """

    QUICK_PATTERNS = [
        r"\b(what is|define|who is|when did|where is)\b",
        r"\b(meaning of|definition of)\b",
        # Single-entity queries (1-3 words, no comparison operators)
    ]

    STANDARD_PATTERNS = [
        r"\b(compare|vs|versus|best|latest|review|how to)\b",
        r"\b(current|recent|2025|2026|this year|this month)\b",
        r"\b(price|cost|spec|feature|release|performance)\b",
    ]

    DEEP_PATTERNS = [
        r"\b(research|analyze|comprehensive|in-depth|thorough)\b",
        r"\b(pros and cons|advantages and disadvantages)\b",
        # Multiple comparison targets ("X vs Y vs Z")
    ]

    def classify(self, query: str) -> SearchIntent: ...
```

**Budget-aware downgrade logic:**
- Quota < 20% remaining: DEEP → STANDARD
- Quota < 10% remaining: STANDARD → QUICK
- Quota < 5% remaining: all queries → free scrapers only (DuckDuckGo/Bing)

### 3. CostAwareSearchRouter

**File:** `backend/app/domain/services/search/cost_router.py`

Replaces static fallback chain with cost-optimized dynamic routing.

```python
PROVIDER_COST = {
    "tavily_basic": 1,
    "tavily_advanced": 2,
    "serper": 1,
    "brave": 1,
    "exa": 1,
    "jina": 1,
    "duckduckgo": 0,  # free scraper
    "bing": 0,        # free scraper
}

class CostAwareSearchRouter:
    """Routes search queries to the cheapest healthy provider
    with remaining monthly quota.

    Routing score formula:
        score = (1 - quota_usage_ratio) * health_score * (1 / cost_per_query)

    Free scrapers (DuckDuckGo, Bing) used for:
    - QUICK intent queries (when search_prefer_free_scrapers_for_quick=True)
    - All queries when paid provider quotas are exhausted
    - Fallback when all paid providers are unhealthy
    """

    def select_provider(
        self,
        intent: SearchIntent,
        quotas: dict[str, QuotaStatus],
        health_scores: dict[str, float],
    ) -> tuple[str, str]:
        """Returns (provider_name, search_depth)."""
        ...

    def select_depth(
        self,
        provider: str,
        intent: SearchIntent,
        quota_remaining_ratio: float,
    ) -> str:
        """Select basic or advanced depth based on intent and budget."""
        ...
```

**Key routing rules:**
1. QUICK queries → prefer free scrapers (DuckDuckGo/Bing) when `search_prefer_free_scrapers_for_quick=True`
2. STANDARD queries → cheapest paid provider with best health score
3. DEEP queries → Tavily (advanced has better quality), with fallback to Serper
4. All tiers → auto-degrade to free scrapers when budget < 5%

### 4. Enhanced Dedup

**File:** `backend/app/domain/services/search/dedup_enhanced.py`

Two-tier dedup: fast string + Jaccard similarity.

```python
class EnhancedDedup:
    """Two-tier query deduplication.

    Tier 1: Normalized string match (existing logic, 0ms)
    Tier 2: Jaccard word similarity with threshold 0.6
            Catches "best laptop 2026" vs "top laptops this year"
    """

    def __init__(self, similarity_threshold: float = 0.6): ...

    def is_duplicate(self, query: str, session_queries: list[str]) -> bool: ...

    @staticmethod
    def jaccard_similarity(a: set[str], b: set[str]) -> float:
        """Word-level Jaccard similarity."""
        ...
```

No embedding API calls — pure word overlap. This alone catches ~60% of paraphrased duplicates at zero cost.

### 5. Configuration (Settings)

**File:** `backend/app/core/config_features.py` — additions to `SearchSettingsMixin`

```python
# --- Quota Management ---
search_quota_tavily: int = 1000
search_quota_serper: int = 2500
search_quota_brave: int = 2000
search_quota_exa: int = 1000
search_quota_jina: int = 500

# --- Credit Optimization ---
search_default_depth: str = "basic"
search_upgrade_depth_threshold: float = 0.7
search_quality_early_stop: int = 5
search_prefer_free_scrapers_for_quick: bool = True

# --- Enhanced Dedup ---
search_enhanced_dedup_enabled: bool = True
search_dedup_jaccard_threshold: float = 0.6

# --- Budget Auto-Degrade Thresholds ---
search_budget_degrade_deep_threshold: float = 0.2    # <20% → DEEP→STANDARD
search_budget_degrade_standard_threshold: float = 0.1 # <10% → STANDARD→QUICK
search_budget_degrade_scraper_threshold: float = 0.05  # <5%  → free scrapers only

# --- Feature Flag ---
search_quota_manager_enabled: bool = False  # Opt-in, zero behavior change until enabled
```

### 6. Live View Enhancement

**Backend changes:**

`backend/app/domain/services/agents/base.py`:
- Line 595: `data.results[:5]` → `data.results[:10]`
- Line 605: `data["sources"][:5]` → `data["sources"][:10]`

`backend/app/domain/models/event.py` — extend SearchToolContent:
```python
class SearchToolContent(BaseModel):
    results: list[SearchResultItem]
    provider: str | None = None       # Which provider answered
    search_depth: str | None = None   # basic/advanced
    credits_used: int | None = None   # Credits consumed
    intent_tier: str | None = None    # QUICK/STANDARD/DEEP
```

**Frontend changes:**

`frontend/src/components/toolViews/SearchContentView.vue`:
- Show provider name as subtle tag on each result
- Show search depth indicator (basic/advanced pill)
- Show credit cost for the search

`frontend/src/types/toolContent.ts`:
- Add `provider`, `search_depth`, `credits_used`, `intent_tier` fields

### 7. Tavily Depth Override

**File:** `backend/app/infrastructure/external/search/tavily_search.py`

Make `search_depth` configurable instead of hardcoded:

```python
def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
    return {
        "query": actual_query,
        "search_depth": self._search_depth,  # from settings, default "basic"
        "include_answer": True,
        ...
    }
```

Constructor accepts `search_depth` parameter, defaulting to settings value.

## File Layout

```
backend/app/
├── domain/services/search/          # NEW directory
│   ├── __init__.py
│   ├── quota_manager.py             # SearchQuotaManager singleton
│   ├── intent_classifier.py         # QueryIntentClassifier (rule-based)
│   ├── cost_router.py               # CostAwareSearchRouter
│   └── dedup_enhanced.py            # Enhanced dedup (Jaccard)
├── core/
│   └── config_features.py           # MODIFIED: add quota/routing settings
├── infrastructure/external/search/
│   └── tavily_search.py             # MODIFIED: configurable depth
├── domain/models/
│   └── event.py                     # MODIFIED: extend SearchToolContent
└── domain/services/
    ├── tools/search.py              # MODIFIED: integrate quota manager
    └── agents/base.py               # MODIFIED: bump [:5] → [:10]

frontend/src/
├── components/toolViews/
│   └── SearchContentView.vue        # MODIFIED: show provider/depth/credits
└── types/
    └── toolContent.ts               # MODIFIED: add new fields
```

**New files:** 5 (4 backend + 1 __init__)
**Modified files:** 6 (4 backend + 2 frontend)
**Estimated new code:** ~600-800 lines
**Estimated modifications:** ~100-150 lines

## Testing Strategy

1. **Unit tests** for each new component (classifier, dedup, router, quota manager)
2. **Integration test** for full route() flow with mocked providers
3. **Budget degrade test** — verify auto-downgrade at 20%/10%/5% thresholds
4. **Dedup accuracy test** — verify Jaccard catches paraphrased queries
5. **Provider rotation test** — verify cost-aware routing picks cheapest healthy provider
6. **Feature flag test** — verify zero behavior change when `search_quota_manager_enabled=False`

## Migration

1. Feature flag `search_quota_manager_enabled` defaults to `False`
2. Existing behavior is 100% unchanged until flag is enabled
3. When enabled, quota manager wraps the existing search flow
4. Existing `SearchTool._BudgetTracker` remains as inner guardrail (per-task cap)
5. Quota manager adds outer guardrail (per-month cap across providers)

## Expected Credit Savings

| Scenario | Before | After | Savings |
|----------|--------|-------|---------|
| Simple lookup | 2 credits (Tavily advanced) | 0 credits (DuckDuckGo) | 100% |
| Standard search | 2 credits (Tavily advanced) | 1 credit (cheapest provider, basic) | 50% |
| wide_research (3 queries) | 12 credits (6 calls x 2) | 3-6 credits (fewer variants, basic depth) | 50-75% |
| Duplicate search | 2 credits (re-executed) | 0 credits (dedup caught) | 100% |
| **Monthly total** | **~500 credits for typical usage** | **~150-200 credits** | **60-70%** |
