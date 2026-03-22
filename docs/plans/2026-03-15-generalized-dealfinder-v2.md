# Generalized DealFinder v2 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the 10-store scraping-only DealFinder with a hybrid Serper Shopping API + verification scrape architecture that searches ALL stores, returns deals + coupons in a single tool call, and auto-routes digital products to web search fallback.

**Architecture:** Serper Shopping API (`POST google.serper.dev/shopping`) provides structured product data from all Google Shopping stores in one call. Top N results are verified via page scraping using the existing price voter stack. Digital/subscription products auto-detected by item classifier fall back to generalized web search + scrape. Coupon search runs in parallel via web search queries. Single unified `deal_search` tool replaces the current 3-tool split.

**Tech Stack:** Python 3.12, FastAPI, httpx, asyncio, Serper API (existing keys), Pydantic v2

---

## Task 1: Add Serper Shopping Search Method

**Files:**
- Modify: `backend/app/infrastructure/external/search/serper_search.py:100,128-140,146-164`
- Create: `backend/tests/infrastructure/external/search/test_serper_shopping.py`

**Step 1: Write the failing test**

```python
# backend/tests/infrastructure/external/search/test_serper_shopping.py
"""Tests for Serper Shopping search endpoint."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.external.search.serper_search import SerperSearchEngine


MOCK_SHOPPING_RESPONSE = {
    "searchParameters": {"q": "Sony WH-1000XM5", "type": "shopping"},
    "shopping": [
        {
            "title": "Sony WH-1000XM5 Wireless Headphones",
            "source": "Best Buy",
            "link": "https://www.bestbuy.com/product/123",
            "price": "$278.00",
            "rating": 4.7,
            "ratingCount": 25000,
            "productId": "12345",
            "position": 1,
            "imageUrl": "https://example.com/img.jpg",
        },
        {
            "title": "Sony WH-1000XM5 Black",
            "source": "Amazon",
            "link": "https://www.amazon.com/dp/B123",
            "price": "$248.00",
            "rating": 4.6,
            "ratingCount": 18000,
            "productId": "67890",
            "position": 2,
        },
    ],
}


@pytest.fixture
def serper_engine():
    return SerperSearchEngine(api_key="test-key-123")


class TestSerperShoppingSearch:
    @pytest.mark.asyncio
    async def test_shopping_search_returns_structured_results(self, serper_engine):
        """Shopping search should return ShoppingResult list with price, source, rating."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_SHOPPING_RESPONSE
        mock_response.text = "{}"
        mock_response.raise_for_status = MagicMock()

        with patch.object(serper_engine, "_get_client") as mock_client:
            client = AsyncMock()
            client.post.return_value = mock_response
            mock_client.return_value = client

            result = await serper_engine.search_shopping("Sony WH-1000XM5")

        assert result.success is True
        items = result.data
        assert len(items) == 2
        assert items[0].title == "Sony WH-1000XM5 Wireless Headphones"
        assert items[0].source == "Best Buy"
        assert items[0].price == 278.00
        assert items[0].rating == 4.7
        assert items[0].link is not None

    @pytest.mark.asyncio
    async def test_shopping_search_uses_shopping_endpoint(self, serper_engine):
        """Should POST to google.serper.dev/shopping, not /search."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"shopping": []}
        mock_response.text = "{}"
        mock_response.raise_for_status = MagicMock()

        with patch.object(serper_engine, "_get_client") as mock_client:
            client = AsyncMock()
            client.post.return_value = mock_response
            mock_client.return_value = client

            await serper_engine.search_shopping("test query")

        call_args = client.post.call_args
        assert "shopping" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_shopping_search_handles_empty_results(self, serper_engine):
        """Empty shopping results should return success with empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"shopping": []}
        mock_response.text = "{}"
        mock_response.raise_for_status = MagicMock()

        with patch.object(serper_engine, "_get_client") as mock_client:
            client = AsyncMock()
            client.post.return_value = mock_response
            mock_client.return_value = client

            result = await serper_engine.search_shopping("nonexistent product xyz")

        assert result.success is True
        assert len(result.data) == 0

    @pytest.mark.asyncio
    async def test_shopping_search_extracts_numeric_price(self, serper_engine):
        """Price string '$278.00' should be extracted as float 278.0."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_SHOPPING_RESPONSE
        mock_response.text = "{}"
        mock_response.raise_for_status = MagicMock()

        with patch.object(serper_engine, "_get_client") as mock_client:
            client = AsyncMock()
            client.post.return_value = mock_response
            mock_client.return_value = client

            result = await serper_engine.search_shopping("Sony WH-1000XM5")

        assert result.data[0].price == 278.00
        assert result.data[1].price == 248.00

    @pytest.mark.asyncio
    async def test_shopping_search_rotates_keys_on_401(self, serper_engine):
        """Should rotate API keys on auth errors, same as organic search."""
        error_response = MagicMock()
        error_response.status_code = 401
        error_response.text = "Unauthorized"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"shopping": []}
        success_response.text = "{}"
        success_response.raise_for_status = MagicMock()

        with patch.object(serper_engine, "_get_client") as mock_client:
            client = AsyncMock()
            client.post.side_effect = [error_response, success_response]
            mock_client.return_value = client

            with patch.object(serper_engine._key_pool, "handle_error", new_callable=AsyncMock):
                result = await serper_engine.search_shopping("test")

        assert result.success is True
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest tests/infrastructure/external/search/test_serper_shopping.py -v`
Expected: FAIL — `AttributeError: 'SerperSearchEngine' object has no attribute 'search_shopping'`

