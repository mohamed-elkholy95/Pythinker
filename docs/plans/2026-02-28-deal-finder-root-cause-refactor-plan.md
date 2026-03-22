# Deal Finder Empty-State UX & Regression Guard Plan

**Goal:** Now that the `ToolResult[SearchResults]` unwrap bug is fixed, add structured empty-reason metadata to the backend response and render reason-aware empty states in the frontend — so users never see a misleading generic "No deals found" when the real cause was infrastructure failure. Lock the fix with regression tests.

**Architecture:** Enrich `DealComparison` (domain dataclass) with an `empty_reason` enum field. Propagate it through `DealScraperTool` → SSE `ToolResult.data` → frontend `DealToolContent` → `DealContentView.vue`. Test both the contract boundary and the reason-classification logic.

**Tech Stack:** Python 3.11, FastAPI backend (DDD layers), Vue 3 + TypeScript frontend, pytest/pytest-asyncio.

---

## Root Cause (Completed — Already Fixed)

### Finding 1 — ToolResult Unwrap (FIXED in adapter.py)
- `_search_store()` now correctly unwraps: `tool_result.success` → `tool_result.data` → `SearchResults.results` (lines 533-541).
- `_search_community()._run_one()` correctly unwraps: `tool_result.data` → `_extract_deals_from_snippets(tool_result.data, ...)` (lines 670-672).
- `_extract_deals_from_snippets()` accepts `SearchResults | None` and reads `.results` directly (lines 191-272).

### Finding 2 — Generic Empty State (STILL PRESENT — this plan's focus)
- When `comparison.deals` is empty, `deal_scraper.py:404-414` returns `ToolResult(success=True, message="No deals found for ...")` without distinguishing *why* — genuine no-match vs all-stores-failed vs search-engine-unavailable.
- `DealContentView.vue:142-206` renders a single generic empty state with hardcoded "No deals found" title and generic suggestions regardless of failure mode.
- `DealComparison` dataclass (`domain/external/deal_finder.py:60-70`) has no `empty_reason` field — only `error: str | None` (used for fatal errors, not graduated empty outcomes).

---

## Execution Status

- Phase 1: **Not Started** — Regression tests for unwrap contract
- Phase 2: **Not Started** — Backend structured empty-reason
- Phase 3: **Not Started** — Frontend reason-aware UX
- Phase 4: **Not Started** — Verification

---

## Phase 1: Regression Tests for Contract Boundary (Priority P0)

> Lock the already-applied ToolResult unwrap fix so it can never silently regress.

### Task 1.1: Test `_search_store` correctly unwraps `ToolResult[SearchResults]`

**Files**
- Create: `backend/tests/infrastructure/external/deal_finder/test_adapter_search_contract.py`
- Create: `backend/tests/infrastructure/external/deal_finder/__init__.py` (empty, for package import)

**Implementation**
1. Create a `DealFinderAdapter` with:
   - `search_engine` mock: `search()` returns `ToolResult.ok(data=SearchResults(results=[SearchResultItem(title="Test", link="https://amazon.com/product", snippet="$199.99")]))`
   - `scraper` mock: `fetch_with_escalation()` returns `ScrapedContent(success=True, html="<span>$199.99</span>", text="...", url="...")`
2. Call `adapter._search_store("test site:amazon.com", "amazon.com", timeout=30)`.
3. Assert result is a non-empty `list[DealResult]` with `price > 0`.
4. Assert `search_engine.search` was called exactly once.

**Key mocking pattern** (matches existing project conventions):
```python
@pytest.fixture
def mock_search_engine():
    engine = AsyncMock()
    engine.search.return_value = ToolResult.ok(
        data=SearchResults(results=[
            SearchResultItem(title="Product X", link="https://amazon.com/dp/X", snippet="$199.99 deal"),
        ])
    )
    return engine

@pytest.fixture
def mock_scraper():
    scraper = AsyncMock()
    scraper.fetch_with_escalation.return_value = ScrapedContent(
        success=True,
        html='<script type="application/ld+json">{"@type":"Product","offers":{"price":199.99}}</script>',
        text="Product X $199.99",
        url="https://amazon.com/dp/X",
    )
    return scraper
```

