# Deal Finder Session Report Fixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 issues from the Deal Finder session report: SSE auth noise, search relevance, deal URL validation, markdown alert rendering, and coupon "NO CODE" filtering.

**Architecture:** Targeted surgical fixes in existing files — no new modules or abstractions. Backend changes in `adapter.py` and `coupon_aggregator.py` (Python). Frontend changes in `client.ts`, `TiptapMessageViewer.vue`, and `DealContentView.vue` (TypeScript/Vue).

**Tech Stack:** Python 3.12 (FastAPI backend), Vue 3 + TypeScript (frontend), marked (markdown), @microsoft/fetch-event-source (SSE)

---

## Task 1: SSE Auth — Reduce Console Noise & Proactive Token Refresh

**Files:**
- Modify: `frontend/src/api/client.ts:1029-1044` (proactive refresh threshold)
- Modify: `frontend/src/api/client.ts:1206-1224` (control error logging)
- Test: Manual — verify console output during SSE session

**Step 1: Widen proactive token refresh window from 5 min to 10 min**

In `frontend/src/api/client.ts`, line 1035, change:
```typescript
// BEFORE:
if (secondsUntilExpiry > 0 && secondsUntilExpiry <= 300) {

// AFTER:
if (secondsUntilExpiry > 0 && secondsUntilExpiry <= 600) {
```

And update the comment on line 1032:
```typescript
// BEFORE:
// Check if token is nearing expiry (within 5 minutes)

// AFTER:
// Check if token is nearing expiry (within 10 minutes)
```

Also update the inline comment on line 1036:
```typescript
// BEFORE:
// Token expires within 5 minutes — trigger proactive refresh

// AFTER:
// Token expires within 10 minutes — trigger proactive refresh
```

**Step 2: Downgrade SSE control error catch-block logging to debug level**

In `frontend/src/api/client.ts`, lines 1206-1224, the `ssePromise.catch` handler already silently returns for control errors. Verify no `console.warn` or `console.error` is emitted for `SSE_CONTROL_ERROR_MANUAL_RETRY`. The `logSseDiagnostics` call on line 1208 should be conditional:

```typescript
// In the ssePromise.catch block (line 1206-1235):
ssePromise.catch((err: unknown) => {
  const error = err instanceof Error ? err : new Error(String(err));

  // Control errors are expected flow — don't log as failures
  if (isSseControlError(error)) {
    return;
  }

  logSseDiagnostics('client', 'connect:promise_rejected', {
    endpoint,
    attempt,
    retryCount,
    message: error.message,
    resumeEventId: lastReceivedEventId ?? null,
  });

  if (abortController.signal.aborted) {
    return;
  }

  const scheduled = scheduleReconnect('promise_rejection', serverRetryAfterMs);
  if (scheduled) {
    return;
  }

  if (onError) {
    onError(error);
  }
  reject(error);
});
```

**Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "fix(sse): widen proactive token refresh to 10min, reduce control error noise"
```

---

## Task 2: Search Relevance — Strengthen Title Matching

**Files:**
- Modify: `backend/app/infrastructure/external/deal_finder/adapter.py:178-189`
- Test: `backend/tests/infrastructure/external/deal_finder/test_title_relevance.py` (create)

**Step 1: Write the failing tests**

Create `backend/tests/infrastructure/external/deal_finder/test_title_relevance.py`:

```python
"""Tests for deal search title relevance matching."""

from app.infrastructure.external.deal_finder.adapter import _title_matches_query