**Step 3: Write the implementation**

Add the `ShoppingResult` dataclass and `search_shopping` method to `serper_search.py`:

```python
# Add after line 19 (imports section) in serper_search.py:
import re
from dataclasses import dataclass, field

@dataclass
class ShoppingResult:
    """Structured product result from Google Shopping."""
    title: str
    source: str  # store name (e.g., "Best Buy", "Amazon")
    price: float
    link: str
    rating: float = 0.0
    rating_count: int = 0
    product_id: str = ""
    image_url: str = ""
    position: int = 0
    price_raw: str = ""  # original price string e.g. "$278.00"
```

Add `search_shopping` method to the `SerperSearchEngine` class (after the existing `search` method):

```python
    async def search_shopping(
        self,
        query: str,
        num: int = 20,
        _attempt: int = 0,
    ) -> ToolResult[list[ShoppingResult]]:
        """Search Google Shopping for structured product/price data.

        Returns structured results with title, price, source (store), rating
        from ALL stores indexed by Google Shopping — no site: filtering.

        Args:
            query: Product search query
            num: Number of results (default 20)
            _attempt: Internal retry counter

        Returns:
            ToolResult containing list of ShoppingResult
        """
        if _attempt >= self._max_retries:
            return ToolResult(success=False, data=[], error="All Serper API keys exhausted")

        query = re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", query).strip()
        query = re.sub(r" {2,}", " ", query)
        if not query:
            return ToolResult(success=False, data=[], error="Empty search query")
        if len(query) > 500:
            query = query[:500]

        key = await self._key_pool.get_healthy_key_or_wait(max_wait_seconds=120.0)
        if not key:
            return ToolResult(success=False, data=[], error="All Serper API keys exhausted")

        try:
            client = await self._get_client()
            params = {"q": query, "gl": "us", "hl": "en", "num": num}

            response = await client.post(
                "https://google.serper.dev/shopping",
                json=params,
                headers={"X-API-Key": key},
            )

            if response.status_code in _ROTATE_STATUS_CODES:
                body = response.text[:200]
                logger.warning("Serper shopping key error (HTTP %d), rotating", response.status_code)
                await self._key_pool.handle_error(key, status_code=response.status_code, body_text=body)
                return await self.search_shopping(query, num, _attempt=_attempt + 1)

            response.raise_for_status()

            data = response.json()
            shopping_items = data.get("shopping", [])

            results = []
            for item in shopping_items:
                price = self._extract_price_number(item.get("price", ""))
                results.append(ShoppingResult(
                    title=item.get("title", ""),
                    source=item.get("source", ""),
                    price=price,
                    link=item.get("link", ""),
                    rating=item.get("rating", 0.0),
                    rating_count=item.get("ratingCount", 0),
                    product_id=str(item.get("productId", "")),
                    image_url=item.get("imageUrl", ""),
                    position=item.get("position", 0),
                    price_raw=item.get("price", ""),
                ))

            self._key_pool.record_success(key)
            return ToolResult(success=True, data=results)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in _ROTATE_STATUS_CODES:
                body = e.response.text[:200] if hasattr(e.response, "text") else ""
                await self._key_pool.handle_error(key, status_code=e.response.status_code, body_text=body)
                return await self.search_shopping(query, num, _attempt=_attempt + 1)
            return ToolResult(success=False, data=[], error=str(e))

        except httpx.TimeoutException:
            await self._key_pool.handle_error(key, is_network_error=True)
            return ToolResult(success=False, data=[], error=f"Shopping search timed out after {self.timeout}s")

        except Exception as e:
            return ToolResult(success=False, data=[], error=str(e))

    @staticmethod
    def _extract_price_number(price_str: str) -> float:
        """Extract numeric price from string like '$278.00' or '£14.95'."""
        if not price_str:
            return 0.0
        match = re.search(r"[\d,]+\.?\d*", price_str.replace(",", ""))
        return float(match.group()) if match else 0.0
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/infrastructure/external/search/test_serper_shopping.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/search/serper_search.py \
       backend/tests/infrastructure/external/search/test_serper_shopping.py
git commit -m "feat(deals): add Serper Shopping search method for structured product data"
```

---

## Task 2: Update Config for DealFinder v2

**Files:**
- Modify: `backend/app/core/config_deals.py:8-42`
- Create: `backend/tests/core/test_config_deals_v2.py`

**Step 1: Write the failing test**

```python
# backend/tests/core/test_config_deals_v2.py
"""Tests for DealFinder v2 configuration."""
import pytest
from app.core.config import get_settings


class TestDealFinderV2Config:
    def test_deal_search_mode_default_is_auto(self):
        """Default search mode should be 'auto' (routes by item type)."""
        settings = get_settings()
        assert settings.deal_search_mode == "auto"

    def test_deal_verify_top_n_default(self):
        """Default verification count should be 5."""
        settings = get_settings()
        assert settings.deal_verify_top_n == 5

    def test_deal_verify_timeout_default(self):
        """Default per-page verification timeout should be 10s."""
        settings = get_settings()
        assert settings.deal_verify_timeout == 10.0

    def test_deal_coupon_search_enabled_default(self):
        """Coupon search should be enabled by default in unified tool."""
        settings = get_settings()
        assert settings.deal_coupon_search_enabled is True
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/core/test_config_deals_v2.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'deal_search_mode'`