**Command**
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/deal_finder/test_adapter_search_contract.py -v
```

### Task 1.2: Test `_search_community` correctly unwraps `ToolResult[SearchResults]`

**File:** Same test file as 1.1.

**Implementation**
1. Mock `search_engine.search()` → `ToolResult.ok(data=SearchResults(results=[SearchResultItem(title="Best deal Reddit", link="https://reddit.com/r/deals/...", snippet="found it for $149.99")]))`.
2. Enable community search via `deal_scraper_community_search=True` in settings mock.
3. Call `adapter._search_community("Product X", timeout=30)`.
4. Assert at least one `DealResult` with `source_type="community"` and `price == 149.99`.

### Task 1.3: Test `ToolResult.success=False` returns empty gracefully

**File:** Same test file as 1.1.

**Implementation**
1. Mock `search_engine.search()` → `ToolResult(success=False, message="Rate limited")`.
2. Assert `_search_store(...)` returns `[]` (not raises).
3. Assert `_search_community(...)` returns `[]` (not raises).

---

## Phase 2: Backend Structured Empty-Reason (Priority P0)

### Task 2.1: Add `empty_reason` to `DealComparison`

**File:** `backend/app/domain/external/deal_finder.py`

**Implementation**
1. Add `EmptyReason` as a `StrEnum`:
   ```python
   from enum import StrEnum

   class EmptyReason(StrEnum):
       NO_MATCHES = "no_matches"           # Searches worked, nothing matched
       ALL_STORE_FAILURES = "all_store_failures"  # Every store errored
       SEARCH_UNAVAILABLE = "search_unavailable"  # No search engine injected
   ```
2. Add field to `DealComparison`:
   ```python
   empty_reason: EmptyReason | None = None
   ```
3. Keep `error: str | None` for fatal errors (backward compat).

**Why StrEnum:** JSON-serializable natively — no custom encoder needed in `ToolResult.data`. Aligns with project pattern (e.g., `MemoryType` uses StrEnum).

### Task 2.2: Classify empty reason in `DealFinderAdapter.search_deals()`

**File:** `backend/app/infrastructure/external/deal_finder/adapter.py`

**Implementation** — At the end of `search_deals()`, before `return DealComparison(...)`:

```python
# Classify empty reason
empty_reason: EmptyReason | None = None
if not deals:
    if not self._search_engine:
        empty_reason = EmptyReason.SEARCH_UNAVAILABLE
    elif len(store_errors) == len(active_stores):
        empty_reason = EmptyReason.ALL_STORE_FAILURES
    else:
        empty_reason = EmptyReason.NO_MATCHES

return DealComparison(
    query=query,
    deals=deals,
    best_deal=best_deal,
    coupons_found=coupons[:10],
    searched_stores=searched_stores,
    store_errors=store_errors,
    community_sources_searched=community_sources_searched,
    empty_reason=empty_reason,
)
```

**Key invariant:** `empty_reason` is `None` when `deals` is non-empty. Only populated on the empty path.

### Task 2.3: Propagate `empty_reason` through `DealScraperTool`

**File:** `backend/app/domain/services/tools/deal_scraper.py`

**Implementation** — In the `deal_search` method, enrich the no-deals `ToolResult.data`:

```python
if not comparison.deals:
    return ToolResult(
        success=True,
        message=f"No deals found for '{query}' across {len(comparison.searched_stores)} stores",
        data={
            "query": query,
            "deals": [],
            "searched_stores": comparison.searched_stores,
            "store_errors": comparison.store_errors,
            "empty_reason": comparison.empty_reason.value if comparison.empty_reason else "no_matches",
            "stores_attempted": len(stores or DEFAULT_STORES),
            "stores_with_results": len(comparison.searched_stores),
        },
    )
```

**Backward compat:** `empty_reason` is a new optional key in the existing dict. Frontend ignores unknown keys.

---

## Phase 3: Frontend Reason-Aware Empty State (Priority P1)

### Task 3.1: Extend `DealToolContent` type

**File:** `frontend/src/types/toolContent.ts`

**Implementation:**
```typescript
export type DealEmptyReason = 'no_matches' | 'all_store_failures' | 'search_unavailable';

export interface DealToolContent extends ToolContentBase {
  deals: DealItem[];
  coupons: CouponItem[];
  query: string;
  best_deal_index: number | null;
  searched_stores?: string[];
  store_errors?: StoreError[];
  // New: structured empty metadata
  empty_reason?: DealEmptyReason;
  stores_attempted?: number;
  stores_with_results?: number;
}
```

### Task 3.2: Render reason-specific empty states in `DealContentView.vue`

**File:** `frontend/src/components/toolViews/DealContentView.vue`

**Implementation** — Replace the static empty state block (lines 142-206) with reason-aware rendering:

1. Add computed property:
   ```typescript
   const emptyReason = computed(() => content?.empty_reason ?? 'no_matches');
   ```

2. Replace hardcoded "No deals found" (`deal-empty-title`, line 146) with:
   ```typescript
   const emptyTitle = computed(() => {
     switch (emptyReason.value) {
       case 'all_store_failures': return 'All stores failed to respond';
       case 'search_unavailable': return 'Deal search unavailable';
       default: return 'No deals found';
     }
   });
   ```

3. Add a reason-specific subtitle below the title:
   ```typescript
   const emptySubtitle = computed(() => {
     switch (emptyReason.value) {
       case 'all_store_failures': return 'This is usually temporary — try again in a moment.';
       case 'search_unavailable': return 'The search service is not configured for this session.';
       default: return null;  // no_matches uses query display + suggestions (existing behavior)
     }
   });
   ```

4. Conditionally hide user-blame suggestions when `emptyReason !== 'no_matches'`:
   ```html
   <div v-if="emptyReason === 'no_matches'" class="empty-suggestions">
     <!-- existing suggestion list -->
   </div>
   ```

5. For `all_store_failures`, show the store error grid prominently (already exists at lines 150-169, just needs priority ordering).

6. For `search_unavailable`, show a minimal infrastructure message — no store grid, no suggestions.

**Key UX principle:** Only show "try a more specific product name" when the issue was genuinely no matches. Infrastructure failures get infrastructure-appropriate messaging.

### Task 3.3: Empty-state icon differentiation

**File:** `frontend/src/components/toolViews/DealContentView.vue`

**Implementation** — Swap the `SearchX` icon for failure states:

```typescript
import { SearchX, AlertTriangle, CloudOff } from 'lucide-vue-next';

