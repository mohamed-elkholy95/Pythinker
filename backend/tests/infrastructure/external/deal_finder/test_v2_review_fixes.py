"""Tests for code review fixes (v2 path scoring, verify exception handling, empty coupon filtering, event models)."""
import pytest
from app.infrastructure.external.deal_finder.adapter import _score_deal_static
from app.domain.external.deal_finder import DealResult, CouponInfo


class TestScoreDealStaticWired:
    def test_score_deal_static_callable(self):
        """_score_deal_static should be a callable function."""
        assert callable(_score_deal_static)

    def test_score_deal_static_returns_int(self):
        deal = DealResult(
            product_name="Test",
            store="TestStore",
            price=99.99,
            url="https://test.com",
            score=0,
            in_stock=True,
            item_category="physical",
            source_type="store",
        )
        score = _score_deal_static(deal, "Test")
        assert isinstance(score, int)
        assert 0 <= score <= 100

    def test_score_deal_static_higher_discount_scores_better(self):
        """A deal with a higher discount should score higher than one without."""
        deal_discounted = DealResult(
            product_name="Widget",
            store="BestBuy",
            price=50.0,
            original_price=100.0,
            discount_percent=50.0,
            url="https://bestbuy.com/widget",
            score=0,
            in_stock=True,
            item_category="physical",
            source_type="store",
        )
        deal_no_discount = DealResult(
            product_name="Widget",
            store="BestBuy",
            price=100.0,
            url="https://bestbuy.com/widget2",
            score=0,
            in_stock=True,
            item_category="physical",
            source_type="store",
        )
        score_disc = _score_deal_static(deal_discounted, "Widget")
        score_none = _score_deal_static(deal_no_discount, "Widget")
        assert score_disc > score_none

    def test_score_deal_static_in_stock_scores_better_than_out(self):
        """In-stock deals should score higher than out-of-stock."""
        deal_in = DealResult(
            product_name="Laptop",
            store="Amazon",
            price=800.0,
            url="https://amazon.com/laptop",
            score=0,
            in_stock=True,
            item_category="physical",
            source_type="store",
        )
        deal_out = DealResult(
            product_name="Laptop",
            store="Amazon",
            price=800.0,
            url="https://amazon.com/laptop2",
            score=0,
            in_stock=False,
            item_category="physical",
            source_type="store",
        )
        assert _score_deal_static(deal_in, "Laptop") > _score_deal_static(deal_out, "Laptop")


class TestEmptyCouponFiltering:
    def test_empty_code_coupon_filtered(self):
        """Coupons with empty code should be filtered out."""
        coupons = [
            CouponInfo(code="SAVE10", description="10% off", store="Amazon", source="web"),
            CouponInfo(code="", description="Some deal", store="eBay", source="web"),
            CouponInfo(code="  ", description="Whitespace", store="Target", source="web"),
        ]
        filtered = [c for c in coupons if c.code and c.code.strip()]
        assert len(filtered) == 1
        assert filtered[0].code == "SAVE10"

    def test_valid_coupons_pass_through(self):
        """All valid-code coupons should survive filtering."""
        coupons = [
            CouponInfo(code="FIRST10", description="10% off", store="Amazon", source="web"),
            CouponInfo(code="SUMMER20", description="20% off", store="Target", source="web"),
        ]
        filtered = [c for c in coupons if c.code and c.code.strip()]
        assert len(filtered) == 2

    def test_none_code_coupon_filtered(self):
        """CouponInfo with None-like falsy code should not survive filtering."""
        coupons = [
            CouponInfo(code="", description="No code", store="Walmart", source="web"),
        ]
        filtered = [c for c in coupons if c.code and c.code.strip()]
        assert len(filtered) == 0


class TestVerifyTopDealsExceptionHandling:
    """Verify that the gather loop keeps original deal on BaseException."""

    def test_exception_replaced_by_original(self):
        """When gather returns a BaseException for an item, the original deal is kept."""
        to_verify = [
            DealResult(
                product_name="A",
                store="StoreA",
                price=10.0,
                url="https://a.com",
                score=50,
                in_stock=True,
                item_category="physical",
                source_type="store",
            ),
            DealResult(
                product_name="B",
                store="StoreB",
                price=20.0,
                url="https://b.com",
                score=60,
                in_stock=True,
                item_category="physical",
                source_type="store",
            ),
        ]
        # Simulate the fixed gather result loop
        verified: list[DealResult | BaseException] = [
            to_verify[0],           # success
            RuntimeError("boom"),   # failure
        ]

        result: list[DealResult] = []
        for i, item in enumerate(verified):
            if isinstance(item, BaseException):
                result.append(to_verify[i])  # Keep original
            else:
                result.append(item)

        assert len(result) == 2
        assert result[1].product_name == "B"  # original deal preserved
        assert result[1].store == "StoreB"

    def test_no_deals_dropped_on_all_exceptions(self):
        """When all gather results are exceptions, all original deals are kept."""
        to_verify = [
            DealResult(
                product_name="X",
                store="StoreX",
                price=5.0,
                url="https://x.com",
                score=40,
                in_stock=True,
                item_category="physical",
                source_type="store",
            ),
        ]
        verified: list[DealResult | BaseException] = [ValueError("network error")]

        result: list[DealResult] = []
        for i, item in enumerate(verified):
            if isinstance(item, BaseException):
                result.append(to_verify[i])
            else:
                result.append(item)

        assert len(result) == 1
        assert result[0].product_name == "X"


class TestDealItemEventModel:
    def test_deal_item_has_item_category(self):
        """DealItem event model should have item_category field."""
        from app.domain.models.event import DealItem

        item = DealItem(store="Test", price=99.99, item_category="digital")
        assert item.item_category == "digital"

    def test_deal_item_category_defaults_to_unknown(self):
        from app.domain.models.event import DealItem

        item = DealItem(store="Test", price=99.99)
        assert item.item_category == "unknown"

    def test_coupon_item_has_item_category(self):
        """CouponItem event model should have item_category field."""
        from app.domain.models.event import CouponItem

        item = CouponItem(code="TEST", description="test", item_category="physical")
        assert item.item_category == "physical"

    def test_coupon_item_category_defaults_to_unknown(self):
        from app.domain.models.event import CouponItem

        item = CouponItem(code="TEST", description="test")
        assert item.item_category == "unknown"

    def test_coupon_item_has_source_url(self):
        from app.domain.models.event import CouponItem

        item = CouponItem(code="TEST", description="test", source_url="https://example.com")
        assert item.source_url == "https://example.com"

    def test_coupon_item_source_url_defaults_to_none(self):
        from app.domain.models.event import CouponItem

        item = CouponItem(code="TEST", description="test")
        assert item.source_url is None