class TestTitleMatchesQuery:
    """Verify multi-signal relevance filter."""

    # ── Should MATCH ──

    def test_exact_phrase_match(self):
        """Full query as substring always passes."""
        assert _title_matches_query("Buy GLM 5 AI at Best Price", "GLM 5 AI")

    def test_majority_word_match(self):
        """>=50% query words present passes."""
        assert _title_matches_query("Sony WH-1000XM5 Headphones", "Sony WH-1000XM5 Black")

    def test_single_word_query(self):
        """Single-word queries still work."""
        assert _title_matches_query("PlayStation 5 Console", "PlayStation")

    def test_case_insensitive(self):
        """Matching is case-insensitive."""
        assert _title_matches_query("glm-5 ai model pricing", "GLM 5 AI")

    # ── Should NOT match ──

    def test_rejects_single_word_overlap_on_multiword_query(self):
        """Only 1 of 3 words matching should fail (33% < 50%)."""
        assert not _title_matches_query("Green Lipped Mussel Supplement", "GLM 5 AI")

    def test_rejects_numeric_mismatch(self):
        """Query has '5' but title has '400' — numeric token enforcement."""
        assert not _title_matches_query("Bosch GLM 400C Laser Measure", "GLM 5 AI")

    def test_rejects_completely_unrelated(self):
        """No word overlap at all."""
        assert not _title_matches_query("Organic Dog Food Premium", "GLM 5 AI")

    def test_empty_inputs(self):
        """Edge case: empty strings."""
        assert not _title_matches_query("", "GLM 5 AI")
        assert not _title_matches_query("Some Title", "")

    def test_all_stop_words_query(self):
        """Query of only stop words should fail (no meaningful words)."""
        assert not _title_matches_query("The Best Deal Ever", "the best")

    def test_numeric_token_present_in_both(self):
        """Numeric token from query present in title — passes."""
        assert _title_matches_query("GLM 5 for Developers Book", "GLM 5 AI")

    def test_numeric_token_absent_from_title(self):
        """Numeric token '5' missing from title with otherwise matching text."""
        assert not _title_matches_query("GLM AI Model Overview", "GLM 5 AI")
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && conda activate pythinker
pytest tests/infrastructure/external/deal_finder/test_title_relevance.py -v
```

Expected: Several tests fail (the reject tests pass against current implementation, but the numeric enforcement tests fail).

**Step 3: Implement the enhanced `_title_matches_query()`**

Replace lines 178-189 in `adapter.py`:

```python
def _title_matches_query(title: str, query: str) -> bool:
    """Check if a search result title is relevant to the original query.

    Multi-signal relevance filter:
    1. Exact phrase: full query as substring → always pass
    2. Numeric enforcement: if query has numbers, title must contain at least one
    3. Word overlap: >= 50% of non-stop query words must appear in title
    """
    if not title or not query:
        return False
    title_lower = title.lower()
    query_lower = query.lower()

    # Signal 1: Exact phrase match — always relevant
    if query_lower in title_lower:
        return True

    query_words = [
        w for w in re.split(r"[\s\-/]+", query_lower)
        if w and w not in _TITLE_STOP_WORDS and len(w) > 1
    ]
    if not query_words:
        return False

    # Signal 2: Numeric token enforcement
    # If the query contains numbers (e.g. "5" in "GLM 5 AI"), at least one
    # must appear in the title. Prevents "GLM 400C" matching "GLM 5".
    query_nums = [w for w in query_words if w.isdigit()]
    if query_nums and not any(num in title_lower.split() for num in query_nums):
        # Also check as substrings for compound tokens like "XM5" containing "5"
        title_tokens = re.split(r"[\s\-/,]+", title_lower)
        if not any(
            num in token for token in title_tokens for num in query_nums
        ):
            return False

    # Signal 3: Word overlap threshold — at least 50% of query words
    matched = sum(1 for word in query_words if word in title_lower)
    threshold = max(1, len(query_words) // 2)  # At least 1, at least 50%
    return matched >= threshold
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/infrastructure/external/deal_finder/test_title_relevance.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/deal_finder/adapter.py \
       backend/tests/infrastructure/external/deal_finder/test_title_relevance.py
git commit -m "fix(deals): strengthen title relevance with 50% word match + numeric enforcement"
```

---

## Task 3: Deal URL Validation — Filter Non-Commerce Pages

**Files:**
- Modify: `backend/app/infrastructure/external/deal_finder/adapter.py:646-650`
- Test: `backend/tests/infrastructure/external/deal_finder/test_url_validation.py` (create)

**Step 1: Write the failing tests**

Create `backend/tests/infrastructure/external/deal_finder/test_url_validation.py`:

```python
"""Tests for deal URL commerce validation."""

from app.infrastructure.external.deal_finder.adapter import _is_commerce_url


class TestIsCommerceUrl:
    """Verify non-commerce URLs are filtered."""

    # ── Should PASS (commerce URLs) ──

    def test_amazon_product_page(self):
        assert _is_commerce_url("https://www.amazon.com/dp/B0C1234567")

    def test_walmart_product_page(self):
        assert _is_commerce_url("https://www.walmart.com/ip/Some-Product/123456")

    def test_ebay_listing(self):
        assert _is_commerce_url("https://www.ebay.com/itm/123456789")

    def test_generic_store_page(self):
        """URLs without deny patterns pass (permissive fallback)."""
        assert _is_commerce_url("https://www.bestbuy.com/site/product/sku123")

    def test_target_product(self):
        assert _is_commerce_url("https://www.target.com/p/product-name/-/A-12345")

    # ── Should REJECT (non-commerce URLs) ──

    def test_rejects_news_article(self):
        assert not _is_commerce_url("https://www.techloy.com/news/glm-5-price-increase")

    def test_rejects_blog_post(self):
        assert not _is_commerce_url("https://example.com/blog/2026/ai-deal-roundup")

    def test_rejects_press_release(self):
        assert not _is_commerce_url("https://www.company.com/press/release/product-launch")

    def test_rejects_article_path(self):
        assert not _is_commerce_url("https://news.site.com/article/12345/ai-pricing")

    def test_rejects_review_page(self):
        assert not _is_commerce_url("https://www.pcmag.com/reviews/product-name")

    def test_rejects_wiki(self):
        assert not _is_commerce_url("https://en.wikipedia.org/wiki/GLM")

    # ── Edge cases ──

    def test_empty_url(self):
        assert not _is_commerce_url("")

    def test_no_path_url(self):
        """Root domain URL passes (could be store home)."""
        assert _is_commerce_url("https://www.amazon.com/")
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/infrastructure/external/deal_finder/test_url_validation.py -v
```

Expected: FAIL — `_is_commerce_url` doesn't exist yet.

**Step 3: Implement `_is_commerce_url()` and apply it**

Add after `_title_matches_query()` in `adapter.py` (after the new implementation from Task 2):

```python
# Paths that indicate non-commerce content (news, blogs, reviews)
_NON_COMMERCE_PATH_PATTERNS = re.compile(
    r"/(?:news|blog|press|article|articles|review|reviews|wiki|editorial|opinion|about|faq|help|support|careers)/",
    re.IGNORECASE,
)


def _is_commerce_url(url: str) -> bool:
    """Check if a URL likely points to a commerce/product page.

    Rejects URLs with news/blog/review/wiki path segments.
    Permissive fallback: URLs without deny patterns pass.
    """
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
    except Exception:
        return False

    # No path or root — allow (could be store homepage)
    if not path or path == "/":
        return True

    # Reject non-commerce path patterns
    if _NON_COMMERCE_PATH_PATTERNS.search(path):
        return False

    return True
```

Add `import urllib.parse` at the top of adapter.py if not already present.

Then modify the URL filtering at line 646:

```python
# BEFORE (line 646-650):
if url and store_domain in _domain_from_url(url):
    if _title_matches_query(item.title or "", relevance_query):
        urls_to_scrape.append((url, item.title))
    else:
        skipped_irrelevant += 1

# AFTER:
if url and store_domain in _domain_from_url(url):
    if not _is_commerce_url(url):
        skipped_irrelevant += 1
    elif _title_matches_query(item.title or "", relevance_query):
        urls_to_scrape.append((url, item.title))
    else:
        skipped_irrelevant += 1
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/infrastructure/external/deal_finder/test_url_validation.py -v
pytest tests/infrastructure/external/deal_finder/test_title_relevance.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/deal_finder/adapter.py \
       backend/tests/infrastructure/external/deal_finder/test_url_validation.py
git commit -m "fix(deals): filter non-commerce URLs (news, blog, review, wiki)"
```

---

## Task 4: Markdown Alert Rendering — Normalize Inline Alert Markers

**Files:**
- Modify: `frontend/src/components/TiptapMessageViewer.vue:112-118`
- Test: Manual — render a message containing `Caveat: > [!WARNING]`

**Step 1: Add `normalizeInlineAlerts()` function**

In `TiptapMessageViewer.vue`, add this function before the `htmlContent` computed (before line 112):

```typescript
/**
 * Normalize inline GFM alert markers so marked.js can parse them as blockquotes.
 *
 * LLMs sometimes embed alert syntax inline (e.g., "Caveat: > [!WARNING]\n> text")
 * instead of starting the blockquote at column 0. This pre-processor splits such
 * lines so the `>` marker starts its own line.
 *
 * Example:
 *   "Caveat: > [!WARNING]"  →  "Caveat:\n\n> [!WARNING]"
 */
const normalizeInlineAlerts = (markdown: string): string => {
  // Match lines where [!TYPE] appears after non-whitespace prefix text
  // e.g., "Caveat: > [!WARNING]" or "Next step: > [!NOTE]"
  return markdown.replace(
    /^(.+?)\s*>\s*(\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\])/gim,
    (_, prefix, marker) => `${prefix.replace(/[:\s]+$/, '')}\n\n> ${marker}`,
  );
};
```

**Step 2: Wire it into the htmlContent pipeline**

Modify the `htmlContent` computed (line 112-132):

```typescript
// BEFORE (line 114-117):
const normalizedMarkdown = normalizeVerificationMarkers(props.content);
const linkedMarkdown = linkifyInlineCitations(normalizedMarkdown);
// Collapse 3+ consecutive newlines to 2
const collapsed = linkedMarkdown.replace(/\n{3,}/g, '\n\n');

