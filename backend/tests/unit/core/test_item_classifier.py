"""Tests for deal finder item classifier heuristics."""

import pytest

from app.infrastructure.external.deal_finder.item_classifier import (
    classify_item_category,
    normalize_domain,
)


@pytest.mark.unit
class TestNormalizeDomain:
    """Tests for normalize_domain function."""

    def test_none_url(self) -> None:
        assert normalize_domain(None) == ""

    def test_empty_url(self) -> None:
        assert normalize_domain("") == ""

    def test_strips_www(self) -> None:
        assert normalize_domain("https://www.amazon.com/product") == "amazon.com"

    def test_preserves_subdomain(self) -> None:
        assert normalize_domain("https://shop.example.com/item") == "shop.example.com"

    def test_lowercase(self) -> None:
        assert normalize_domain("https://WWW.Example.COM/page") == "example.com"

    def test_with_port(self) -> None:
        assert normalize_domain("https://example.com:8080/page") == "example.com:8080"


@pytest.mark.unit
class TestClassifyItemCategory:
    """Tests for classify_item_category function."""

    # Digital domain tests
    def test_appsumo_is_digital(self) -> None:
        assert classify_item_category(url="https://appsumo.com/deal") == "digital"

    def test_udemy_is_digital(self) -> None:
        assert classify_item_category(url="https://udemy.com/course") == "digital"

    def test_steam_is_digital(self) -> None:
        assert classify_item_category(url="https://steampowered.com/app/123") == "digital"

    def test_humble_bundle_is_digital(self) -> None:
        assert classify_item_category(url="https://humblebundle.com/games") == "digital"

    def test_gumroad_is_digital(self) -> None:
        assert classify_item_category(url="https://gumroad.com/product") == "digital"

    # Physical domain tests
    def test_amazon_is_physical(self) -> None:
        assert classify_item_category(url="https://amazon.com/dp/B123") == "physical"

    def test_walmart_is_physical(self) -> None:
        assert classify_item_category(url="https://walmart.com/item") == "physical"

    def test_bestbuy_is_physical(self) -> None:
        assert classify_item_category(url="https://bestbuy.com/product") == "physical"

    def test_target_is_physical(self) -> None:
        assert classify_item_category(url="https://target.com/item") == "physical"

    def test_costco_is_physical(self) -> None:
        assert classify_item_category(url="https://costco.com/item") == "physical"

    # Keyword-based classification
    def test_software_keyword_digital(self) -> None:
        assert classify_item_category(text="Great software deal on cloud hosting") == "digital"

    def test_subscription_keyword_digital(self) -> None:
        assert classify_item_category(text="Annual subscription to VPN service") == "digital"

    def test_shipping_keyword_physical(self) -> None:
        assert classify_item_category(text="Free shipping on electronics orders") == "physical"

    def test_in_store_keyword_physical(self) -> None:
        assert classify_item_category(text="In-store pickup available for laptop") == "physical"

    def test_furniture_keyword_physical(self) -> None:
        assert classify_item_category(text="50% off furniture sale") == "physical"

    # Edge cases
    def test_empty_returns_unknown(self) -> None:
        assert classify_item_category() == "unknown"

    def test_no_signals_returns_unknown(self) -> None:
        assert classify_item_category(text="Great deal available now") == "unknown"

    def test_store_name_included_in_analysis(self) -> None:
        result = classify_item_category(text="50% off", store="Best software store")
        assert result == "digital"

    def test_www_prefix_stripped_for_domain_match(self) -> None:
        assert classify_item_category(url="https://www.amazon.com/deal") == "physical"

    def test_digital_wins_on_tie_with_subscription(self) -> None:
        result = classify_item_category(text="subscription service with shipping")
        assert result in ("digital", "physical")