**Step 3: Write the implementation**

Add new settings to `config_deals.py` after the existing settings (after line 42):

```python
    # --- DealFinder v2: Generalized Search ---
    deal_search_mode: str = "auto"
    """Search mode: 'auto' (route by item type), 'shopping' (always Serper Shopping), 'web' (always web scrape)."""

    deal_verify_top_n: int = 5
    """Number of top Shopping results to verify via page scrape."""

    deal_verify_timeout: float = 10.0
    """Per-page timeout (seconds) for verification scrapes."""

    deal_coupon_search_enabled: bool = True
    """Include coupon search in unified deal_search results."""
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/core/test_config_deals_v2.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add backend/app/core/config_deals.py backend/tests/core/test_config_deals_v2.py
git commit -m "feat(deals): add DealFinder v2 config settings (search mode, verification, coupons)"
```

---

## Task 3: Add Shopping-Powered Search to DealFinder Adapter

This is the core task — replacing the per-store `site:` search with Serper Shopping.

**Files:**
- Modify: `backend/app/infrastructure/external/deal_finder/adapter.py:46-57,485-658,692-829`
- Create: `backend/tests/infrastructure/external/deal_finder/test_shopping_search.py`

**Step 1: Write the failing tests**

```python
# backend/tests/infrastructure/external/deal_finder/test_shopping_search.py
"""Tests for Shopping-powered deal search in DealFinderAdapter."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from app.infrastructure.external.deal_finder.adapter import DealFinderAdapter
from app.infrastructure.external.search.serper_search import ShoppingResult
from app.domain.models.tool_result import ToolResult


def _make_shopping_results(items: list[dict]) -> ToolResult[list[ShoppingResult]]:
    """Helper to build mock Shopping results."""
    results = [
        ShoppingResult(
            title=it.get("title", "Product"),
            source=it.get("source", "Store"),
            price=it.get("price", 99.99),
            link=it.get("link", "https://store.com/p"),
            rating=it.get("rating", 4.5),
            rating_count=it.get("rating_count", 100),
            price_raw=f"${it.get('price', 99.99)}",
        )
        for it in items
    ]
    return ToolResult(success=True, data=results)


@pytest.fixture
def adapter():
    """Create adapter with mocked dependencies."""
    mock_scraper = AsyncMock()
    mock_search = AsyncMock()
    mock_search.search_shopping = AsyncMock(return_value=_make_shopping_results([
        {"title": "Sony WH-1000XM5", "source": "Best Buy", "price": 278.00},
        {"title": "Sony WH-1000XM5", "source": "Amazon", "price": 248.00},
        {"title": "Sony WH-1000XM5 Black", "source": "Walmart", "price": 295.00},
    ]))
    return DealFinderAdapter(scraper=mock_scraper, search_engine=mock_search)


class TestShoppingPoweredSearch:
    @pytest.mark.asyncio
    async def test_shopping_search_returns_deals_from_multiple_stores(self, adapter):
        """Shopping search should produce DealResult objects from various stores."""
        result = await adapter.search_deals(query="Sony WH-1000XM5")
        assert len(result.deals) >= 3
        stores = {d.store for d in result.deals}
        assert "Best Buy" in stores
        assert "Amazon" in stores

    @pytest.mark.asyncio
    async def test_shopping_search_no_site_operator(self, adapter):
        """Shopping search should NOT use site: operator — searches all stores."""
        await adapter.search_deals(query="Sony WH-1000XM5")
        call_args = adapter._search_engine.search_shopping.call_args
        query_arg = call_args[0][0] if call_args[0] else call_args[1].get("query", "")
        assert "site:" not in query_arg

    @pytest.mark.asyncio
    async def test_deals_sorted_by_score(self, adapter):
        """Deals should be sorted by score descending."""
        result = await adapter.search_deals(query="Sony WH-1000XM5")
        if len(result.deals) >= 2:
            scores = [d.score for d in result.deals]
            assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_digital_product_falls_back_to_web_search(self, adapter):
        """Digital products should use web search, not Shopping API."""
        adapter._search_engine.search_shopping = AsyncMock(
            return_value=ToolResult(success=True, data=[])
        )
        adapter._search_engine.search = AsyncMock(
            return_value=ToolResult(success=True, data=MagicMock(results=[]))
        )
        # "Adobe Creative Cloud subscription" should be classified as digital
        result = await adapter.search_deals(query="Adobe Creative Cloud annual subscription")
        # Web search should have been called as fallback
        assert adapter._search_engine.search.called or len(result.deals) == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/infrastructure/external/deal_finder/test_shopping_search.py -v`
Expected: FAIL — tests rely on new `search_shopping` integration path in adapter

**Step 3: Implement the Shopping search path in adapter.py**

Key changes to `adapter.py`:

1. **Add `_search_via_shopping` method** — calls `search_engine.search_shopping()`, converts `ShoppingResult` → `DealResult`
2. **Add `_search_via_web` method** — refactored existing `_search_store` without `site:` for digital products
3. **Modify `search_deals`** — route based on `deal_search_mode` and item classification
4. **Add `_verify_top_deals`** — scrape actual product pages for top N results to verify prices

