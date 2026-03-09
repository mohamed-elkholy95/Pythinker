"""Tests for coupon empty-code filtering."""

from app.infrastructure.external.deal_finder.coupon_aggregator import (
    CouponInfo,
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

    def test_whitespace_only_code_is_without(self):
        coupons = [_make_coupon("   "), _make_coupon("  \t ")]
        with_code, without_code = _partition_coupons(coupons)
        assert len(with_code) == 0
        assert len(without_code) == 2

    def test_preserves_order(self):
        coupons = [_make_coupon("A"), _make_coupon(""), _make_coupon("B")]
        with_code, _ = _partition_coupons(coupons)
        assert [c.code for c in with_code] == ["A", "B"]