const emptyIcon = computed(() => {
  switch (emptyReason.value) {
    case 'all_store_failures': return AlertTriangle;
    case 'search_unavailable': return CloudOff;
    default: return SearchX;
  }
});
```

Use `<component :is="emptyIcon" :size="22" />` instead of hardcoded `<SearchX>`.

---

## Phase 4: Verification (Priority P0)

### Task 4.1: Backend tests for empty-reason classification

**File:** Create `backend/tests/domain/services/tools/test_deal_scraper_empty_reason.py`

**Test cases:**
1. `test_empty_reason_no_matches` — Mock adapter returns `DealComparison(deals=[], searched_stores=["Amazon"], store_errors=[], empty_reason=EmptyReason.NO_MATCHES)`. Assert `ToolResult.data["empty_reason"] == "no_matches"`.
2. `test_empty_reason_all_store_failures` — Mock adapter returns `DealComparison(deals=[], searched_stores=[], store_errors=[{"store": "Amazon", "error": "timeout"}], empty_reason=EmptyReason.ALL_STORE_FAILURES)`. Assert `ToolResult.data["empty_reason"] == "all_store_failures"`.
3. `test_empty_reason_search_unavailable` — Construct `DealScraperTool` with `deal_finder=None`. Assert appropriate error handling.
4. `test_empty_reason_absent_when_deals_exist` — Mock adapter returns deals. Assert `"empty_reason"` not in `ToolResult.data` (or is `None`).

### Task 4.2: Backend lint + full test suite

```bash
conda activate pythinker && cd backend && ruff check . && ruff format --check .
conda activate pythinker && cd backend && pytest tests/infrastructure/external/deal_finder/test_adapter_search_contract.py tests/domain/services/tools/test_deal_scraper_empty_reason.py -v
conda activate pythinker && cd backend && pytest tests/
```

### Task 4.3: Frontend lint + type check

```bash
cd frontend && bun run lint && bun run type-check
```

### Task 4.4: Manual smoke test

1. Start a session: `"Find me the best deal on Sony WH-1000XM5 headphones"`.
2. Verify store chips animate during search and deals render correctly on completion.
3. If deals = 0 with `empty_reason=no_matches`: title says "No deals found", shows suggestions.
4. If all stores fail: title says "All stores failed to respond", shows store error chips, no user-blame suggestions.

---

## Files Changed Summary

| File | Action | Layer |
|------|--------|-------|
| `backend/app/domain/external/deal_finder.py` | Add `EmptyReason` enum + field on `DealComparison` | Domain |
| `backend/app/infrastructure/external/deal_finder/adapter.py` | Classify `empty_reason` at end of `search_deals()` | Infrastructure |
| `backend/app/domain/services/tools/deal_scraper.py` | Propagate `empty_reason` + counters in `ToolResult.data` | Domain/Tool |
| `frontend/src/types/toolContent.ts` | Add `DealEmptyReason` type + new fields on `DealToolContent` | Frontend/Types |
| `frontend/src/components/toolViews/DealContentView.vue` | Reason-aware title/subtitle/icon/suggestions | Frontend/UI |
| `backend/tests/infrastructure/external/deal_finder/test_adapter_search_contract.py` | New: 3+ regression tests | Tests |
| `backend/tests/infrastructure/external/deal_finder/__init__.py` | New: empty package init | Tests |
| `backend/tests/domain/services/tools/test_deal_scraper_empty_reason.py` | New: 4 empty-reason classification tests | Tests |

**No new dependencies. No config changes. No migration needed.**

---

## Design Decisions

1. **`StrEnum` over string literals** — Validated via Context7 Pydantic v2 docs. StrEnum serializes to plain strings in JSON, works with `dataclasses.asdict()`, and catches typos at import time. Project already uses this pattern.

2. **`empty_reason` on `DealComparison` (domain) not on `ToolResult`** — The domain dataclass knows why deals are empty (searched_stores, store_errors). The tool layer just forwards it. This keeps classification logic in the right DDD layer.

3. **Reason classification at adapter level** — `DealFinderAdapter.search_deals()` already tracks `searched_stores`, `store_errors`, `active_stores`, and `self._search_engine`. It has all signals needed for classification. No need for a separate classifier.

4. **Frontend: computed, not prop-drilled** — `emptyReason`, `emptyTitle`, `emptySubtitle`, `emptyIcon` are all `computed()` from the existing `content` prop. No new props or emits needed on `DealContentView`.

5. **No breaking changes** — `empty_reason` is optional on both backend (`None` default) and frontend (`?:` optional). Old sessions without the field render the existing "No deals found" default.
