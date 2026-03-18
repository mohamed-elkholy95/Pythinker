"""Tests for unified deal_search tool — returns both deals and coupons in a single call.

Verifies:
- deal_search ToolResult.data includes 'coupons' with coupon data from the adapter
- deal_search tool description does NOT mention specific store names
  (Amazon, Walmart, Best Buy, Target, Costco)
- Empty-coupons path still serializes an empty list (not None)
- Coupon fields survive the asdict() round-trip
"""

from __future__ import annotations

import pytest

from app.domain.external.deal_finder import (
    CouponInfo,
    CouponSearchResult,
    DealComparison,
    DealResult,
)
from app.domain.services.tools.deal_scraper import DealScraperTool

# ---------------------------------------------------------------------------
# Shared stub
# ---------------------------------------------------------------------------


class StubDealFinder:
    """Configurable stub — returns whatever comparison/coupon objects are provided."""

    def __init__(
        self,
        comparison: DealComparison | None = None,
        coupon_result: CouponSearchResult | None = None,
    ) -> None:
        self._comparison = comparison or DealComparison(query="default", deals=[])
        self._coupon_result = coupon_result or CouponSearchResult(coupons=[])

    async def search_deals(
        self,
        query: str,
        stores: list[str] | None = None,
        max_results: int = 10,
        progress=None,
    ) -> DealComparison:
        return self._comparison

    async def find_coupons(
        self,
        store: str,
        product_url: str | None = None,
        progress=None,
    ) -> CouponSearchResult:
        return self._coupon_result

    async def compare_prices(
        self,
        product_urls: list[str],
        progress=None,
    ) -> DealComparison:
        return DealComparison(query="compare", deals=[])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_deal(store: str = "TestStore", price: float = 99.99) -> DealResult:
    return DealResult(
        product_name="Test Product",
        store=store,
        price=price,
        url=f"https://{store.lower()}.example.com/product",
    )


def _make_coupon(code: str = "SAVE10", store: str = "TestStore", verified: bool = True) -> CouponInfo:
    return CouponInfo(
        code=code,
        description="10% off",
        store=store,
        expiry="2026-12-31",
        verified=verified,
        source="slickdeals.net",
    )


# ---------------------------------------------------------------------------
# Tests: deal_search returns coupons
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deal_search_includes_coupons_in_result() -> None:
    """deal_search response must include 'coupons' key with coupon data."""
    coupon = _make_coupon()
    comparison = DealComparison(
        query="wireless headphones",
        deals=[_make_deal()],
        coupons_found=[coupon],
    )
    tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))

    result = await tool.deal_search("wireless headphones")

    assert result.success is True
    assert result.data is not None
    assert "coupons" in result.data
    assert len(result.data["coupons"]) == 1
    coupon_dict = result.data["coupons"][0]
    assert coupon_dict["code"] == "SAVE10"
    assert coupon_dict["description"] == "10% off"
    assert coupon_dict["verified"] is True
    assert coupon_dict["store"] == "TestStore"


@pytest.mark.asyncio
async def test_deal_search_includes_multiple_coupons() -> None:
    """deal_search serializes all coupons from the adapter, preserving order."""
    coupons = [
        _make_coupon(code="FIRST20", verified=True),
        _make_coupon(code="SECOND10", verified=False),
        _make_coupon(code="THIRD5", verified=True),
    ]
    comparison = DealComparison(
        query="laptop",
        deals=[_make_deal()],
        coupons_found=coupons,
    )
    tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))

    result = await tool.deal_search("laptop")

    assert result.success is True
    assert result.data is not None
    codes = [c["code"] for c in result.data["coupons"]]
    assert codes == ["FIRST20", "SECOND10", "THIRD5"]


@pytest.mark.asyncio
async def test_deal_search_empty_coupons_returns_empty_list() -> None:
    """When the adapter returns no coupons, 'coupons' must be an empty list, not None."""
    comparison = DealComparison(
        query="monitor",
        deals=[_make_deal()],
        coupons_found=[],
    )
    tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))

    result = await tool.deal_search("monitor")

    assert result.success is True
    assert result.data is not None
    assert "coupons" in result.data
    assert result.data["coupons"] == []