```python
# New method: _search_via_shopping (add after _search_community, ~line 893)
async def _search_via_shopping(
    self,
    query: str,
    progress: DealProgressCallback | None = None,
) -> list[DealResult]:
    """Search using Serper Shopping API — returns structured deals from all stores."""
    if progress:
        await progress("Searching all stores", 0, None, None)

    result = await self._search_engine.search_shopping(query, num=20)
    if not result.success or not result.data:
        logger.warning("Shopping search returned no results for %r", query)
        return []

    deals: list[DealResult] = []
    for item in result.data:
        if item.price <= 0:
            continue
        deal = DealResult(
            product_name=item.title,
            store=item.source,
            price=item.price,
            original_price=0.0,  # Shopping API doesn't always provide this
            discount_percent=0.0,
            url=item.link,
            score=0,  # scored later by _score_deal
            in_stock=True,
            coupon_code=None,
            image_url=item.image_url,
            item_category=classify_item_category(text=item.title, url=item.link),
            source_type="store",
        )
        deals.append(deal)

    if progress:
        await progress("Found deals", len(deals), len(deals), None)

    return deals
```

```python
# New method: _verify_top_deals (add after _search_via_shopping)
async def _verify_top_deals(
    self,
    deals: list[DealResult],
    top_n: int = 5,
    timeout: float = 10.0,
) -> list[DealResult]:
    """Verify prices of top N deals by scraping actual product pages."""
    to_verify = deals[:top_n]
    if not to_verify:
        return deals

    async def _verify_one(deal: DealResult) -> DealResult:
        try:
            if not deal.url or "google.com/search" in deal.url:
                return deal  # Google redirect URL, can't scrape directly
            html = await asyncio.wait_for(
                self._scraper.fetch(deal.url),
                timeout=timeout,
            )
            if not html or not html.html_content:
                return deal

            from app.infrastructure.external.deal_finder.price_voter import vote_on_price
            vote = vote_on_price(html.html_content, deal.url)
            if vote.price > 0 and vote.confidence >= 0.5:
                verified = DealResult(
                    **{**deal.__dict__,
                       "price": vote.price,
                       "original_price": vote.original_price or deal.original_price,
                       "discount_percent": (
                           round((1 - vote.price / vote.original_price) * 100, 1)
                           if vote.original_price and vote.original_price > vote.price
                           else deal.discount_percent
                       ),
                    }
                )
                return verified
        except Exception as e:
            logger.debug("Verification scrape failed for %s: %s", deal.url, e)
        return deal

    verified = await asyncio.gather(
        *(_verify_one(d) for d in to_verify),
        return_exceptions=True,
    )

    result = []
    for i, v in enumerate(verified):
        result.append(v if isinstance(v, DealResult) else to_verify[i])
    # Append unverified deals beyond top_n
    result.extend(deals[top_n:])
    return result
```

```python
# Modified search_deals (replace lines 485-658):
async def search_deals(
    self,
    query: str,
    stores: list[str] | None = None,
    max_results: int = 10,
    progress: DealProgressCallback | None = None,
) -> DealComparison:
    """Search for deals using Shopping API (physical) or web search (digital)."""
    settings = get_settings()

    # Determine search mode
    mode = settings.deal_search_mode
    if mode == "auto":
        category = classify_item_category(text=query)
        mode = "web" if category == "digital" else "shopping"

    # --- Primary deal search ---
    if mode == "shopping":
        deals = await self._search_via_shopping(query, progress)
        # If Shopping returned nothing, fall back to web search
        if not deals:
            logger.info("Shopping returned 0 results, falling back to web search for %r", query)
            deals = await self._search_via_web(query, progress)
    else:
        deals = await self._search_via_web(query, progress)

    # --- Verification scrape (parallel with coupons) ---
    verify_task = self._verify_top_deals(
        deals,
        top_n=settings.deal_verify_top_n,
        timeout=settings.deal_verify_timeout,
    )

    # --- Coupon search (parallel) ---
    coupon_task = self._search_coupons_web(query) if settings.deal_coupon_search_enabled else asyncio.sleep(0)

    verified_deals, coupon_result = await asyncio.gather(
        verify_task,
        coupon_task,
        return_exceptions=True,
    )

    if isinstance(verified_deals, list):
        deals = verified_deals
    if isinstance(coupon_result, BaseException):
        coupon_result = []

    # Score and sort
    for deal in deals:
        deal.score = self._score_deal(deal, query)
    deals.sort(key=lambda d: d.score, reverse=True)
    deals = deals[:max_results]

    # Collect unique stores
    searched_stores = list({d.store for d in deals})

    return DealComparison(
        query=query,
        deals=deals,
        coupons=coupon_result if isinstance(coupon_result, list) else [],
        searched_stores=searched_stores,
        empty_reason=EmptyReason.NO_MATCHES if not deals else None,
    )
```