// AFTER:
const normalizedMarkdown = normalizeVerificationMarkers(props.content);
const alertNormalized = normalizeInlineAlerts(normalizedMarkdown);
const linkedMarkdown = linkifyInlineCitations(alertNormalized);
// Collapse 3+ consecutive newlines to 2
const collapsed = linkedMarkdown.replace(/\n{3,}/g, '\n\n');
```

**Step 3: Verify lint passes**

```bash
cd frontend && bun run lint && bun run type-check
```

**Step 4: Commit**

```bash
git add frontend/src/components/TiptapMessageViewer.vue
git commit -m "fix(ui): normalize inline GFM alert markers for proper blockquote rendering"
```

---

## Task 5: Coupon "NO CODE" Filtering — Backend + Frontend

**Files:**
- Modify: `backend/app/infrastructure/external/deal_finder/coupon_aggregator.py:699-702`
- Modify: `frontend/src/components/toolViews/DealContentView.vue:125-139,293-300`
- Test: `backend/tests/infrastructure/external/deal_finder/test_coupon_filtering.py` (create)

### Part A: Backend — Filter empty codes in aggregator

**Step 1: Write the failing test**

Create `backend/tests/infrastructure/external/deal_finder/test_coupon_filtering.py`:

```python
"""Tests for coupon empty-code filtering."""

