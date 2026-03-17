"""Tests for _score_deal_static — web-wide scoring that doesn't penalise unknown stores.

Ensures fair scoring when most results come from stores not in STORE_RELIABILITY.
"""

from __future__ import annotations

from app.domain.external.deal_finder import DealResult
from app.infrastructure.external.deal_finder.adapter import _score_deal_static


def _make_deal(
    *,
    product_name: str = "Test Product",
    store: str = "SomeStore",
    price: float = 50.0,
    original_price: float | None = None,
    discount_percent: float | None = None,
    in_stock: bool = True,
    source_type: str = "store",
    coupon_code: str | None = None,
) -> DealResult:
    """Construct a DealResult with sensible defaults for testing."""
    return DealResult(
        product_name=product_name,
        store=store,
        price=price,
        url="https://example.com/product",
        original_price=original_price,
        discount_percent=discount_percent,
        in_stock=in_stock,
        source_type=source_type,
        coupon_code=coupon_code,
    )


# ---------------------------------------------------------------------------
# Unknown-store fairness
# ---------------------------------------------------------------------------


def test_unknown_store_gets_reasonable_score() -> None:
    """A store not in STORE_RELIABILITY should still score >= 50."""
    deal = _make_deal(
        product_name="Sony WH-1000XM5 Headphones",
        store="BargainWorld",  # Not in STORE_RELIABILITY dict
        price=249.99,
        original_price=349.99,
        discount_percent=28.6,
        in_stock=True,
        source_type="store",
    )
    score = _score_deal_static(deal, "Sony WH-1000XM5 headphones")
    assert score >= 50, f"Unknown store should score >= 50 for a decent deal, got {score}"


def test_unknown_store_score_is_not_zero() -> None:
    """An unknown store with no discount should still get points from other signals."""
    deal = _make_deal(
        store="ObscureOutlet",
        product_name="Laptop Stand",
        price=30.0,
        in_stock=True,
        source_type="store",
    )
    score = _score_deal_static(deal, "laptop stand")
    assert score > 0, "Even a no-discount unknown-store deal should score > 0"


def test_unknown_store_reliability_contributes_7_pts() -> None:
    """Unknown stores use reliability=0.70 → int(0.70*10)=7 reliability points."""
    # Build a deal where only in_stock (5 pts) + price sanity (5 pts) + reliability
    # can contribute. No discount, source_type="open_web" (0 pts), no title match.
    deal = _make_deal(
        store="NoNameStore",
        product_name="xyzzy widget",  # Won't match query
        price=10.0,
        original_price=None,
        discount_percent=None,
        in_stock=True,
        source_type="open_web",
    )
    score = _score_deal_static(deal, "totally different query")
    assert score == 17, (
        f"Expected 17 pts (0 discount + 0 title + 0 source + 7 reliability + 5 in_stock + 5 price) "
        f"for unknown store baseline, got {score}"
    )


# ---------------------------------------------------------------------------
# Source-type ordering
# ---------------------------------------------------------------------------


def test_shopping_api_source_scores_higher_than_community() -> None:
    """source_type='store' (Shopping API) must outscore source_type='community'."""
    base_kwargs = {
        "product_name": "iPhone 15 case",
        "store": "SomeShop",
        "price": 15.0,
        "discount_percent": 20.0,
        "in_stock": True,
    }
    store_deal = _make_deal(**base_kwargs, source_type="store")
    community_deal = _make_deal(**base_kwargs, source_type="community")

    store_score = _score_deal_static(store_deal, "iPhone 15 case")
    community_score = _score_deal_static(community_deal, "iPhone 15 case")

    assert store_score > community_score, (
        f"store source ({store_score}) should outscore community source ({community_score})"
    )


def test_store_source_gets_15_pts_community_gets_5_pts() -> None:
    """Verify exact point values for source_type bonus."""
    # Isolate source_type contribution: no discount, no title match, no in_stock,
    # price=0 (no price sanity pts), same store (known: eBay=0.70 → 7 pts)
    base_kwargs = {
        "product_name": "zork",  # Won't match query
        "store": "eBay",  # int(0.70 * 10) = 7 pts
        "price": 0.0,  # No price sanity pts
        "in_stock": False,  # No in_stock pts
        "discount_percent": None,
    }
    store_deal = _make_deal(**base_kwargs, source_type="store")
    community_deal = _make_deal(**base_kwargs, source_type="community")
    open_web_deal = _make_deal(**base_kwargs, source_type="open_web")

    store_score = _score_deal_static(store_deal, "query")
    community_score = _score_deal_static(community_deal, "query")
    open_web_score = _score_deal_static(open_web_deal, "query")

    assert store_score == 22, f"store: 0+0+15+7+0+0=22, got {store_score}"
    assert community_score == 12, f"community: 0+0+5+7+0+0=12, got {community_score}"
    assert open_web_score == 7, f"open_web: 0+0+0+7+0+0=7, got {open_web_score}"


# ---------------------------------------------------------------------------
# Discount scoring
# ---------------------------------------------------------------------------


