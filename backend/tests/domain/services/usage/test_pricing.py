"""Tests for model pricing and cost calculation."""

import pytest

from app.domain.services.usage.pricing import (
    DEFAULT_PRICING,
    MODEL_PRICING,
    ModelPricing,
    get_model_pricing,
)


class TestModelPricing:
    def test_calculate_cost_basic(self) -> None:
        p = ModelPricing(prompt_price=2.50, completion_price=10.0)
        prompt_cost, completion_cost, total = p.calculate_cost(1_000_000, 500_000)
        assert prompt_cost == pytest.approx(2.50)
        assert completion_cost == pytest.approx(5.0)
        assert total == pytest.approx(7.50)

    def test_calculate_cost_with_caching(self) -> None:
        p = ModelPricing(prompt_price=3.0, completion_price=15.0, cached_price=0.30)
        prompt_cost, completion_cost, total = p.calculate_cost(
            prompt_tokens=1_000_000,
            completion_tokens=100_000,
            cached_tokens=500_000,
        )
        # 500k at 3.0/M + 500k at 0.30/M = 1.50 + 0.15 = 1.65
        assert prompt_cost == pytest.approx(1.65)
        assert completion_cost == pytest.approx(1.50)
        assert total == pytest.approx(3.15)

    def test_calculate_cost_zero_tokens(self) -> None:
        p = ModelPricing(prompt_price=10.0, completion_price=30.0)
        prompt_cost, completion_cost, total = p.calculate_cost(0, 0)
        assert total == 0.0

    def test_free_model(self) -> None:
        p = ModelPricing(prompt_price=0.0, completion_price=0.0)
        _, _, total = p.calculate_cost(1_000_000, 1_000_000)
        assert total == 0.0

    def test_cached_tokens_no_cached_price(self) -> None:
        p = ModelPricing(prompt_price=5.0, completion_price=15.0, cached_price=None)
        # When cached_price is None, cached_tokens are ignored
        prompt_cost, _, total = p.calculate_cost(1_000_000, 0, cached_tokens=500_000)
        assert prompt_cost == pytest.approx(5.0)


class TestGetModelPricing:
    def test_exact_match_gpt4o(self) -> None:
        p = get_model_pricing("gpt-4o")
        assert p.prompt_price == 2.50
        assert p.completion_price == 10.0

    def test_exact_match_claude_sonnet(self) -> None:
        p = get_model_pricing("claude-3-5-sonnet-20241022")
        assert p.prompt_price == 3.0

    def test_fuzzy_match(self) -> None:
        # Should match base gpt-4o for variants
        get_model_pricing.cache_clear()
        p = get_model_pricing("gpt-4o-2024-11-20")
        assert p.prompt_price == 2.50

    def test_free_model_ollama(self) -> None:
        get_model_pricing.cache_clear()
        p = get_model_pricing("llama3.2")
        assert p.prompt_price == 0.0
        assert p.completion_price == 0.0

    def test_unknown_model_returns_fallback(self) -> None:
        get_model_pricing.cache_clear()
        p = get_model_pricing("totally-unknown-model-abc123")
        # Should return some pricing (either default or a fuzzy match)
        assert p.prompt_price >= 0.0
        assert p.completion_price >= 0.0

    def test_case_insensitive(self) -> None:
        get_model_pricing.cache_clear()
        p = get_model_pricing("GPT-4o")
        assert p.prompt_price == 2.50

    def test_deepseek(self) -> None:
        get_model_pricing.cache_clear()
        p = get_model_pricing("deepseek-chat")
        assert p.prompt_price == 0.14


class TestModelPricingDatabase:
    def test_all_have_positive_or_zero_prices(self) -> None:
        for name, p in MODEL_PRICING.items():
            assert p.prompt_price >= 0.0, f"{name} has negative prompt_price"
            assert p.completion_price >= 0.0, f"{name} has negative completion_price"
            if p.cached_price is not None:
                assert p.cached_price >= 0.0, f"{name} has negative cached_price"

    def test_cached_price_less_than_prompt(self) -> None:
        for name, p in MODEL_PRICING.items():
            if p.cached_price is not None and p.prompt_price > 0:
                assert p.cached_price <= p.prompt_price, (
                    f"{name} cached_price ({p.cached_price}) > prompt_price ({p.prompt_price})"
                )
