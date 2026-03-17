"""Tests for the price history persistence layer (deal_history_repository.py).

Validates:
- Product ID normalization (case, suffixes, store prefixing)
- Regex escaping for MongoDB $regex
- Record/bulk-record error resilience (never raises)
- Query building for get_price_history
- Pipeline construction for get_price_stats and get_sparkline_data
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.repositories.deal_history_repository import (
    _escape_regex,
    _normalize_product_id,
    ensure_indexes,
    get_price_history,
    get_price_stats,
    get_sparkline_data,
    record_price,
    record_prices_bulk,
)

# ──────────────────────────────────────────────────────────────
# Product ID normalization
# ──────────────────────────────────────────────────────────────


class TestNormalizeProductId:
    def test_basic(self) -> None:
        assert _normalize_product_id("Sony WH-1000XM5", "Amazon") == "amazon:sony wh-1000xm5"

    def test_strips_suffix_after_dash(self) -> None:
        result = _normalize_product_id("Headphones - Best Buy Special Edition", "BestBuy")
        assert result == "bestbuy:headphones"

    def test_strips_suffix_after_pipe(self) -> None:
        result = _normalize_product_id("Widget | Amazon.com", "Amazon")
        assert result == "amazon:widget"

    def test_strips_whitespace(self) -> None:
        result = _normalize_product_id("  Laptop  ", "Walmart")
        assert result == "walmart:laptop"

    def test_lowercases_store(self) -> None:
        result = _normalize_product_id("Item", "NEWEGG")
        assert result.startswith("newegg:")


# ──────────────────────────────────────────────────────────────
# Regex escaping
# ──────────────────────────────────────────────────────────────


class TestEscapeRegex:
    def test_dots(self) -> None:
        assert _escape_regex("3.5mm") == "3\\.5mm"

    def test_parens(self) -> None:
        assert _escape_regex("(Pro)") == "\\(Pro\\)"

    def test_brackets(self) -> None:
        assert _escape_regex("[NEW]") == "\\[NEW\\]"

    def test_dollar_sign(self) -> None:
        assert _escape_regex("$49") == "\\$49"

    def test_plain_text(self) -> None:
        assert _escape_regex("Headphones") == "Headphones"


# ──────────────────────────────────────────────────────────────
# Mock DealResult dataclass
# ──────────────────────────────────────────────────────────────


@dataclass
class FakeDeal:
    """Minimal stand-in for DealResult to avoid importing domain models."""

    product_name: str = "Test Widget"
    store: str = "Amazon"
    price: float = 49.99
    original_price: float | None = 79.99
    url: str = "https://amazon.com/widget"
    extraction_strategy: str = "json_ld"
    extraction_confidence: float = 0.95
    in_stock: bool = True
    source_type: str = "store_search"


# ──────────────────────────────────────────────────────────────
# record_price / record_prices_bulk
# ──────────────────────────────────────────────────────────────


class TestRecordPrice:
    @pytest.mark.asyncio
    async def test_inserts_document(self) -> None:
        mock_col = AsyncMock()
        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            await record_price(FakeDeal(), query="headphones", user_id="u1")
            mock_col.insert_one.assert_awaited_once()

            doc = mock_col.insert_one.call_args[0][0]
            assert doc["product_name"] == "Test Widget"
            assert doc["price"] == 49.99
            assert doc["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_does_not_raise_on_error(self) -> None:
        mock_col = AsyncMock()
        mock_col.insert_one.side_effect = RuntimeError("DB down")
        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            # Should not raise
            await record_price(FakeDeal())


class TestRecordPricesBulk:
    @pytest.mark.asyncio
    async def test_bulk_insert(self) -> None:
        mock_col = AsyncMock()
        deals = [FakeDeal(price=10.0), FakeDeal(price=20.0)]
        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            await record_prices_bulk(deals, query="test")
            mock_col.insert_many.assert_awaited_once()
            docs = mock_col.insert_many.call_args[0][0]
            assert len(docs) == 2

    @pytest.mark.asyncio
    async def test_skips_zero_price(self) -> None:
        mock_col = AsyncMock()
        deals = [FakeDeal(price=0.0), FakeDeal(price=10.0)]
        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            await record_prices_bulk(deals, query="test")
            docs = mock_col.insert_many.call_args[0][0]
            assert len(docs) == 1

    @pytest.mark.asyncio
    async def test_empty_deals_list(self) -> None:
        mock_col = AsyncMock()
        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            await record_prices_bulk([], query="test")
            mock_col.insert_many.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_error(self) -> None:
        mock_col = AsyncMock()
        mock_col.insert_many.side_effect = RuntimeError("DB down")
        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            await record_prices_bulk([FakeDeal()], query="test")


# ──────────────────────────────────────────────────────────────
# ensure_indexes
# ──────────────────────────────────────────────────────────────


class TestEnsureIndexes:
    @pytest.mark.asyncio
    async def test_creates_three_indexes(self) -> None:
        mock_col = AsyncMock()
        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            await ensure_indexes()
            assert mock_col.create_index.await_count == 3

    @pytest.mark.asyncio
    async def test_does_not_raise_on_error(self) -> None:
        mock_col = AsyncMock()
        mock_col.create_index.side_effect = RuntimeError("Connection error")
        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            await ensure_indexes()  # Should not raise


# ──────────────────────────────────────────────────────────────
# get_price_history
# ──────────────────────────────────────────────────────────────


class TestGetPriceHistory:
    @pytest.mark.asyncio
    async def test_with_store_uses_product_id(self) -> None:
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[{"price": 49.99}])

        mock_col = MagicMock()
        mock_find = MagicMock(return_value=mock_col)
        mock_col.sort = MagicMock(return_value=mock_col)
        mock_col.limit = MagicMock(return_value=mock_cursor)
        mock_col_root = MagicMock()
        mock_col_root.find = mock_find

        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col_root,
        ):
            result = await get_price_history("Widget", store="Amazon", days=30)
            assert result == [{"price": 49.99}]
            query_arg = mock_find.call_args[0][0]
            assert "product_id" in query_arg

    @pytest.mark.asyncio
    async def test_without_store_uses_regex(self) -> None:
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_col = MagicMock()
        mock_find = MagicMock(return_value=mock_col)
        mock_col.sort = MagicMock(return_value=mock_col)
        mock_col.limit = MagicMock(return_value=mock_cursor)
        mock_col_root = MagicMock()
        mock_col_root.find = mock_find

        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col_root,
        ):
            await get_price_history("Widget", days=7)
            query_arg = mock_find.call_args[0][0]
            assert "product_name" in query_arg
            assert "$regex" in query_arg["product_name"]

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self) -> None:
        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            side_effect=RuntimeError("DB error"),
        ):
            result = await get_price_history("Widget")
            assert result == []


# ──────────────────────────────────────────────────────────────
# get_price_stats
# ──────────────────────────────────────────────────────────────


class TestGetPriceStats:
    @pytest.mark.asyncio
    async def test_returns_stats_dict(self) -> None:
        agg_result = [
            {
                "_id": None,
                "min_price": 40.0,
                "max_price": 60.0,
                "avg_price": 50.0,
                "count": 10,
                "latest_price": 45.0,
                "first_price": 55.0,
            }
        ]
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=agg_result)

        mock_col = MagicMock()
        mock_col.aggregate = MagicMock(return_value=mock_cursor)

        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            stats = await get_price_stats("Widget", "Amazon", days=90)
            assert stats is not None
            assert stats["min_price"] == 40.0
            assert stats["max_price"] == 60.0
            assert stats["avg_price"] == 50.0
            assert stats["trend"] == "decreasing"  # 45 < 55
            assert stats["is_all_time_low"] is False  # 45 > 40

    @pytest.mark.asyncio
    async def test_all_time_low_detection(self) -> None:
        agg_result = [
            {
                "_id": None,
                "min_price": 40.0,
                "max_price": 60.0,
                "avg_price": 50.0,
                "count": 5,
                "latest_price": 40.0,
                "first_price": 55.0,
            }
        ]
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=agg_result)

        mock_col = MagicMock()
        mock_col.aggregate = MagicMock(return_value=mock_cursor)

        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            stats = await get_price_stats("Widget", "Amazon")
            assert stats["is_all_time_low"] is True

    @pytest.mark.asyncio
    async def test_no_data_returns_none(self) -> None:
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_col = MagicMock()
        mock_col.aggregate = MagicMock(return_value=mock_cursor)

        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            stats = await get_price_stats("Widget", "Amazon")
            assert stats is None

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self) -> None:
        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            side_effect=RuntimeError("DB error"),
        ):
            stats = await get_price_stats("Widget", "Amazon")
            assert stats is None


# ──────────────────────────────────────────────────────────────
# get_sparkline_data
# ──────────────────────────────────────────────────────────────


class TestGetSparklineData:
    @pytest.mark.asyncio
    async def test_returns_price_list(self) -> None:
        agg_result = [
            {"_id": "2026-02-25", "price": 49.99},
            {"_id": "2026-02-26", "price": 47.50},
            {"_id": "2026-02-27", "price": 45.00},
        ]
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=agg_result)

        mock_col = MagicMock()
        mock_col.aggregate = MagicMock(return_value=mock_cursor)

        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            data = await get_sparkline_data("Widget", "Amazon", days=30, points=30)
            assert data == [49.99, 47.50, 45.00]

    @pytest.mark.asyncio
    async def test_empty_when_no_data(self) -> None:
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_col = MagicMock()
        mock_col.aggregate = MagicMock(return_value=mock_cursor)

        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            return_value=mock_col,
        ):
            data = await get_sparkline_data("Widget", "Amazon")
            assert data == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self) -> None:
        with patch(
            "app.infrastructure.repositories.deal_history_repository._get_collection",
            side_effect=RuntimeError("DB error"),
        ):
            data = await get_sparkline_data("Widget", "Amazon")
            assert data == []