def test_high_discount_raises_score() -> None:
    """50% discount should add significantly to score."""
    low_discount = _make_deal(discount_percent=5.0, source_type="store")
    high_discount = _make_deal(discount_percent=50.0, source_type="store")

    low_score = _score_deal_static(low_discount, "test product")
    high_score = _score_deal_static(high_discount, "test product")

    assert high_score > low_score


def test_discount_capped_at_35_pts() -> None:
    """discount_percent=100 should not push discount contribution above 35."""
    deal = _make_deal(
        product_name="xyzzy",
        store="NoNameStore",
        price=0.01,
        discount_percent=100.0,
        in_stock=False,
        source_type="open_web",
    )
    score = _score_deal_static(deal, "totally different query")
    # 35 (discount capped) + 0 (title) + 0 (source) + 7 (reliability) + 0 (in_stock) + 5 (price>0) = 47
    assert score == 47, f"Expected 47 with capped discount, got {score}"


def test_zero_discount_percent_contributes_nothing() -> None:
    """discount_percent=0 should contribute 0 points."""
    deal = _make_deal(
        product_name="xyzzy",
        store="NoNameStore",
        price=10.0,
        discount_percent=0.0,
        in_stock=False,
        source_type="open_web",
    )
    score = _score_deal_static(deal, "totally different query")
    # 0 + 0 + 0 + 7 + 0 + 5 = 12
    assert score == 12


def test_none_discount_percent_contributes_nothing() -> None:
    """discount_percent=None should be treated as 0."""
    deal_none = _make_deal(
        product_name="xyzzy",
        store="NoNameStore",
        price=10.0,
        discount_percent=None,
        in_stock=False,
        source_type="open_web",
    )
    deal_zero = _make_deal(
        product_name="xyzzy",
        store="NoNameStore",
        price=10.0,
        discount_percent=0.0,
        in_stock=False,
        source_type="open_web",
    )
    assert _score_deal_static(deal_none, "totally different query") == _score_deal_static(
        deal_zero, "totally different query"
    )


# ---------------------------------------------------------------------------
# In-stock bonus
# ---------------------------------------------------------------------------


def test_in_stock_adds_5_pts() -> None:
    """in_stock=True should add exactly 5 pts over in_stock=False."""
    in_stock = _make_deal(in_stock=True, source_type="open_web", store="NoNameStore", product_name="xyzzy", price=0.0)
    out_of_stock = _make_deal(
        in_stock=False, source_type="open_web", store="NoNameStore", product_name="xyzzy", price=0.0
    )
    diff = _score_deal_static(in_stock, "query") - _score_deal_static(out_of_stock, "query")
    assert diff == 5


# ---------------------------------------------------------------------------
# Price sanity
# ---------------------------------------------------------------------------


def test_positive_price_adds_5_pts() -> None:
    """price > 0 should contribute 5 pts; price = 0 should not."""
    with_price = _make_deal(
        price=10.0, in_stock=False, source_type="open_web", store="NoNameStore", product_name="xyzzy"
    )
    no_price = _make_deal(price=0.0, in_stock=False, source_type="open_web", store="NoNameStore", product_name="xyzzy")
    diff = _score_deal_static(with_price, "query") - _score_deal_static(no_price, "query")
    assert diff == 5


def test_price_below_original_adds_extra_5_pts() -> None:
    """price < original_price should add an extra 5 pts on top of the base 5."""
    with_original = _make_deal(
        price=80.0,
        original_price=100.0,
        in_stock=False,
        source_type="open_web",
        store="NoNameStore",
        product_name="xyzzy",
    )
    no_original = _make_deal(
        price=80.0,
        original_price=None,
        in_stock=False,
        source_type="open_web",
        store="NoNameStore",
        product_name="xyzzy",
    )
    diff = _score_deal_static(with_original, "query") - _score_deal_static(no_original, "query")
    assert diff == 5


# ---------------------------------------------------------------------------
# Score ceiling
# ---------------------------------------------------------------------------


def test_score_never_exceeds_100() -> None:
    """Perfect deal across all signals should be capped at 100."""
    deal = _make_deal(
        product_name="Sony WH-1000XM5 Headphones",
        store="Amazon",  # Known high-reliability store
        price=199.99,
        original_price=349.99,
        discount_percent=42.8,
        in_stock=True,
        source_type="store",
    )
    score = _score_deal_static(deal, "Sony WH-1000XM5 headphones")
    assert score <= 100, f"Score must never exceed 100, got {score}"


# ---------------------------------------------------------------------------
# Known-store vs unknown-store comparison
# ---------------------------------------------------------------------------


def test_known_store_scores_higher_than_unknown_store_all_else_equal() -> None:
    """A known high-reliability store should outscore an unknown store, all else equal."""
    known = _make_deal(store="Amazon", product_name="Widget", price=10.0, source_type="store")
    unknown = _make_deal(store="UnknownMart", product_name="Widget", price=10.0, source_type="store")

    known_score = _score_deal_static(known, "widget")
    unknown_score = _score_deal_static(unknown, "widget")

    # Amazon: int(0.95 * 10) = 9 pts; UnknownMart: int(0.70 * 10) = 7 pts
    assert known_score > unknown_score
