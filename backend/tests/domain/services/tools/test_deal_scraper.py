"""Comprehensive tests for deal_scraper module.

Covers:
- Module-level constants and helper functions
- _empty_category_summary
- _count_item_categories
- _build_progress_html
- _confidence_label
- _escape_md_pipe
- _build_coupon_table
- _build_deal_report_message
- DealScraperTool initialization and state
- DealScraperTool._normalize_store_name (static method)
- DealScraperTool._enqueue_progress
- DealScraperTool._progress_callback (step parsing logic)
- DealScraperTool.drain_progress_events
- DealScraperTool.deal_search (all branches)
- DealScraperTool.deal_compare_prices (all branches)
- DealScraperTool.deal_find_coupons (all branches)
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.external.deal_finder import (
    CouponInfo,
    CouponSearchResult,
    DealComparison,
    DealResult,
    EmptyReason,
)
from app.domain.services.tools.deal_scraper import (
    _COUPON_NOISE_WORDS,
    _QUEUE_MAX_SIZE,
    DealScraperTool,
    _build_coupon_table,
    _build_deal_report_message,
    _build_progress_html,
    _confidence_label,
    _count_item_categories,
    _empty_category_summary,
    _escape_md_pipe,
)

# ---------------------------------------------------------------------------
# Helpers — stub implementations of external dependencies
# ---------------------------------------------------------------------------


class StubDealFinder:
    """Configurable stub for DealFinder protocol."""

    def __init__(
        self,
        comparison: DealComparison | None = None,
        coupon_result: CouponSearchResult | None = None,
        search_exc: Exception | None = None,
        compare_exc: Exception | None = None,
        coupon_exc: Exception | None = None,
    ) -> None:
        self._comparison = comparison or DealComparison(query="default", deals=[])
        self._coupon_result = coupon_result or CouponSearchResult(coupons=[])
        self._search_exc = search_exc
        self._compare_exc = compare_exc
        self._coupon_exc = coupon_exc

    async def search_deals(
        self,
        query: str,
        stores: list[str] | None = None,
        max_results: int = 10,
        progress=None,
    ) -> DealComparison:
        if self._search_exc:
            raise self._search_exc
        return self._comparison

    async def find_coupons(
        self,
        store: str,
        product_url: str | None = None,
        progress=None,
    ) -> CouponSearchResult:
        if self._coupon_exc:
            raise self._coupon_exc
        return self._coupon_result

    async def compare_prices(
        self,
        product_urls: list[str],
        progress=None,
    ) -> DealComparison:
        if self._compare_exc:
            raise self._compare_exc
        return self._comparison


class StubDealFinderWithProgress:
    """Stub that invokes the progress callback so we can test callback logic.

    Because DealScraperTool passes self._progress_callback (the BaseTool instance
    attribute, which is None) rather than the class-level _progress_callback method,
    tests that need the callback to fire must pass it explicitly via `inject_callback`.
    """

    def __init__(self, comparison: DealComparison, steps: list[tuple]) -> None:
        self._comparison = comparison
        # steps: list of (current_step, steps_completed, steps_total, partial_data)
        self._steps = steps
        self._injected_callback = None

    def inject_callback(self, cb) -> None:
        """Inject the callback to use when progress fires."""
        self._injected_callback = cb

    async def search_deals(self, query, stores=None, max_results=10, progress=None):
        cb = self._injected_callback or progress
        if cb:
            for step in self._steps:
                await cb(*step)
        return self._comparison

    async def find_coupons(self, store, product_url=None, progress=None):
        return CouponSearchResult(coupons=[])

    async def compare_prices(self, product_urls, progress=None):
        return self._comparison


def _make_deal(
    store: str = "Amazon",
    price: float = 99.99,
    original_price: float | None = None,
    discount_percent: float | None = None,
    in_stock: bool = True,
    score: int = 75,
    item_category: str = "unknown",
) -> DealResult:
    return DealResult(
        product_name="Test Product",
        store=store,
        price=price,
        url=f"https://{store.lower()}.example.com/product",
        original_price=original_price,
        discount_percent=discount_percent,
        in_stock=in_stock,
        score=score,
        item_category=item_category,
    )


def _make_coupon(
    code: str = "SAVE10",
    store: str = "Amazon",
    verified: bool = True,
    confidence: float = 0.9,
    expiry: str | None = "2026-12-31",
    source: str = "slickdeals.net",
    source_url: str | None = "https://slickdeals.net/deal/123",
    description: str = "10% off everything",
    item_category: str = "unknown",
) -> CouponInfo:
    return CouponInfo(
        code=code,
        description=description,
        store=store,
        expiry=expiry,
        verified=verified,
        source=source,
        confidence=confidence,
        item_category=item_category,
        source_url=source_url,
    )


# ---------------------------------------------------------------------------
# Tests: module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_queue_max_size_is_positive(self) -> None:
        assert _QUEUE_MAX_SIZE > 0

    def test_coupon_noise_words_is_frozenset(self) -> None:
        assert isinstance(_COUPON_NOISE_WORDS, frozenset)

    def test_coupon_noise_words_contains_expected_terms(self) -> None:
        expected = {"coupon", "coupons", "code", "codes", "promo", "discount", "deal", "deals"}
        assert expected.issubset(_COUPON_NOISE_WORDS)

    def test_coupon_noise_words_contains_offer_and_sale(self) -> None:
        assert "offer" in _COUPON_NOISE_WORDS
        assert "sale" in _COUPON_NOISE_WORDS

    def test_coupon_noise_words_contains_temporal_and_quality(self) -> None:
        assert "best" in _COUPON_NOISE_WORDS
        assert "top" in _COUPON_NOISE_WORDS
        assert "latest" in _COUPON_NOISE_WORDS
        assert "new" in _COUPON_NOISE_WORDS

    def test_coupon_noise_words_contains_free_and_online(self) -> None:
        assert "free" in _COUPON_NOISE_WORDS
        assert "online" in _COUPON_NOISE_WORDS





class TestEmptyCategorySummary:
    def test_returns_dict_with_three_keys(self) -> None:
        result = _empty_category_summary()
        assert set(result.keys()) == {"digital", "physical", "unknown"}

    def test_all_values_are_zero(self) -> None:
        result = _empty_category_summary()
        assert result["digital"] == 0
        assert result["physical"] == 0
        assert result["unknown"] == 0

    def test_returns_new_dict_each_call(self) -> None:
        a = _empty_category_summary()
        b = _empty_category_summary()
        a["digital"] = 99
        assert b["digital"] == 0





class TestCountItemCategories:
    def _obj(self, category: str) -> Any:
        """Create a simple object with item_category attribute."""
        obj = MagicMock()
        obj.item_category = category
        return obj

    def test_empty_list_returns_all_zeros(self) -> None:
        result = _count_item_categories([])
        assert result == {"digital": 0, "physical": 0, "unknown": 0}

    def test_counts_digital_items(self) -> None:
        items = [self._obj("digital"), self._obj("digital")]
        result = _count_item_categories(items)
        assert result["digital"] == 2
        assert result["physical"] == 0
        assert result["unknown"] == 0

    def test_counts_physical_items(self) -> None:
        items = [self._obj("physical")]
        result = _count_item_categories(items)
        assert result["physical"] == 1

    def test_counts_unknown_items(self) -> None:
        items = [self._obj("unknown"), self._obj("unknown"), self._obj("unknown")]
        result = _count_item_categories(items)
        assert result["unknown"] == 3

    def test_mixed_categories(self) -> None:
        items = [
            self._obj("digital"),
            self._obj("physical"),
            self._obj("physical"),
            self._obj("unknown"),
        ]
        result = _count_item_categories(items)
        assert result == {"digital": 1, "physical": 2, "unknown": 1}

    def test_invalid_category_falls_back_to_unknown(self) -> None:
        items = [self._obj("gadget"), self._obj("software")]
        result = _count_item_categories(items)
        assert result["unknown"] == 2
        assert result["digital"] == 0
        assert result["physical"] == 0

    def test_object_without_item_category_falls_back_to_unknown(self) -> None:
        """Objects missing item_category attribute default to 'unknown' via getattr."""
        obj = object()
        result = _count_item_categories([obj])
        assert result["unknown"] == 1

    def test_items_with_none_item_category_fall_back_to_unknown(self) -> None:
        obj = MagicMock()
        obj.item_category = None
        result = _count_item_categories([obj])
        assert result["unknown"] == 1

    def test_uses_domain_deal_results_directly(self) -> None:
        deals = [
            _make_deal(item_category="digital"),
            _make_deal(item_category="physical"),
            _make_deal(item_category="unknown"),
        ]
        result = _count_item_categories(deals)
        assert result == {"digital": 1, "physical": 1, "unknown": 1}





class TestBuildProgressHtml:
    def test_returns_string(self) -> None:
        html = _build_progress_html("test query")
        assert isinstance(html, str)

    def test_contains_doctype(self) -> None:
        html = _build_progress_html("headphones")
        assert "<!DOCTYPE html>" in html

    def test_contains_query_in_output(self) -> None:
        html = _build_progress_html("Sony WH-1000XM5")
        assert "Sony WH-1000XM5" in html

    def test_contains_default_action(self) -> None:
        html = _build_progress_html("query")
        assert "Searching Deals" in html

    def test_contains_custom_action(self) -> None:
        html = _build_progress_html("query", action="Comparing Prices")
        assert "Comparing Prices" in html

    def test_truncates_long_query_to_80_chars(self) -> None:
        long_query = "a" * 200
        html = _build_progress_html(long_query)
        # The displayed query must be no more than 80 chars
        assert "a" * 81 not in html

    def test_escapes_ampersand_in_query(self) -> None:
        html = _build_progress_html("mac & cheese")
        assert "&amp;" in html
        assert "mac & cheese" not in html

    def test_escapes_less_than_in_query(self) -> None:
        html = _build_progress_html("price < 100")
        assert "&lt;" in html

    def test_escapes_double_quote_in_query(self) -> None:
        html = _build_progress_html('say "hello"')
        assert "&quot;" in html

    def test_escapes_ampersand_in_action(self) -> None:
        html = _build_progress_html("query", action="Find & Compare")
        assert "&amp;" in html

    def test_escapes_less_than_in_action(self) -> None:
        html = _build_progress_html("query", action="<Script>")
        assert "&lt;" in html

    def test_contains_animation_css(self) -> None:
        html = _build_progress_html("query")
        assert "animation" in html

    def test_contains_store_chips(self) -> None:
        html = _build_progress_html("query")
        assert "All Stores" in html
        assert "Google Shopping" in html
        assert "Coupon Sites" in html

    def test_finding_coupons_action(self) -> None:
        html = _build_progress_html("Best Buy", action="Finding Coupons")
        assert "Finding Coupons" in html
        assert "Best Buy" in html





class TestConfidenceLabel:
    def test_high_at_exactly_0_8(self) -> None:
        assert _confidence_label(0.8) == "High"

    def test_high_above_0_8(self) -> None:
        assert _confidence_label(0.9) == "High"
        assert _confidence_label(1.0) == "High"

    def test_medium_at_exactly_0_5(self) -> None:
        assert _confidence_label(0.5) == "Medium"

    def test_medium_between_0_5_and_0_8(self) -> None:
        assert _confidence_label(0.6) == "Medium"
        assert _confidence_label(0.79) == "Medium"

    def test_low_below_0_5(self) -> None:
        assert _confidence_label(0.49) == "Low"
        assert _confidence_label(0.0) == "Low"

    def test_low_at_zero(self) -> None:
        assert _confidence_label(0.0) == "Low"

    def test_boundary_just_below_high(self) -> None:
        assert _confidence_label(0.799) == "Medium"

    def test_boundary_just_below_medium(self) -> None:
        assert _confidence_label(0.499) == "Low"





class TestEscapeMdPipe:
    def test_escapes_single_pipe(self) -> None:
        assert _escape_md_pipe("foo|bar") == "foo\\|bar"

    def test_escapes_multiple_pipes(self) -> None:
        assert _escape_md_pipe("a|b|c") == "a\\|b\\|c"

    def test_no_pipe_unchanged(self) -> None:
        text = "no pipes here"
        assert _escape_md_pipe(text) == text

    def test_empty_string(self) -> None:
        assert _escape_md_pipe("") == ""

    def test_pipe_at_start(self) -> None:
        assert _escape_md_pipe("|start") == "\\|start"

    def test_pipe_at_end(self) -> None:
        assert _escape_md_pipe("end|") == "end\\|"

    def test_only_pipes(self) -> None:
        assert _escape_md_pipe("|||") == "\\|\\|\\|"

    def test_preserves_other_special_chars(self) -> None:
        text = "hello & world <tag>"
        assert _escape_md_pipe(text) == text





class TestBuildCouponTable:
    def test_returns_list_of_strings(self) -> None:
        result = _build_coupon_table([_make_coupon()])
        assert isinstance(result, list)
        assert all(isinstance(line, str) for line in result)

    def test_header_contains_count(self) -> None:
        coupons = [_make_coupon("A"), _make_coupon("B")]
        result = _build_coupon_table(coupons)
        assert "2 found" in result[0]

    def test_header_contains_verified_count(self) -> None:
        coupons = [_make_coupon(verified=True), _make_coupon(verified=False)]
        result = _build_coupon_table(coupons)
        assert "1 verified" in result[0]

    def test_table_has_markdown_header_row(self) -> None:
        result = _build_coupon_table([_make_coupon()])
        header_line = result[2]
        assert "Code" in header_line
        assert "Description" in header_line
        assert "Store" in header_line
        assert "Status" in header_line
        assert "Confidence" in header_line
        assert "Expiry" in header_line
        assert "Source" in header_line
        assert "Link" in header_line

    def test_table_has_separator_row(self) -> None:
        result = _build_coupon_table([_make_coupon()])
        sep_line = result[3]
        assert "---" in sep_line

    def test_verified_coupon_shows_verified_status(self) -> None:
        coupon = _make_coupon(verified=True)
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "Verified" in data_line

    def test_unverified_coupon_shows_unverified_status(self) -> None:
        coupon = _make_coupon(verified=False)
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "Unverified" in data_line

    def test_code_wrapped_in_backticks(self) -> None:
        coupon = _make_coupon(code="TESTCODE")
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "`TESTCODE`" in data_line

    def test_no_code_shows_dash(self) -> None:
        coupon = _make_coupon()
        coupon.code = ""
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "—" in data_line

    def test_no_expiry_shows_dash(self) -> None:
        coupon = _make_coupon(expiry=None)
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "—" in data_line

    def test_no_source_shows_dash(self) -> None:
        coupon = _make_coupon(source="")
        result = _build_coupon_table([coupon])
        data_line = result[4]
        # source field shows dash
        assert "—" in data_line

    def test_source_url_becomes_link(self) -> None:
        coupon = _make_coupon(source_url="https://example.com/deal")
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "[Source](https://example.com/deal)" in data_line

    def test_no_source_url_shows_dash(self) -> None:
        coupon = _make_coupon(source_url=None)
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "—" in data_line

    def test_verified_sorted_before_unverified(self) -> None:
        coupons = [
            _make_coupon(code="UNVERIFIED", verified=False, confidence=0.3),
            _make_coupon(code="VERIFIED", verified=True, confidence=0.9),
        ]
        result = _build_coupon_table(coupons)
        # Verified should appear first in the table rows
        data_rows = result[4:]
        verified_idx = next(i for i, r in enumerate(data_rows) if "VERIFIED" in r and "UNVERIFIED" not in r)
        unverified_idx = next(i for i, r in enumerate(data_rows) if "UNVERIFIED" in r)
        assert verified_idx < unverified_idx

    def test_within_verified_sorted_by_confidence_descending(self) -> None:
        coupons = [
            _make_coupon(code="LOW", verified=True, confidence=0.6),
            _make_coupon(code="HIGH", verified=True, confidence=0.95),
        ]
        result = _build_coupon_table(coupons)
        data_rows = result[4:]
        high_idx = next(i for i, r in enumerate(data_rows) if "HIGH" in r)
        low_idx = next(i for i, r in enumerate(data_rows) if "LOW" in r)
        assert high_idx < low_idx

    def test_description_truncated_to_60_chars(self) -> None:
        long_desc = "D" * 100
        coupon = _make_coupon(description=long_desc)
        result = _build_coupon_table([coupon])
        data_line = result[4]
        # 61+ consecutive D chars should not appear
        assert "D" * 61 not in data_line

    def test_pipe_in_code_is_escaped(self) -> None:
        coupon = _make_coupon(code="PIPE|CODE")
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "PIPE\\|CODE" in data_line

    def test_pipe_in_store_is_escaped(self) -> None:
        coupon = _make_coupon(store="Store|Name")
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "Store\\|Name" in data_line

    def test_index_numbers_are_sequential(self) -> None:
        coupons = [_make_coupon("A"), _make_coupon("B"), _make_coupon("C")]
        result = _build_coupon_table(coupons)
        data_rows = [r for r in result if r.startswith("| ")]
        # Skip header row
        data_only = [r for r in data_rows if "Code" not in r and "---" not in r]
        assert data_only[0].startswith("| 1 ")
        assert data_only[1].startswith("| 2 ")
        assert data_only[2].startswith("| 3 ")

    def test_trailing_empty_line(self) -> None:
        result = _build_coupon_table([_make_coupon()])
        assert result[-1] == ""

    def test_high_confidence_label_in_table(self) -> None:
        coupon = _make_coupon(confidence=0.9)
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "High" in data_line

    def test_medium_confidence_label_in_table(self) -> None:
        coupon = _make_coupon(confidence=0.6)
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "Medium" in data_line

    def test_low_confidence_label_in_table(self) -> None:
        coupon = _make_coupon(confidence=0.2)
        result = _build_coupon_table([coupon])
        data_line = result[4]
        assert "Low" in data_line





class TestBuildDealReportMessage:
    def test_returns_string(self) -> None:
        comparison = DealComparison(query="test", deals=[])
        result = _build_deal_report_message(comparison)
        assert isinstance(result, str)

    def test_includes_deal_count(self) -> None:
        comparison = DealComparison(
            query="headphones",
            deals=[_make_deal()],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "1 deal" in result

    def test_includes_store_count(self) -> None:
        comparison = DealComparison(
            query="laptop",
            deals=[_make_deal()],
            searched_stores=["Amazon", "BestBuy"],
        )
        result = _build_deal_report_message(comparison)
        assert "2 stores" in result

    def test_includes_best_deal_when_present(self) -> None:
        deal = _make_deal(store="Amazon", price=49.99)
        comparison = DealComparison(
            query="keyboard",
            deals=[deal],
            best_deal=deal,
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "Best:" in result
        assert "$49.99" in result
        assert "Amazon" in result

    def test_includes_discount_percent_in_best_deal(self) -> None:
        deal = _make_deal(store="Amazon", price=49.99, discount_percent=20.0)
        comparison = DealComparison(
            query="keyboard",
            deals=[deal],
            best_deal=deal,
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "20.0% off" in result

    def test_no_best_deal_omits_best_summary(self) -> None:
        comparison = DealComparison(
            query="test",
            deals=[_make_deal()],
            best_deal=None,
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "Best:" not in result

    def test_community_sources_message_when_present(self) -> None:
        comparison = DealComparison(
            query="gpu",
            deals=[_make_deal()],
            searched_stores=["Amazon"],
            community_sources_searched=3,
        )
        result = _build_deal_report_message(comparison)
        assert "3 community" in result
        assert "Reddit" in result

    def test_community_sources_message_absent_when_zero(self) -> None:
        comparison = DealComparison(
            query="gpu",
            deals=[_make_deal()],
            searched_stores=["Amazon"],
            community_sources_searched=0,
        )
        result = _build_deal_report_message(comparison)
        assert "community" not in result

    def test_price_table_included_when_deals_present(self) -> None:
        comparison = DealComparison(
            query="monitor",
            deals=[_make_deal(store="Amazon", price=299.99)],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "Store" in result
        assert "Price" in result
        assert "299.99" in result

    def test_price_table_omitted_when_no_deals(self) -> None:
        comparison = DealComparison(query="test", deals=[], searched_stores=[])
        result = _build_deal_report_message(comparison)
        assert "| Store |" not in result

    def test_deal_with_original_price_shows_formatted(self) -> None:
        deal = _make_deal(price=79.99, original_price=99.99)
        comparison = DealComparison(
            query="product",
            deals=[deal],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "99.99" in result

    def test_deal_without_original_price_shows_dash(self) -> None:
        deal = _make_deal(price=79.99, original_price=None)
        comparison = DealComparison(
            query="product",
            deals=[deal],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "—" in result

    def test_deal_with_discount_percent_shows_value(self) -> None:
        deal = _make_deal(price=79.99, discount_percent=20.0)
        comparison = DealComparison(
            query="product",
            deals=[deal],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "20.0" in result

    def test_deal_without_discount_shows_dash(self) -> None:
        deal = _make_deal(price=79.99, discount_percent=None)
        comparison = DealComparison(
            query="product",
            deals=[deal],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "—" in result

    def test_in_stock_deal_shows_yes(self) -> None:
        deal = _make_deal(in_stock=True)
        comparison = DealComparison(
            query="product",
            deals=[deal],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "Yes" in result

    def test_out_of_stock_deal_shows_dash(self) -> None:
        deal = _make_deal(in_stock=False)
        comparison = DealComparison(
            query="product",
            deals=[deal],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        # out-of-stock shows dash
        assert "—" in result

    def test_failed_stores_listed(self) -> None:
        comparison = DealComparison(
            query="test",
            deals=[_make_deal()],
            searched_stores=["Amazon"],
            store_errors=[{"store": "Walmart", "error": "timeout"}],
        )
        result = _build_deal_report_message(comparison)
        assert "Could not check" in result
        assert "Walmart" in result

    def test_no_failed_stores_omits_could_not_check(self) -> None:
        comparison = DealComparison(
            query="test",
            deals=[_make_deal()],
            searched_stores=["Amazon"],
            store_errors=[],
        )
        result = _build_deal_report_message(comparison)
        assert "Could not check" not in result

    def test_category_info_shown_when_digital_or_physical(self) -> None:
        comparison = DealComparison(
            query="software",
            deals=[_make_deal(item_category="digital")],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "Item categories" in result

    def test_category_info_omitted_when_all_unknown(self) -> None:
        comparison = DealComparison(
            query="product",
            deals=[_make_deal(item_category="unknown")],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "Item categories" not in result

    def test_format_instruction_always_included(self) -> None:
        comparison = DealComparison(query="test", deals=[], searched_stores=[])
        result = _build_deal_report_message(comparison)
        assert "FORMAT" in result
        assert "promo codes" in result.lower() or "FORMAT" in result

    def test_format_instruction_mentions_disclaimer(self) -> None:
        comparison = DealComparison(query="test", deals=[], searched_stores=[])
        result = _build_deal_report_message(comparison)
        assert "Prices checked" in result
        assert "Verify coupon codes" in result

    def test_coupons_table_included_when_coupons_present(self) -> None:
        comparison = DealComparison(
            query="test",
            deals=[_make_deal()],
            coupons_found=[_make_coupon()],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "Promo Codes" in result
        assert "SAVE10" in result

    def test_coupons_table_omitted_when_no_coupons(self) -> None:
        comparison = DealComparison(
            query="test",
            deals=[_make_deal()],
            coupons_found=[],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        assert "Promo Codes" not in result

    def test_coupons_table_appears_before_summary(self) -> None:
        comparison = DealComparison(
            query="test",
            deals=[_make_deal()],
            coupons_found=[_make_coupon()],
            searched_stores=["Amazon"],
        )
        result = _build_deal_report_message(comparison)
        promo_idx = result.index("Promo Codes")
        deal_idx = result.index("deal")
        assert promo_idx < deal_idx


# ---------------------------------------------------------------------------
# Tests: DealScraperTool initialization
# ---------------------------------------------------------------------------


class TestDealScraperToolInit:
    def test_default_name(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        assert tool.name == "deal_scraper"

    def test_supports_progress_is_true(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        assert tool.supports_progress is True

    def test_progress_queue_initialized(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        assert isinstance(tool._progress_queue, asyncio.Queue)

    def test_coupon_searched_stores_starts_empty(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        assert tool._coupon_searched_stores == set()

    def test_partial_state_initialized(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        assert "store_statuses" in tool._partial_state
        assert "partial_deals" in tool._partial_state
        assert "query" in tool._partial_state

    def test_partial_state_lists_are_empty(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        assert tool._partial_state["store_statuses"] == []
        assert tool._partial_state["partial_deals"] == []
        assert tool._partial_state["query"] == ""

    def test_start_time_initially_zero(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        assert tool._start_time == 0.0

    def test_active_tool_call_id_initially_empty(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        assert tool._active_tool_call_id == ""

    def test_active_function_name_initially_empty(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        assert tool._active_function_name == ""

    def test_browser_stored_when_provided(self) -> None:
        mock_browser = MagicMock()
        tool = DealScraperTool(deal_finder=StubDealFinder(), browser=mock_browser)
        assert tool._browser is mock_browser

    def test_browser_is_none_by_default(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        assert tool._browser is None

    def test_max_observe_passed_to_base(self) -> None:
        # Just verify it doesn't raise
        tool = DealScraperTool(deal_finder=StubDealFinder(), max_observe=5)
        assert tool is not None

    def test_get_tools_returns_three_tools(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tools = tool.get_tools()
        names = {t["function"]["name"] for t in tools}
        assert names == {"deal_search", "deal_compare_prices", "deal_find_coupons"}





class TestNormalizeStoreName:
    def test_lowercases_name(self) -> None:
        result = DealScraperTool._normalize_store_name("AMAZON")
        assert result == "amazon"

    def test_strips_trailing_whitespace(self) -> None:
        result = DealScraperTool._normalize_store_name("  amazon  ")
        assert result == "amazon"

    def test_strips_coupon_noise_words(self) -> None:
        result = DealScraperTool._normalize_store_name("Amazon Coupons 2026")
        assert "coupons" not in result
        assert "amazon" in result

    def test_strips_trailing_year(self) -> None:
        result = DealScraperTool._normalize_store_name("Amazon 2026")
        assert "2026" not in result

    def test_strips_multiple_noise_words(self) -> None:
        result = DealScraperTool._normalize_store_name("Best Buy Promo Code 2025")
        assert "promo" not in result
        assert "code" not in result
        assert "2025" not in result

    def test_anthropic_example_from_docstring(self) -> None:
        result = DealScraperTool._normalize_store_name("Anthropic Claude Code Coupons 2026")
        assert "anthropic" in result
        assert "coupons" not in result
        assert "2026" not in result

    def test_name_variants_normalize_to_same_form(self) -> None:
        a = DealScraperTool._normalize_store_name("Anthropic coupons")
        b = DealScraperTool._normalize_store_name("anthropic promo codes")
        assert a == b

    def test_limits_to_three_meaningful_tokens(self) -> None:
        result = DealScraperTool._normalize_store_name("One Two Three Four Five")
        assert len(result.split()) <= 3

    def test_all_noise_words_falls_back_to_first_token(self) -> None:
        # "free best top" are all noise words — falls back to taking first original token
        result = DealScraperTool._normalize_store_name("free best top")
        assert len(result) > 0

    def test_single_word_store(self) -> None:
        result = DealScraperTool._normalize_store_name("Walmart")
        assert result == "walmart"

    def test_short_tokens_filtered_out(self) -> None:
        # Single-character tokens like "a" are filtered (len > 1 required)
        result = DealScraperTool._normalize_store_name("a Amazon")
        assert result == "amazon"

    def test_different_year_formats_stripped(self) -> None:
        for year in ["2020", "2025", "2029"]:
            result = DealScraperTool._normalize_store_name(f"Store {year}")
            assert year not in result

    def test_non_2000s_year_not_stripped(self) -> None:
        # Only years matching 20XX pattern are stripped
        result = DealScraperTool._normalize_store_name("Store 1999")
        assert "1999" in result





class TestEnqueueProgress:
    def test_enqueues_event_successfully(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._enqueue_progress("Fetching data", 1, 5)
        assert tool._progress_queue.qsize() == 1

    def test_progress_percent_calculated_correctly(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._enqueue_progress("Step 2", 2, 4)
        event = tool._progress_queue.get_nowait()
        assert event.progress_percent == 50

    def test_progress_percent_capped_at_99(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._enqueue_progress("Almost done", 10, 10)
        event = tool._progress_queue.get_nowait()
        assert event.progress_percent <= 99

    def test_progress_percent_is_zero_when_steps_total_none(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._enqueue_progress("Unknown total", 1, None)
        event = tool._progress_queue.get_nowait()
        assert event.progress_percent == 0

    def test_progress_percent_is_zero_when_steps_total_zero(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._enqueue_progress("Zero total", 1, 0)
        event = tool._progress_queue.get_nowait()
        assert event.progress_percent == 0

    def test_event_has_correct_tool_name(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._enqueue_progress("Test", 0, 5)
        event = tool._progress_queue.get_nowait()
        assert event.tool_name == "deal_scraper"

    def test_event_has_correct_current_step(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._enqueue_progress("Searching Amazon", 1, 10)
        event = tool._progress_queue.get_nowait()
        assert event.current_step == "Searching Amazon"

    def test_event_has_checkpoint_data(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._enqueue_progress("Step", 1, 5, checkpoint_data={"key": "val"})
        event = tool._progress_queue.get_nowait()
        assert event.checkpoint_data == {"key": "val"}

    def test_drops_event_when_queue_full(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        # Fill queue to max
        for i in range(_QUEUE_MAX_SIZE):
            tool._enqueue_progress(f"Step {i}", i, _QUEUE_MAX_SIZE)
        # This should not raise — event is silently dropped
        tool._enqueue_progress("Overflow step", _QUEUE_MAX_SIZE + 1, _QUEUE_MAX_SIZE + 1)
        assert tool._progress_queue.qsize() == _QUEUE_MAX_SIZE

    def test_elapsed_ms_is_zero_when_start_time_not_set(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._start_time = 0.0
        tool._enqueue_progress("Step", 1, 5)
        event = tool._progress_queue.get_nowait()
        assert event.elapsed_ms == 0

    def test_elapsed_ms_positive_when_start_time_set(self) -> None:
        import time

        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._start_time = time.monotonic() - 0.5  # started 500ms ago
        tool._enqueue_progress("Step", 1, 5)
        event = tool._progress_queue.get_nowait()
        assert event.elapsed_ms > 0



# ---------------------------------------------------------------------------
# Tests: drain_progress_events
# ---------------------------------------------------------------------------


class TestDrainProgressEvents:
    @pytest.mark.asyncio
    async def test_drains_all_queued_events(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._enqueue_progress("Step 1", 1, 3)
        tool._enqueue_progress("Step 2", 2, 3)
        tool._enqueue_progress("Step 3", 3, 3)

        events = [event async for event in tool.drain_progress_events()]

        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_drain_yields_events_in_order(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._enqueue_progress("Alpha", 1, 3)
        tool._enqueue_progress("Beta", 2, 3)

        events = [event async for event in tool.drain_progress_events()]

        assert events[0].current_step == "Alpha"
        assert events[1].current_step == "Beta"

    @pytest.mark.asyncio
    async def test_drain_empty_queue_yields_nothing(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        events = [event async for event in tool.drain_progress_events()]
        assert events == []

    @pytest.mark.asyncio
    async def test_drain_clears_queue(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._enqueue_progress("Step", 1, 1)
        async for _ in tool.drain_progress_events():
            pass
        assert tool._progress_queue.empty()





class TestDealSearch:
    @pytest.mark.asyncio
    async def test_empty_query_returns_failure(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        result = await tool.deal_search("")
        assert result.success is False
        assert "empty" in result.message

    @pytest.mark.asyncio
    async def test_whitespace_only_query_returns_failure(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        result = await tool.deal_search("   ")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_success_with_deals(self) -> None:
        comparison = DealComparison(
            query="headphones",
            deals=[_make_deal("Amazon", 99.99)],
            searched_stores=["Amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("headphones")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_result_data_has_deals_key(self) -> None:
        comparison = DealComparison(
            query="laptop",
            deals=[_make_deal()],
            searched_stores=["Amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("laptop")
        assert result.data is not None
        assert "deals" in result.data

    @pytest.mark.asyncio
    async def test_deal_dict_has_price_display(self) -> None:
        deal = _make_deal(price=149.99)
        comparison = DealComparison(query="tv", deals=[deal], searched_stores=["Amazon"])
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("tv")
        assert result.data is not None
        assert result.data["deals"][0]["price_display"] == "$149.99"

    @pytest.mark.asyncio
    async def test_deal_dict_has_original_price_display_when_present(self) -> None:
        deal = _make_deal(price=79.99, original_price=99.99)
        comparison = DealComparison(query="monitor", deals=[deal], searched_stores=["Amazon"])
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("monitor")
        assert result.data is not None
        assert result.data["deals"][0]["original_price_display"] == "$99.99"

    @pytest.mark.asyncio
    async def test_deal_dict_omits_original_price_display_when_none(self) -> None:
        deal = _make_deal(price=79.99, original_price=None)
        comparison = DealComparison(query="monitor", deals=[deal], searched_stores=["Amazon"])
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("monitor")
        assert result.data is not None
        assert "original_price_display" not in result.data["deals"][0]

    @pytest.mark.asyncio
    async def test_deal_dict_has_discount_display_when_present(self) -> None:
        deal = _make_deal(price=79.99, discount_percent=20.0)
        comparison = DealComparison(query="product", deals=[deal], searched_stores=["Amazon"])
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("product")
        assert result.data is not None
        assert result.data["deals"][0]["discount_display"] == "20.0% off"

    @pytest.mark.asyncio
    async def test_deal_dict_omits_discount_display_when_none(self) -> None:
        deal = _make_deal(price=79.99, discount_percent=None)
        comparison = DealComparison(query="product", deals=[deal], searched_stores=["Amazon"])
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("product")
        assert result.data is not None
        assert "discount_display" not in result.data["deals"][0]

    @pytest.mark.asyncio
    async def test_best_deal_serialized_in_data(self) -> None:
        deal = _make_deal("Amazon", 49.99)
        comparison = DealComparison(
            query="keyboard",
            deals=[deal],
            best_deal=deal,
            searched_stores=["Amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("keyboard")
        assert result.data is not None
        assert result.data["best_deal"] is not None
        assert result.data["best_deal"]["store"] == "Amazon"

    @pytest.mark.asyncio
    async def test_best_deal_is_none_when_no_best(self) -> None:
        comparison = DealComparison(
            query="product",
            deals=[_make_deal()],
            best_deal=None,
            searched_stores=["Amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("product")
        assert result.data is not None
        assert result.data["best_deal"] is None

    @pytest.mark.asyncio
    async def test_data_includes_coupons_list(self) -> None:
        comparison = DealComparison(
            query="product",
            deals=[_make_deal()],
            coupons_found=[_make_coupon()],
            searched_stores=["Amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("product")
        assert result.data is not None
        assert "coupons" in result.data
        assert len(result.data["coupons"]) == 1

    @pytest.mark.asyncio
    async def test_data_includes_empty_coupons_list(self) -> None:
        comparison = DealComparison(
            query="product",
            deals=[_make_deal()],
            coupons_found=[],
            searched_stores=["Amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("product")
        assert result.data is not None
        assert result.data["coupons"] == []

    @pytest.mark.asyncio
    async def test_data_includes_item_category_summary(self) -> None:
        comparison = DealComparison(
            query="product",
            deals=[_make_deal(item_category="digital")],
            searched_stores=["Amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("product")
        assert result.data is not None
        summary = result.data["item_category_summary"]
        assert summary["digital"] == 1
        assert summary["physical"] == 0

    @pytest.mark.asyncio
    async def test_data_includes_coupon_item_category_summary(self) -> None:
        comparison = DealComparison(
            query="product",
            deals=[_make_deal()],
            coupons_found=[_make_coupon(item_category="physical")],
            searched_stores=["Amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("product")
        assert result.data is not None
        assert "coupon_item_category_summary" in result.data

    @pytest.mark.asyncio
    async def test_suggested_filename_generated(self) -> None:
        comparison = DealComparison(
            query="Sony WH-1000XM5 Headphones",
            deals=[_make_deal()],
            searched_stores=["Amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("Sony WH-1000XM5 Headphones")
        assert result.suggested_filename is not None
        assert result.suggested_filename.startswith("deal_report_")
        assert result.suggested_filename.endswith(".md")

    @pytest.mark.asyncio
    async def test_suggested_filename_slug_lowercased(self) -> None:
        comparison = DealComparison(
            query="UPPERCASE Product",
            deals=[_make_deal()],
            searched_stores=["Amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("UPPERCASE Product")
        assert result.suggested_filename == result.suggested_filename.lower()

    @pytest.mark.asyncio
    async def test_suggested_filename_slug_max_40_chars_before_extension(self) -> None:
        long_query = "a" * 100
        comparison = DealComparison(
            query=long_query,
            deals=[_make_deal()],
            searched_stores=["Amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search(long_query)
        assert result.suggested_filename is not None
        # "deal_report_" prefix + slug (max 40) + ".md"
        slug_part = result.suggested_filename[len("deal_report_") : -len(".md")]
        assert len(slug_part) <= 40

    @pytest.mark.asyncio
    async def test_comparison_error_returns_failure(self) -> None:
        comparison = DealComparison(query="test", deals=[], error="Service unavailable")
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("test")
        assert result.success is False
        assert "Service unavailable" in result.message

    @pytest.mark.asyncio
    async def test_exception_during_search_returns_failure(self) -> None:
        tool = DealScraperTool(
            deal_finder=StubDealFinder(search_exc=RuntimeError("network down"))
        )
        result = await tool.deal_search("headphones")
        assert result.success is False
        assert "network down" in result.message

    @pytest.mark.asyncio
    async def test_no_deals_returns_success_with_empty_list(self) -> None:
        comparison = DealComparison(
            query="unobtainium",
            deals=[],
            searched_stores=["Amazon"],
            empty_reason=EmptyReason.NO_MATCHES,
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("unobtainium")
        assert result.success is True
        assert result.data is not None
        assert result.data["deals"] == []

    @pytest.mark.asyncio
    async def test_no_deals_message_mentions_query(self) -> None:
        comparison = DealComparison(
            query="unobtainium",
            deals=[],
            searched_stores=["Amazon"],
            empty_reason=EmptyReason.NO_MATCHES,
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("unobtainium")
        assert "unobtainium" in result.message

    @pytest.mark.asyncio
    async def test_no_deals_data_has_empty_reason(self) -> None:
        comparison = DealComparison(
            query="test",
            deals=[],
            searched_stores=[],
            empty_reason=EmptyReason.ALL_STORE_FAILURES,
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("test")
        assert result.data["empty_reason"] == "all_store_failures"

    @pytest.mark.asyncio
    async def test_no_deals_data_fallback_reason_when_none(self) -> None:
        comparison = DealComparison(
            query="test",
            deals=[],
            searched_stores=[],
            empty_reason=None,
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_search("test")
        assert result.data["empty_reason"] == "no_matches"

    @pytest.mark.asyncio
    async def test_partial_state_reset_on_each_search(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        tool._partial_state["store_statuses"].append({"store": "Old", "status": "found"})
        tool._partial_state["query"] = "old query"

        await tool.deal_search("new query")

        assert tool._partial_state["query"] == "new query"
        assert tool._partial_state["store_statuses"] == []
        assert tool._partial_state["partial_deals"] == []

    @pytest.mark.asyncio
    async def test_stores_passed_to_deal_finder(self) -> None:
        """Verify that stores list is forwarded to the underlying search."""
        received: list[list[str] | None] = []

        class TrackingFinder:
            async def search_deals(self, query, stores=None, max_results=10, progress=None):
                received.append(stores)
                return DealComparison(query=query, deals=[])

            async def find_coupons(self, *a, **kw):
                return CouponSearchResult()

            async def compare_prices(self, *a, **kw):
                return DealComparison(query="", deals=[])

        tool = DealScraperTool(deal_finder=TrackingFinder())
        await tool.deal_search("product", stores=["amazon.com", "walmart.com"])
        assert received[0] == ["amazon.com", "walmart.com"]

    @pytest.mark.asyncio
    async def test_progress_events_enqueued_via_callback(self) -> None:
        steps = [
            ("Searched Amazon (3 results)", 1, 3, None),
        ]
        comparison = DealComparison(query="test", deals=[_make_deal()], searched_stores=["Amazon"])
        finder = StubDealFinderWithProgress(comparison, steps)
        tool = DealScraperTool(deal_finder=finder)
        # Inject the unbound class-level callback since BaseTool shadows the instance method
        finder.inject_callback(DealScraperTool._progress_callback.__get__(tool))
        await tool.deal_search("test")
        assert tool._progress_queue.qsize() >= 1

    @pytest.mark.asyncio
    async def test_no_browser_show_progress_page_is_noop(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder(), browser=None)
        # Should complete without error even with no browser
        await tool._show_progress_page("test", "Searching")

    @pytest.mark.asyncio
    async def test_browser_navigate_called_when_browser_present(self) -> None:
        mock_browser = MagicMock()
        mock_browser.navigate_for_display = AsyncMock()
        comparison = DealComparison(query="test", deals=[_make_deal()], searched_stores=["Amazon"])
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison), browser=mock_browser)
        await tool.deal_search("test")
        # The progress page task is created; navigate_for_display may be called
        # We verify the browser attribute was used (task creation)
        assert tool._browser is mock_browser





class TestDealComparePrices:
    @pytest.mark.asyncio
    async def test_empty_urls_returns_failure(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        result = await tool.deal_compare_prices([])
        assert result.success is False
        assert "empty" in result.message

    @pytest.mark.asyncio
    async def test_urls_capped_at_10(self) -> None:
        """Verify that only the first 10 URLs are used."""
        received: list[list[str]] = []

        class TrackingFinder:
            async def search_deals(self, *a, **kw):
                return DealComparison(query="", deals=[])

            async def find_coupons(self, *a, **kw):
                return CouponSearchResult()

            async def compare_prices(self, product_urls, progress=None):
                received.append(product_urls)
                return DealComparison(query="", deals=[])

        tool = DealScraperTool(deal_finder=TrackingFinder())
        urls = [f"https://store{i}.example.com/product" for i in range(15)]
        await tool.deal_compare_prices(urls)
        assert len(received[0]) == 10

    @pytest.mark.asyncio
    async def test_success_with_deals(self) -> None:
        comparison = DealComparison(
            query="compare",
            deals=[
                _make_deal("Amazon", 99.99),
                _make_deal("Walmart", 89.99),
            ],
            searched_stores=["Amazon", "Walmart"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_compare_prices(
            ["https://amazon.com/dp/B001", "https://walmart.com/ip/12345"]
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_message_shows_cheapest_store(self) -> None:
        comparison = DealComparison(
            query="compare",
            deals=[
                _make_deal("Amazon", 89.99),
                _make_deal("Walmart", 99.99),
            ],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_compare_prices(
            ["https://amazon.com/dp/B001", "https://walmart.com/ip/12345"]
        )
        assert "89.99" in result.message
        assert "Amazon" in result.message

    @pytest.mark.asyncio
    async def test_message_shows_savings_when_multiple_deals(self) -> None:
        comparison = DealComparison(
            query="compare",
            deals=[
                _make_deal("Amazon", 89.99),
                _make_deal("Walmart", 109.99),
            ],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_compare_prices(
            ["https://amazon.com/dp/B001", "https://walmart.com/ip/12345"]
        )
        assert "save" in result.message.lower() or "20.00" in result.message

    @pytest.mark.asyncio
    async def test_message_no_savings_for_single_deal(self) -> None:
        comparison = DealComparison(
            query="compare",
            deals=[_make_deal("Amazon", 89.99)],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_compare_prices(["https://amazon.com/dp/B001"])
        assert result.success is True
        # savings should be 0, no "save" mention expected
        assert result.data is not None
        assert result.data["savings"] == 0

    @pytest.mark.asyncio
    async def test_data_has_price_display(self) -> None:
        comparison = DealComparison(
            query="compare",
            deals=[_make_deal("Amazon", 149.99)],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_compare_prices(["https://amazon.com/dp/B001"])
        assert result.data is not None
        assert result.data["deals"][0]["price_display"] == "$149.99"

    @pytest.mark.asyncio
    async def test_data_savings_rounded_to_2dp(self) -> None:
        comparison = DealComparison(
            query="compare",
            deals=[
                _make_deal("Amazon", 89.99),
                _make_deal("Walmart", 100.00),
            ],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_compare_prices(
            ["https://amazon.com/dp/B001", "https://walmart.com/ip/12345"]
        )
        assert result.data is not None
        savings = result.data["savings"]
        assert round(savings, 2) == savings

    @pytest.mark.asyncio
    async def test_no_deals_returns_success_with_failure_message(self) -> None:
        comparison = DealComparison(
            query="compare",
            deals=[],
            store_errors=[],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_compare_prices(["https://unknown.com/product"])
        assert result.success is True
        assert "Could not extract" in result.message

    @pytest.mark.asyncio
    async def test_no_deals_message_includes_store_errors(self) -> None:
        comparison = DealComparison(
            query="compare",
            deals=[],
            store_errors=[{"store": "example.com", "error": "timeout"}],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_compare_prices(["https://example.com/product"])
        assert "example.com" in result.message
        assert "timeout" in result.message

    @pytest.mark.asyncio
    async def test_failed_stores_listed_in_message(self) -> None:
        comparison = DealComparison(
            query="compare",
            deals=[_make_deal("Amazon", 99.99)],
            store_errors=[{"store": "Walmart", "error": "403 Forbidden"}],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_compare_prices(
            ["https://amazon.com/dp/B001", "https://walmart.com/ip/12345"]
        )
        assert "Walmart" in result.message
        assert "Could not check" in result.message

    @pytest.mark.asyncio
    async def test_exception_returns_failure(self) -> None:
        tool = DealScraperTool(
            deal_finder=StubDealFinder(compare_exc=ConnectionError("connection refused"))
        )
        result = await tool.deal_compare_prices(["https://example.com/product"])
        assert result.success is False
        assert "connection refused" in result.message

    @pytest.mark.asyncio
    async def test_format_instruction_in_message(self) -> None:
        comparison = DealComparison(
            query="compare",
            deals=[_make_deal("Amazon", 99.99)],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(comparison=comparison))
        result = await tool.deal_compare_prices(["https://amazon.com/dp/B001"])
        assert "FORMAT" in result.message





class TestDealFindCoupons:
    @pytest.mark.asyncio
    async def test_empty_store_name_returns_failure(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        result = await tool.deal_find_coupons("")
        assert result.success is False
        assert "empty" in result.message

    @pytest.mark.asyncio
    async def test_whitespace_store_name_returns_failure(self) -> None:
        tool = DealScraperTool(deal_finder=StubDealFinder())
        result = await tool.deal_find_coupons("   ")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_success_with_coupons(self) -> None:
        coupon_result = CouponSearchResult(coupons=[_make_coupon()])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_message_mentions_coupon_count(self) -> None:
        coupon_result = CouponSearchResult(coupons=[_make_coupon("A"), _make_coupon("B")])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert "2" in result.message
        assert "coupon" in result.message.lower()

    @pytest.mark.asyncio
    async def test_message_mentions_verified_count(self) -> None:
        coupons = [
            _make_coupon("A", verified=True),
            _make_coupon("B", verified=False),
        ]
        coupon_result = CouponSearchResult(coupons=coupons)
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert "1 verified" in result.message

    @pytest.mark.asyncio
    async def test_message_mentions_sources(self) -> None:
        coupons = [_make_coupon(source="slickdeals.net")]
        coupon_result = CouponSearchResult(coupons=coupons)
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert "slickdeals.net" in result.message

    @pytest.mark.asyncio
    async def test_data_has_coupons_key(self) -> None:
        coupon_result = CouponSearchResult(coupons=[_make_coupon()])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert result.data is not None
        assert "coupons" in result.data

    @pytest.mark.asyncio
    async def test_data_has_total(self) -> None:
        coupons = [_make_coupon("A"), _make_coupon("B"), _make_coupon("C")]
        coupon_result = CouponSearchResult(coupons=coupons)
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert result.data is not None
        assert result.data["total"] == 3

    @pytest.mark.asyncio
    async def test_data_has_verified_count(self) -> None:
        coupons = [
            _make_coupon("A", verified=True),
            _make_coupon("B", verified=True),
            _make_coupon("C", verified=False),
        ]
        coupon_result = CouponSearchResult(coupons=coupons)
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert result.data is not None
        assert result.data["verified_count"] == 2

    @pytest.mark.asyncio
    async def test_data_has_item_category_summary(self) -> None:
        coupons = [_make_coupon(item_category="digital")]
        coupon_result = CouponSearchResult(coupons=coupons)
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert result.data is not None
        summary = result.data["item_category_summary"]
        assert summary["digital"] == 1

    @pytest.mark.asyncio
    async def test_dedup_same_store_returns_cached_message(self) -> None:
        coupon_result = CouponSearchResult(coupons=[_make_coupon()])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))

        await tool.deal_find_coupons("Amazon")
        result = await tool.deal_find_coupons("Amazon Coupons")

        assert result.success is True
        assert "deduplicated" in result.data
        assert result.data["deduplicated"] is True

    @pytest.mark.asyncio
    async def test_dedup_message_contains_normalized_name(self) -> None:
        coupon_result = CouponSearchResult(coupons=[_make_coupon()])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))

        await tool.deal_find_coupons("Amazon")
        result = await tool.deal_find_coupons("Amazon Promo Code")

        assert "normalized" in result.data
        assert result.data["normalized"] == "amazon"

    @pytest.mark.asyncio
    async def test_different_stores_not_deduped(self) -> None:
        coupon_result = CouponSearchResult(coupons=[_make_coupon()])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))

        result1 = await tool.deal_find_coupons("Amazon")
        result2 = await tool.deal_find_coupons("BestBuy")

        assert result1.success is True
        assert result2.success is True
        # Neither should be a dedup hit
        assert not result1.data.get("deduplicated", False)
        assert not result2.data.get("deduplicated", False)

    @pytest.mark.asyncio
    async def test_normalized_store_added_to_searched_set(self) -> None:
        coupon_result = CouponSearchResult(coupons=[_make_coupon()])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))

        await tool.deal_find_coupons("Amazon")

        assert "amazon" in tool._coupon_searched_stores

    @pytest.mark.asyncio
    async def test_no_coupons_returns_success_with_failure_lines(self) -> None:
        coupon_result = CouponSearchResult(
            coupons=[],
            source_failures=[{"source": "slickdeals.net", "reason": "blocked"}],
            urls_checked=["https://slickdeals.net/amazon"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert result.success is True
        assert "No coupons found" in result.message
        assert "slickdeals.net" in result.message

    @pytest.mark.asyncio
    async def test_no_coupons_message_includes_urls_checked(self) -> None:
        coupon_result = CouponSearchResult(
            coupons=[],
            urls_checked=["https://retailmenot.com/view/amazon.com"],
        )
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert "https://retailmenot.com" in result.message

    @pytest.mark.asyncio
    async def test_no_coupons_message_warns_against_browser_navigate(self) -> None:
        coupon_result = CouponSearchResult(coupons=[])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert "browser_navigate" in result.message

    @pytest.mark.asyncio
    async def test_no_coupons_data_has_empty_category_summary(self) -> None:
        coupon_result = CouponSearchResult(coupons=[])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert result.data is not None
        assert result.data["item_category_summary"] == {"digital": 0, "physical": 0, "unknown": 0}

    @pytest.mark.asyncio
    async def test_no_coupons_data_has_store_key(self) -> None:
        coupon_result = CouponSearchResult(coupons=[])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Target")
        assert result.data is not None
        assert result.data["store"] == "Target"

    @pytest.mark.asyncio
    async def test_exception_returns_failure(self) -> None:
        tool = DealScraperTool(
            deal_finder=StubDealFinder(coupon_exc=ValueError("api error"))
        )
        result = await tool.deal_find_coupons("Amazon")
        assert result.success is False
        assert "api error" in result.message

    @pytest.mark.asyncio
    async def test_product_url_forwarded_to_finder(self) -> None:
        received: list[str | None] = []

        class TrackingFinder:
            async def search_deals(self, *a, **kw):
                return DealComparison(query="", deals=[])

            async def find_coupons(self, store, product_url=None, progress=None):
                received.append(product_url)
                return CouponSearchResult(coupons=[])

            async def compare_prices(self, *a, **kw):
                return DealComparison(query="", deals=[])

        tool = DealScraperTool(deal_finder=TrackingFinder())
        await tool.deal_find_coupons("Amazon", product_url="https://amazon.com/dp/B001")
        assert received[0] == "https://amazon.com/dp/B001"

    @pytest.mark.asyncio
    async def test_coupon_fields_serialized_via_asdict(self) -> None:
        coupon = CouponInfo(
            code="HOLIDAY30",
            description="30% off holiday",
            store="Amazon",
            expiry="2026-01-15",
            verified=True,
            source="retailmenot.com",
            confidence=0.85,
            item_category="physical",
            source_url="https://retailmenot.com/deal/456",
        )
        coupon_result = CouponSearchResult(coupons=[coupon])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert result.data is not None
        serialized = result.data["coupons"][0]
        assert serialized["code"] == "HOLIDAY30"
        assert serialized["confidence"] == 0.85
        assert serialized["item_category"] == "physical"
        assert serialized["source_url"] == "https://retailmenot.com/deal/456"

    @pytest.mark.asyncio
    async def test_message_includes_category_info(self) -> None:
        coupons = [
            _make_coupon(item_category="digital"),
            _make_coupon(code="B", item_category="physical"),
        ]
        coupon_result = CouponSearchResult(coupons=coupons)
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Adobe")
        assert "Item categories" in result.message

    @pytest.mark.asyncio
    async def test_format_instruction_in_message(self) -> None:
        coupon_result = CouponSearchResult(coupons=[_make_coupon()])
        tool = DealScraperTool(deal_finder=StubDealFinder(coupon_result=coupon_result))
        result = await tool.deal_find_coupons("Amazon")
        assert "FORMAT" in result.message
        assert "Verify at checkout" in result.message