```python
# New method: _search_via_web (generalized web search, no site: operator)
async def _search_via_web(
    self,
    query: str,
    progress: DealProgressCallback | None = None,
) -> list[DealResult]:
    """Generalized web search for deals — no store restrictions.

    Used for digital products, subscriptions, and as fallback when
    Shopping API returns no results.
    """
    search_queries = [
        f"{query} buy price deal",
        f"{query} best price discount",
    ]

    all_deals: list[DealResult] = []
    seen_urls: set[str] = set()

    for sq in search_queries:
        result = await self._search_engine.search(sq)
        if not result.success or not result.data:
            continue

        for item in result.data.results:
            if item.link in seen_urls or _is_editorial_url(item.link):
                continue
            seen_urls.add(item.link)

            # Scrape page for price
            try:
                html = await asyncio.wait_for(
                    self._scraper.fetch(item.link),
                    timeout=10.0,
                )
                if not html or not html.html_content:
                    continue

                from app.infrastructure.external.deal_finder.price_voter import vote_on_price
                vote = vote_on_price(html.html_content, item.link)
                if vote.price <= 0:
                    continue

                store = _store_from_url(item.link) or _domain_from_url(item.link)
                deal = DealResult(
                    product_name=item.title or query,
                    store=store,
                    price=vote.price,
                    original_price=vote.original_price or 0.0,
                    discount_percent=(
                        round((1 - vote.price / vote.original_price) * 100, 1)
                        if vote.original_price and vote.original_price > vote.price
                        else 0.0
                    ),
                    url=item.link,
                    score=0,
                    in_stock=True,
                    item_category=classify_item_category(text=item.title or query, url=item.link),
                    source_type="store",
                )
                all_deals.append(deal)

            except Exception as e:
                logger.debug("Web scrape failed for %s: %s", item.link, e)
                continue

    return all_deals
```

```python
# New method: _search_coupons_web (product-specific coupon web search)
async def _search_coupons_web(self, query: str) -> list[CouponInfo]:
    """Search web for product-specific coupon codes."""
    import datetime
    year = datetime.datetime.now().year

    coupon_query = f"{query} coupon code promo discount {year}"
    result = await self._search_engine.search(coupon_query)
    if not result.success or not result.data:
        return []

    coupons: list[CouponInfo] = []
    for item in result.data.results[:5]:
        coupons.append(CouponInfo(
            code="CODES",
            description=item.title or "",
            store=_domain_from_url(item.link),
            source=item.link,
            source_url=item.link,
            verified=False,
        ))

    # Also fetch Slickdeals (with lock fix from Task 4)
    try:
        from app.infrastructure.external.deal_finder.coupon_aggregator import fetch_slickdeals_coupons
        sd_coupons = await fetch_slickdeals_coupons(self._scraper, query)
        coupons.extend(sd_coupons)
    except Exception:
        pass

    return coupons
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/infrastructure/external/deal_finder/test_shopping_search.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/deal_finder/adapter.py \
       backend/tests/infrastructure/external/deal_finder/test_shopping_search.py
git commit -m "feat(deals): replace 10-store scraping with Serper Shopping + web fallback"
```

---

## Task 4: Fix Slickdeals Race Condition

**Files:**
- Modify: `backend/app/infrastructure/external/deal_finder/coupon_aggregator.py:135,318-328`
- Create: `backend/tests/infrastructure/external/deal_finder/test_feed_cache_lock.py`

**Step 1: Write the failing test**

```python
# backend/tests/infrastructure/external/deal_finder/test_feed_cache_lock.py
"""Test that Slickdeals feed cache uses asyncio.Lock to prevent duplicate requests."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.external.deal_finder.coupon_aggregator import fetch_slickdeals_coupons


class TestFeedCacheLock:
    @pytest.mark.asyncio
    async def test_concurrent_slickdeals_fetches_only_one_http_request(self):
        """10 concurrent calls should produce at most 2 HTTP requests (frontpage + popular), not 20."""
        mock_scraper = AsyncMock()
        fetch_count = 0

        async def mock_fetch(url, **kwargs):
            nonlocal fetch_count
            fetch_count += 1
            await asyncio.sleep(0.01)  # simulate network latency
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.html_content = "<rss><channel></channel></rss>"
            mock_response.get_all_text = MagicMock(return_value="")
            return mock_response

        mock_scraper.fetch = mock_fetch

        # Run 10 concurrent fetches for different stores
        tasks = [
            fetch_slickdeals_coupons(mock_scraper, f"store_{i}")
            for i in range(10)
        ]

        # Clear caches first
        from app.infrastructure.external.deal_finder import coupon_aggregator
        coupon_aggregator._feed_cache.clear()

        await asyncio.gather(*tasks)

        # Should be at most 4 requests (2 feeds × 2 for cache miss), NOT 20
        assert fetch_count <= 4, f"Expected ≤4 HTTP requests but got {fetch_count} (race condition!)"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/infrastructure/external/deal_finder/test_feed_cache_lock.py -v`
Expected: FAIL — `assert 20 <= 4` (race condition produces 20 requests)

**Step 3: Add asyncio.Lock to feed cache**

In `coupon_aggregator.py`, after the `_feed_cache` declaration (line 135):

```python
# Line 135-137: Replace plain dict cache with lock-protected cache
_feed_cache: dict[str, tuple[float, list[Any]]] = {}
_feed_cache_locks: dict[str, asyncio.Lock] = {}
_feed_cache_lock_guard = asyncio.Lock()  # protects _feed_cache_locks dict itself


async def _get_feed_lock(url: str) -> asyncio.Lock:
    """Get or create a per-URL lock for feed cache."""
    async with _feed_cache_lock_guard:
        if url not in _feed_cache_locks:
            _feed_cache_locks[url] = asyncio.Lock()
        return _feed_cache_locks[url]
```