import pytest

from app.infrastructure.external.deal_finder.coupon_aggregator import (
    CouponInfo,
    _deduplicate_coupons,
    _partition_coupons,
)


def _make_coupon(code: str = "", store: str = "Test", verified: bool = False, confidence: float = 0.5) -> CouponInfo:
    return CouponInfo(
        code=code,
        description=f"Coupon for {store}",
        store=store,
        expiry=None,
        source="test",
        verified=verified,
        confidence=confidence,
    )


class TestPartitionCoupons:
    """Verify coupons are separated into with-code and without-code."""

    def test_all_with_code(self):
        coupons = [_make_coupon("SAVE10"), _make_coupon("DEAL20")]
        with_code, without_code = _partition_coupons(coupons)
        assert len(with_code) == 2
        assert len(without_code) == 0

    def test_all_without_code(self):
        coupons = [_make_coupon(""), _make_coupon("")]
        with_code, without_code = _partition_coupons(coupons)
        assert len(with_code) == 0
        assert len(without_code) == 2

    def test_mixed(self):
        coupons = [_make_coupon("SAVE10"), _make_coupon(""), _make_coupon("DEAL20")]
        with_code, without_code = _partition_coupons(coupons)
        assert len(with_code) == 2
        assert len(without_code) == 1

    def test_backfill_when_few_codes(self):
        """When < 3 real codes, backfill from no-code coupons."""
        with_code = [_make_coupon("SAVE10")]
        without_code = [_make_coupon(""), _make_coupon(""), _make_coupon("")]
        # Backfill up to 3 total
        result = with_code + without_code[: max(0, 3 - len(with_code))]
        assert len(result) == 3

    def test_no_backfill_when_enough_codes(self):
        """When >= 3 real codes, no backfill."""
        with_code = [_make_coupon("A"), _make_coupon("B"), _make_coupon("C"), _make_coupon("D")]
        without_code = [_make_coupon("")]
        result = with_code  # No backfill needed
        assert len(result) == 4
        assert all(c.code for c in result)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/infrastructure/external/deal_finder/test_coupon_filtering.py -v
