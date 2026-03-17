"""Tests for DealFinder v2 configuration."""
from app.core.config import get_settings


class TestDealFinderV2Config:
    def test_deal_search_mode_default_is_auto(self):
        settings = get_settings()
        assert settings.deal_search_mode == "auto"

    def test_deal_verify_top_n_default(self):
        settings = get_settings()
        assert settings.deal_verify_top_n == 5

    def test_deal_verify_timeout_default(self):
        settings = get_settings()
        assert settings.deal_verify_timeout == 10.0

    def test_deal_coupon_search_enabled_default(self):
        settings = get_settings()
        assert settings.deal_coupon_search_enabled is True