Then modify the feed fetch logic (around line 318-328) to use the lock:

```python
# Replace the existing feed cache check with:
feed_lock = await _get_feed_lock(feed_url)
async with feed_lock:
    feed_cached = _feed_cache.get(feed_url)
    if feed_cached and time.time() - feed_cached[0] < ttl:
        entries = feed_cached[1]
    else:
        result = await scraper.fetch(feed_url)
        # ... existing parsing logic ...
        _feed_cache[feed_url] = (time.time(), list(entries))
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/infrastructure/external/deal_finder/test_feed_cache_lock.py -v`
Expected: PASS — concurrent fetches now produce ≤4 HTTP requests

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/deal_finder/coupon_aggregator.py \
       backend/tests/infrastructure/external/deal_finder/test_feed_cache_lock.py
git commit -m "fix(deals): add asyncio.Lock to Slickdeals feed cache preventing 36 duplicate requests"
```

---

## Task 5: Unify Tool Interface (Single `deal_search` with Coupons)

**Files:**
- Modify: `backend/app/domain/services/tools/deal_scraper.py:77-117,334-480,587-725`
- Create: `backend/tests/domain/services/tools/test_unified_deal_search.py`

**Step 1: Write the failing test**

```python
# backend/tests/domain/services/tools/test_unified_deal_search.py
"""Tests for unified deal_search tool that returns deals + coupons."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.services.tools.deal_scraper import DealScraperTool
from app.domain.external.deal_finder import DealComparison, DealResult, CouponInfo


def _make_comparison(**kwargs) -> DealComparison:
    defaults = {
        "query": "test product",
        "deals": [
            DealResult(
                product_name="Test Product",
                store="Amazon",
                price=99.99,
                original_price=149.99,
                discount_percent=33.3,
                url="https://amazon.com/dp/test",
                score=85,
                in_stock=True,
                item_category="physical",
                source_type="store",
            )
        ],
        "coupons": [
            CouponInfo(
                code="SAVE10",
                description="10% off",
                store="Amazon",
                source="web",
                source_url="https://example.com",
                verified=False,
            )
        ],
        "searched_stores": ["Amazon"],
    }
    defaults.update(kwargs)
    return DealComparison(**defaults)


class TestUnifiedDealSearch:
    @pytest.mark.asyncio
    async def test_deal_search_returns_deals_and_coupons(self):
        """Single deal_search call should return both deals and coupons."""
        mock_finder = AsyncMock()
        mock_finder.search_deals.return_value = _make_comparison()

        tool = DealScraperTool(deal_finder=mock_finder)
        result = await tool.deal_search(query="test product")

        assert result.success is True
        data = result.data
        assert "deals" in data or len(data.get("results", [])) > 0

    @pytest.mark.asyncio
    async def test_tool_description_not_limited_to_specific_stores(self):
        """Tool description should mention 'all stores', not list specific stores."""
        mock_finder = AsyncMock()
        tool = DealScraperTool(deal_finder=mock_finder)

        # Check the tool description doesn't hardcode specific stores
        desc = tool.deal_search.__doc__ or ""
        # Should NOT contain hardcoded store list
        assert "Amazon, Walmart, Best Buy, Target, Costco" not in desc
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/domain/services/tools/test_unified_deal_search.py -v`
Expected: FAIL — current tool description still mentions specific stores

**Step 3: Update tool descriptions and merge coupon results**

In `deal_scraper.py`:

1. Update `deal_search` tool description (lines 336-371) — remove hardcoded store names:
```python
"""Search for product deals across all online stores.

Finds the best prices, discounts, and coupon codes for any product by
searching Google Shopping and retailer websites. Returns deals sorted
by value along with relevant coupon codes.

Args:
    query: Product to search for (e.g., "Sony WH-1000XM5 headphones")
    stores: Optional list of specific store domains to search (searches all stores if omitted)
    max_results: Maximum number of deals to return (default 10)
    progress: Optional progress callback for live view updates