```

Expected: FAIL — `_partition_coupons` doesn't exist.

**Step 3: Add `_partition_coupons()` and wire into `aggregate_coupons()`**

In `coupon_aggregator.py`, add before `aggregate_coupons()`:

```python
def _partition_coupons(
    coupons: list[CouponInfo],
) -> tuple[list[CouponInfo], list[CouponInfo]]:
    """Split coupons into those with actual codes and those without.

    Returns (with_code, without_code) lists, each sorted by confidence descending.
    """
    with_code: list[CouponInfo] = []
    without_code: list[CouponInfo] = []
    for c in coupons:
        if c.code and c.code.strip():
            with_code.append(c)
        else:
            without_code.append(c)
    return with_code, without_code
```

Then modify the end of `aggregate_coupons()` (lines 699-702):

```python
# BEFORE:
    # Deduplicate and sort by confidence (highest first)
    deduplicated = _deduplicate_coupons(all_coupons)
    deduplicated.sort(key=lambda c: c.confidence, reverse=True)
    return deduplicated, source_failures

# AFTER:
    # Deduplicate and sort by confidence (highest first)
    deduplicated = _deduplicate_coupons(all_coupons)
    deduplicated.sort(key=lambda c: c.confidence, reverse=True)

    # Partition: prioritize coupons with actual codes
    with_code, without_code = _partition_coupons(deduplicated)
    # Backfill from no-code coupons only when very few real codes exist
    if len(with_code) < 3:
        result = with_code + without_code[: max(0, 3 - len(with_code))]
    else:
        result = with_code
    return result, source_failures
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/infrastructure/external/deal_finder/test_coupon_filtering.py -v
```

Expected: All PASS

**Step 5: Commit backend**

```bash
git add backend/app/infrastructure/external/deal_finder/coupon_aggregator.py \
       backend/tests/infrastructure/external/deal_finder/test_coupon_filtering.py
git commit -m "fix(deals): filter NO CODE coupons, prioritize real promo codes"
```

### Part B: Frontend — Show accurate count + collapse empty codes

**Step 6: Update DealContentView coupon display**

In `DealContentView.vue`, add computed properties after `sortedCoupons`:

```typescript
// Coupons with actual codes (for the count badge)
const couponsWithCode = computed(() =>
  sortedCoupons.value.filter(c => c.code && c.code.trim() && c.code !== 'NO CODE'),
);
```

Then update the coupon section header (lines 125-131) to show accurate count:

```html
<!-- BEFORE -->
<span class="coupon-count">{{ sortedCoupons.length }}</span>

<!-- AFTER -->
<span class="coupon-count">{{ couponsWithCode.length || sortedCoupons.length }}</span>
```

**Step 7: Lint check**

```bash
cd frontend && bun run lint && bun run type-check
```

**Step 8: Commit frontend**

```bash
git add frontend/src/components/toolViews/DealContentView.vue
git commit -m "fix(ui): show accurate coupon count excluding NO CODE entries"
```

---

## Task 6: Run Full Test Suite & Final Verification

**Step 1: Run all backend tests**

```bash
cd backend && conda activate pythinker
pytest tests/ -x -q 2>&1 | tail -20
```

Expected: All pass (5500+ tests)

**Step 2: Run all frontend checks**

```bash
cd frontend && bun run lint && bun run type-check
```

Expected: Clean

**Step 3: Verify new tests specifically**

```bash
cd backend
pytest tests/infrastructure/external/deal_finder/test_title_relevance.py \
       tests/infrastructure/external/deal_finder/test_coupon_filtering.py \
       tests/infrastructure/external/deal_finder/test_url_validation.py -v
```

Expected: All PASS

---

## Summary

| Task | Fix | Files | Tests |
|------|-----|-------|-------|
| 1 | SSE auth console noise + early refresh | `client.ts` | Manual |
| 2 | Title relevance 50% + numeric enforcement | `adapter.py` | 12 tests |
| 3 | Non-commerce URL filtering | `adapter.py` | 13 tests |
| 4 | Inline GFM alert normalization | `TiptapMessageViewer.vue` | Manual |
| 5 | Coupon NO CODE filtering (backend + frontend) | `coupon_aggregator.py`, `DealContentView.vue` | 5 tests |
| 6 | Full test suite verification | — | All |
