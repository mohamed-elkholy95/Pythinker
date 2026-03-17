"""Tests for the LLM-powered price extraction fallback (llm_price_extractor.py).

Validates:
- HTML context extraction (price-area detection, script/style stripping)
- LLM response parsing (valid JSON, markdown code blocks, malformed)
- Price validation (zero, negative, extreme values)
- Confidence scaling (LLM self-reported x base confidence)
- Error handling (JSON decode errors, LLM exceptions)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.external.deal_finder.llm_price_extractor import (
    CONFIDENCE_LLM,
    _extract_price_context,
    extract_price_with_llm,
)

# ──────────────────────────────────────────────────────────────
# Context extraction
# ──────────────────────────────────────────────────────────────


class TestExtractPriceContext:
    def test_finds_price_area(self) -> None:
        html = '<html><body><p>Hello</p><div class="price-box">$49.99</div></body></html>'
        result = _extract_price_context(html, "https://example.com")
        assert "$49.99" in result

    def test_fallback_to_head_of_document(self) -> None:
        html = "<html><body><p>No price keywords here</p></body></html>"
        result = _extract_price_context(html, "https://example.com")
        assert "No price keywords" in result

    def test_strips_script_tags(self) -> None:
        html = '<div class="price">$10</div><script>var x = 1;</script>'
        result = _extract_price_context(html, "https://example.com")
        assert "var x = 1" not in result
        assert "$10" in result

    def test_strips_style_tags(self) -> None:
        html = '<style>.price { color: red; }</style><span class="offer">$25</span>'
        result = _extract_price_context(html, "https://example.com")
        assert "color: red" not in result

    def test_truncates_to_max_length(self) -> None:
        html = '<div class="price">' + "x" * 10_000 + "</div>"
        result = _extract_price_context(html, "https://example.com")
        assert len(result) <= 3000


# ──────────────────────────────────────────────────────────────
# LLM extraction - successful cases
# ──────────────────────────────────────────────────────────────


class TestExtractPriceWithLLM:
    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_basic_extraction(self, mock_llm: AsyncMock) -> None:
        mock_llm.ask.return_value = {
            "content": json.dumps(
                {
                    "price": 49.99,
                    "original_price": 79.99,
                    "currency": "USD",
                    "in_stock": True,
                    "product_name": "Widget",
                    "confidence": 0.9,
                }
            )
        }

        vote = await extract_price_with_llm(
            "<div class='price'>$49.99</div>",
            "https://example.com/widget",
            mock_llm,
        )

        assert vote.price == 49.99
        assert vote.original_price == 79.99
        assert vote.product_name == "Widget"
        assert vote.method == "llm"
        assert vote.confidence == pytest.approx(CONFIDENCE_LLM * 0.9)

    @pytest.mark.asyncio
    async def test_markdown_code_block_response(self, mock_llm: AsyncMock) -> None:
        """LLM wraps JSON in markdown — extractor handles it."""
        mock_llm.ask.return_value = {
            "content": '```json\n{"price": 29.99, "currency": "USD", "in_stock": true, "confidence": 0.8}\n```'
        }

        vote = await extract_price_with_llm(
            "<span>$29.99</span>",
            "https://example.com/product",
            mock_llm,
        )

        assert vote.price == 29.99
        assert vote.confidence == pytest.approx(CONFIDENCE_LLM * 0.8)

    @pytest.mark.asyncio
    async def test_string_response(self, mock_llm: AsyncMock) -> None:
        """LLM returns a plain string instead of dict."""
        mock_llm.ask.return_value = '{"price": 15.00, "currency": "USD", "in_stock": true, "confidence": 0.7}'

        vote = await extract_price_with_llm(
            "<div>$15</div>",
            "https://example.com/item",
            mock_llm,
        )

        assert vote.price == 15.00

    @pytest.mark.asyncio
    async def test_null_price_in_response(self, mock_llm: AsyncMock) -> None:
        mock_llm.ask.return_value = {
            "content": '{"price": null, "currency": "USD", "in_stock": false, "confidence": 0.3}'
        }

        vote = await extract_price_with_llm(
            "<div>Out of stock</div>",
            "https://example.com/gone",
            mock_llm,
        )

        assert vote.price is None
        assert vote.method == "llm"

    @pytest.mark.asyncio
    async def test_product_hint_passed(self, mock_llm: AsyncMock) -> None:
        mock_llm.ask.return_value = {
            "content": '{"price": 99.99, "currency": "USD", "in_stock": true, "confidence": 0.9}'
        }

        await extract_price_with_llm(
            "<div>$99.99</div>",
            "https://example.com/headphones",
            mock_llm,
            product_hint="Sony WH-1000XM5",
        )

        call_args = mock_llm.ask.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "Sony WH-1000XM5" in user_msg["content"]


# ──────────────────────────────────────────────────────────────
# Price validation
# ──────────────────────────────────────────────────────────────


class TestPriceValidation:
    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_zero_price_rejected(self, mock_llm: AsyncMock) -> None:
        mock_llm.ask.return_value = {"content": '{"price": 0, "currency": "USD", "in_stock": true, "confidence": 0.9}'}

        vote = await extract_price_with_llm("<div>$0</div>", "https://example.com", mock_llm)
        assert vote.price is None

    @pytest.mark.asyncio
    async def test_negative_price_rejected(self, mock_llm: AsyncMock) -> None:
        mock_llm.ask.return_value = {
            "content": '{"price": -5.0, "currency": "USD", "in_stock": true, "confidence": 0.9}'
        }

        vote = await extract_price_with_llm("<div>-$5</div>", "https://example.com", mock_llm)
        assert vote.price is None

    @pytest.mark.asyncio
    async def test_extreme_price_rejected(self, mock_llm: AsyncMock) -> None:
        mock_llm.ask.return_value = {
            "content": '{"price": 999999, "currency": "USD", "in_stock": true, "confidence": 0.5}'
        }

        vote = await extract_price_with_llm("<div>$999999</div>", "https://example.com", mock_llm)
        assert vote.price is None

    @pytest.mark.asyncio
    async def test_negative_original_price_rejected(self, mock_llm: AsyncMock) -> None:
        mock_llm.ask.return_value = {
            "content": '{"price": 49.99, "original_price": -10, "currency": "USD", "in_stock": true, "confidence": 0.9}'
        }

        vote = await extract_price_with_llm("<div>$49.99</div>", "https://example.com", mock_llm)
        assert vote.price == 49.99
        assert vote.original_price is None


# ──────────────────────────────────────────────────────────────
# Error handling
# ──────────────────────────────────────────────────────────────


class TestErrorHandling:
    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_no_json_in_response(self, mock_llm: AsyncMock) -> None:
        mock_llm.ask.return_value = {"content": "I'm sorry, I can't determine the price."}

        vote = await extract_price_with_llm("<div>???</div>", "https://example.com", mock_llm)
        assert vote.price is None
        assert vote.confidence == 0.0

    @pytest.mark.asyncio
    async def test_malformed_json(self, mock_llm: AsyncMock) -> None:
        mock_llm.ask.return_value = {"content": '{"price": not_a_number}'}

        vote = await extract_price_with_llm("<div>$10</div>", "https://example.com", mock_llm)
        assert vote.price is None
        assert vote.confidence == 0.0

    @pytest.mark.asyncio
    async def test_llm_raises_exception(self, mock_llm: AsyncMock) -> None:
        mock_llm.ask.side_effect = RuntimeError("LLM service unavailable")

        vote = await extract_price_with_llm("<div>$10</div>", "https://example.com", mock_llm)
        assert vote.price is None
        assert vote.confidence == 0.0

    @pytest.mark.asyncio
    async def test_default_confidence_when_missing(self, mock_llm: AsyncMock) -> None:
        """No 'confidence' key in LLM response → defaults to 0.7."""
        mock_llm.ask.return_value = {"content": '{"price": 25.00, "currency": "USD", "in_stock": true}'}

        vote = await extract_price_with_llm("<div>$25</div>", "https://example.com", mock_llm)
        assert vote.price == 25.00
        assert vote.confidence == pytest.approx(CONFIDENCE_LLM * 0.7)