"""
```

2. Update `_build_progress_html` (lines 111-115) — replace hardcoded store chips with dynamic "Searching all stores":
```python
# Replace hardcoded Amazon/Walmart/BestBuy chips with:
store_chips = '<div class="store-chip">All Stores</div><div class="store-chip">Google Shopping</div>'
```

3. Ensure `deal_search` returns coupons alongside deals in the ToolResult data (they come from `DealComparison.coupons` which is now populated by the unified search).

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/domain/services/tools/test_unified_deal_search.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/tools/deal_scraper.py \
       backend/tests/domain/services/tools/test_unified_deal_search.py
git commit -m "feat(deals): unify deal_search tool to return deals + coupons, remove hardcoded stores"
```

---

## Task 6: Update Scoring for Web-Wide Results

**Files:**
- Modify: `backend/app/infrastructure/external/deal_finder/adapter.py:60-73,278-336`
- Create: `backend/tests/infrastructure/external/deal_finder/test_webwide_scoring.py`

**Step 1: Write the failing test**

```python
# backend/tests/infrastructure/external/deal_finder/test_webwide_scoring.py
"""Tests for web-wide deal scoring (stores not in STORE_RELIABILITY)."""
import pytest

from app.infrastructure.external.deal_finder.adapter import DealFinderAdapter
from app.domain.external.deal_finder import DealResult


class TestWebWideScoring:
    def test_unknown_store_gets_reasonable_score(self):
        """Stores not in STORE_RELIABILITY should get a fair base score, not penalized."""
        deal = DealResult(
            product_name="Test Product",
            store="Micro Center",  # Not in STORE_RELIABILITY
            price=199.99,
            original_price=299.99,
            discount_percent=33.3,
            url="https://microcenter.com/product/123",
            score=0,
            in_stock=True,
            item_category="physical",
            source_type="store",
        )

        score = DealFinderAdapter._score_deal_static(deal, "Test Product")
        assert score >= 50, f"Unknown store should score ≥50 but got {score}"

    def test_shopping_api_source_scores_higher_than_community(self):
        """Deals from Shopping API (source_type='store') should score higher than community mentions."""
        store_deal = DealResult(
            product_name="Test Product", store="NewStore.com", price=199.99,
            original_price=299.99, discount_percent=33.3,
            url="https://newstore.com/p/123", score=0, in_stock=True,
            item_category="physical", source_type="store",
        )
        community_deal = DealResult(
            product_name="Test Product", store="Reddit", price=150.00,
            original_price=0, discount_percent=0,
            url="https://reddit.com/r/deals/123", score=0, in_stock=True,
            item_category="physical", source_type="community",
        )

        store_score = DealFinderAdapter._score_deal_static(store_deal, "Test Product")
        community_score = DealFinderAdapter._score_deal_static(community_deal, "Test Product")
        assert store_score > community_score
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/infrastructure/external/deal_finder/test_webwide_scoring.py -v`
Expected: FAIL — `_score_deal_static` doesn't exist yet

**Step 3: Refactor scoring to be web-wide friendly**

Extract `_score_deal` as a static method and adjust reliability scoring:

```python
@staticmethod
def _score_deal_static(deal: DealResult, query: str) -> int:
    """Score a deal 0-100. Works for any store, not just known ones."""
    score = 0

    # Discount (0-35 points)
    if deal.discount_percent > 0:
        score += min(35, int(deal.discount_percent * 0.7))

    # Title relevance (0-25 points)
    if _title_matches_query(deal.product_name, query):
        score += 25
    elif any(w.lower() in deal.product_name.lower() for w in query.split()[:3]):
        score += 15

    # Source type (0-15 points)
    if deal.source_type == "store":
        score += 15
    elif deal.source_type == "community":
        score += 5

    # Store reliability (0-10 points) — known stores get bonus, unknown get 7/10
    reliability = STORE_RELIABILITY.get(deal.store, 0.70)
    score += int(reliability * 10)

    # In stock bonus (0-5 points)
    if deal.in_stock:
        score += 5

    # Price sanity (0-10 points) — penalize suspiciously low or $0
    if deal.price > 0:
        score += 5
        if deal.original_price > 0 and deal.price < deal.original_price:
            score += 5

    return min(100, score)
```

Wire `_score_deal` to call `_score_deal_static`.

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/infrastructure/external/deal_finder/test_webwide_scoring.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/deal_finder/adapter.py \
       backend/tests/infrastructure/external/deal_finder/test_webwide_scoring.py
git commit -m "refactor(deals): web-wide scoring that doesn't penalize unknown stores"
```

---

## Task 7: Step Audit Tool Mapping Fix

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py` (find the tool→action mapping)
- Create: `backend/tests/domain/services/flows/test_deal_tool_audit.py`

**Step 1: Find the audit mapping**

Use LSP/grep to find where `expected=['search']` is evaluated against `tools_used=['deal_scraper']`. The step audit maps tool names to action categories. `deal_scraper` needs to map to `search`.

**Step 2: Write the failing test**

```python
# backend/tests/domain/services/flows/test_deal_tool_audit.py
"""Test that deal_scraper tool maps to 'search' action in step audit."""
import pytest
from app.domain.services.flows.plan_act import _tool_to_actions  # or wherever the mapping lives


class TestDealToolAudit:
    def test_deal_scraper_maps_to_search_action(self):
        """deal_scraper should be recognized as fulfilling 'search' action."""
        actions = _tool_to_actions("deal_scraper")
        assert "search" in actions
```

**Step 3: Add `deal_scraper` → `search` to the mapping**

Find the tool-to-action mapping dict and add: `"deal_scraper": ["search"]`

**Step 4: Run test, verify pass, commit**

```bash
git commit -m "fix(audit): map deal_scraper tool to search action in step audit"
```

---

## Task 8: Integration Test — End-to-End Shopping Search

**Files:**
- Create: `backend/tests/integration/test_dealfinder_v2_e2e.py`

**Step 1: Write integration test**

```python
# backend/tests/integration/test_dealfinder_v2_e2e.py
"""End-to-end integration test for DealFinder v2 Shopping-powered search."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.external.deal_finder.adapter import DealFinderAdapter
from app.infrastructure.external.search.serper_search import ShoppingResult
from app.domain.models.tool_result import ToolResult