@pytest.mark.asyncio
async def test_deal_search_coupon_fields_survive_asdict_roundtrip() -> None:
    """All CouponInfo fields are present after asdict() serialization."""
    coupon = CouponInfo(
        code="HOLIDAY25",
        description="25% off holiday sale",
        store="AnyStore",
        expiry="2026-01-01",
        verified=True,
        source="retailmenot.com",
        confidence=0.9,
        item_category="physical",
        source_url="https://retailmenot.com/deal/123",
    )
    comparison = DealComparison(
        query="keyboard",
        deals=[_make_deal()],
        coupons_found=[coupon],
    )
    tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))

    result = await tool.deal_search("keyboard")

    assert result.data is not None
    serialized = result.data["coupons"][0]
    assert serialized["code"] == "HOLIDAY25"
    assert serialized["expiry"] == "2026-01-01"
    assert serialized["confidence"] == 0.9
    assert serialized["item_category"] == "physical"
    assert serialized["source_url"] == "https://retailmenot.com/deal/123"


@pytest.mark.asyncio
async def test_deal_search_has_coupon_item_category_summary() -> None:
    """deal_search response includes coupon_item_category_summary alongside deals."""
    comparison = DealComparison(
        query="software",
        deals=[_make_deal()],
        coupons_found=[
            _make_coupon(code="DIGITAL1"),
            _make_coupon(code="PHYSICAL1"),
        ],
    )
    tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))

    result = await tool.deal_search("software")

    assert result.data is not None
    assert "coupon_item_category_summary" in result.data
    summary = result.data["coupon_item_category_summary"]
    assert "digital" in summary
    assert "physical" in summary
    assert "unknown" in summary


# ---------------------------------------------------------------------------
# Tests: tool description does not list specific store names
# ---------------------------------------------------------------------------


def _get_deal_search_description() -> str:
    """Extract the description string from the deal_search tool decorator."""
    # The @tool decorator stores metadata as _tool_meta or in __doc__/func attributes.
    # We inspect the tool's registered schema via get_tools().
    stub = StubDealFinder()
    instance = DealScraperTool(deal_finder=stub)
    tools = instance.get_tools()
    deal_search_schema = next(t for t in tools if t["function"]["name"] == "deal_search")
    return deal_search_schema["function"]["description"]


def test_deal_search_description_does_not_mention_amazon() -> None:
    """Tool description must not list 'Amazon' as a specific store."""
    desc = _get_deal_search_description()
    assert "Amazon" not in desc, f"Description still mentions 'Amazon': {desc[:200]}"


def test_deal_search_description_does_not_mention_walmart() -> None:
    """Tool description must not list 'Walmart' as a specific store."""
    desc = _get_deal_search_description()
    assert "Walmart" not in desc, f"Description still mentions 'Walmart': {desc[:200]}"


def test_deal_search_description_does_not_mention_best_buy() -> None:
    """Tool description must not list 'Best Buy' as a specific store."""
    desc = _get_deal_search_description()
    assert "Best Buy" not in desc, f"Description still mentions 'Best Buy': {desc[:200]}"


def test_deal_search_description_does_not_mention_target() -> None:
    """Tool description must not list 'Target' as a specific store."""
    desc = _get_deal_search_description()
    assert "Target" not in desc, f"Description still mentions 'Target': {desc[:200]}"


def test_deal_search_description_does_not_mention_costco() -> None:
    """Tool description must not list 'Costco' as a specific store."""
    desc = _get_deal_search_description()
    assert "Costco" not in desc, f"Description still mentions 'Costco': {desc[:200]}"


def test_deal_search_description_mentions_google_shopping() -> None:
    """Updated description should reference Google Shopping as a generalized source."""
    desc = _get_deal_search_description()
    assert "Google Shopping" in desc, f"Description does not mention 'Google Shopping': {desc[:200]}"


def test_deal_search_description_mentions_all_online_stores() -> None:
    """Updated description should state it searches all online stores."""
    desc = _get_deal_search_description()
    lower = desc.lower()
    assert "all online stores" in lower or "all stores" in lower, (
        f"Description does not mention 'all online stores' or 'all stores': {desc[:200]}"
    )


def test_deal_search_description_mentions_coupon_codes() -> None:
    """Updated description should mention that coupon codes are returned."""
    desc = _get_deal_search_description()
    lower = desc.lower()
    assert "coupon" in lower, f"Description does not mention coupons: {desc[:200]}"