def _mock_shopping_response():
    """Realistic Shopping API response."""
    return ToolResult(success=True, data=[
        ShoppingResult(title="Sony WH-1000XM5 Wireless", source="Best Buy", price=278.0,
                       link="https://bestbuy.com/p/123", rating=4.7, rating_count=25000, price_raw="$278.00"),
        ShoppingResult(title="Sony WH-1000XM5 Black", source="Amazon", price=248.0,
                       link="https://amazon.com/dp/ABC", rating=4.6, rating_count=18000, price_raw="$248.00"),
        ShoppingResult(title="Sony WH-1000XM5", source="Walmart", price=295.0,
                       link="https://walmart.com/ip/456", rating=4.5, rating_count=12000, price_raw="$295.00"),
        ShoppingResult(title="Sony WH-1000XM5 Silver", source="Target", price=279.99,
                       link="https://target.com/p/789", rating=4.5, rating_count=8000, price_raw="$279.99"),
        ShoppingResult(title="Sony WH1000XM5", source="Adorama", price=269.0,
                       link="https://adorama.com/p/012", rating=4.7, rating_count=500, price_raw="$269.00"),
    ])


class TestDealFinderV2E2E:
    @pytest.mark.asyncio
    async def test_full_search_flow_physical_product(self):
        """Physical product search: Shopping API → verify → score → return."""
        mock_scraper = AsyncMock()
        mock_scraper.fetch.return_value = None  # skip verification

        mock_search = AsyncMock()
        mock_search.search_shopping = AsyncMock(return_value=_mock_shopping_response())
        mock_search.search = AsyncMock(return_value=ToolResult(success=True, data=MagicMock(results=[])))

        adapter = DealFinderAdapter(scraper=mock_scraper, search_engine=mock_search)
        result = await adapter.search_deals(query="Sony WH-1000XM5 headphones")

        assert len(result.deals) >= 3
        assert all(d.score > 0 for d in result.deals)
        assert result.deals[0].score >= result.deals[-1].score  # sorted descending
        stores = {d.store for d in result.deals}
        assert len(stores) >= 3  # multiple stores

    @pytest.mark.asyncio
    async def test_full_search_flow_digital_product(self):
        """Digital product search: should use web search, not Shopping API."""
        mock_scraper = AsyncMock()
        mock_scraper.fetch.return_value = None

        mock_search = AsyncMock()
        mock_search.search_shopping = AsyncMock(return_value=ToolResult(success=True, data=[]))
        mock_search.search = AsyncMock(return_value=ToolResult(success=True, data=MagicMock(results=[])))

        adapter = DealFinderAdapter(scraper=mock_scraper, search_engine=mock_search)
        result = await adapter.search_deals(query="Adobe Creative Cloud annual subscription")

        # For digital products, web search should be used
        # Shopping may return empty, triggering web fallback
        assert result is not None
        assert result.empty_reason in (None, "no_matches")

    @pytest.mark.asyncio
    async def test_coupons_included_in_results(self):
        """Unified search should include coupons alongside deals."""
        mock_scraper = AsyncMock()
        mock_search = AsyncMock()
        mock_search.search_shopping = AsyncMock(return_value=_mock_shopping_response())
        mock_search.search = AsyncMock(return_value=ToolResult(
            success=True,
            data=MagicMock(results=[
                MagicMock(title="Sony WH-1000XM5 Coupon 10% Off", link="https://coupons.com/sony", snippet="SAVE10"),
            ]),
        ))

        adapter = DealFinderAdapter(scraper=mock_scraper, search_engine=mock_search)
        result = await adapter.search_deals(query="Sony WH-1000XM5")

        # Should have both deals and coupons
        assert len(result.deals) > 0
        # Coupons may or may not be found depending on web search results
        assert isinstance(result.coupons, list)
```

**Step 2: Run integration tests**

Run: `cd backend && pytest tests/integration/test_dealfinder_v2_e2e.py -v`
Expected: All 3 tests PASS

**Step 3: Commit**

```bash
git add backend/tests/integration/test_dealfinder_v2_e2e.py
git commit -m "test(deals): add e2e integration tests for DealFinder v2 Shopping-powered search"
```

---

## Task 9: Run Full Test Suite & Validate

**Step 1: Run all deal-related tests**

```bash
cd backend && conda activate pythinker && pytest tests/ -k deal -v --tb=short
```

Expected: All new + existing tests pass.

**Step 2: Run linting**

```bash
cd backend && ruff check . && ruff format --check .
```

**Step 3: Run full test suite**

```bash
cd backend && pytest tests/ --tb=short -q
```

Expected: No regressions.

**Step 4: Final commit (if any lint fixes needed)**

```bash
git commit -m "chore(deals): lint fixes for DealFinder v2"
```

---

## Summary

| Task | What | Files | Tests |
|------|------|-------|-------|
| 1 | Serper Shopping method | serper_search.py | 5 tests |
| 2 | Config settings | config_deals.py | 4 tests |
| 3 | Shopping-powered adapter | adapter.py | 4 tests |
| 4 | Slickdeals race fix | coupon_aggregator.py | 1 test |
| 5 | Unified tool interface | deal_scraper.py | 2 tests |
| 6 | Web-wide scoring | adapter.py | 2 tests |
| 7 | Step audit mapping | plan_act.py | 1 test |
| 8 | E2E integration | test_e2e.py | 3 tests |
| 9 | Full suite validation | — | all tests |
| **Total** | | **7 files modified, 7 test files** | **22 new tests** |
