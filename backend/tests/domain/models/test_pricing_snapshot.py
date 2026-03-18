from datetime import UTC, datetime

import pytest

from app.domain.models.pricing_snapshot import PricingSnapshot


class TestPricingSnapshot:
    def test_is_effective_at_returns_true_within_bounded_window(self) -> None:
        snapshot = PricingSnapshot(
            provider="openai",
            model_pattern="gpt-4o-mini",
            effective_from=datetime(2026, 3, 1, tzinfo=UTC),
            effective_to=datetime(2026, 3, 31, tzinfo=UTC),
            input_price_per_1m=0.15,
            output_price_per_1m=0.60,
            currency="USD",
            source_url="https://openai.com/api/pricing/",
            source_retrieved_at=datetime(2026, 3, 17, tzinfo=UTC),
        )

        assert snapshot.is_effective_at(datetime(2026, 3, 17, tzinfo=UTC)) is True
        assert snapshot.is_effective_at(datetime(2026, 4, 1, tzinfo=UTC)) is False

    def test_matches_model_supports_exact_and_prefix_variants(self) -> None:
        snapshot = PricingSnapshot(
            provider="anthropic",
            model_pattern="claude-sonnet-4",
            effective_from=datetime(2026, 3, 1, tzinfo=UTC),
            effective_to=None,
            input_price_per_1m=3.0,
            output_price_per_1m=15.0,
            cached_read_price_per_1m=0.30,
            cache_write_price_per_1m=3.75,
            currency="USD",
            source_url="https://platform.claude.com/docs/about-claude/pricing",
            source_retrieved_at=datetime(2026, 3, 17, tzinfo=UTC),
        )

        assert snapshot.matches_model("claude-sonnet-4") is True
        assert snapshot.matches_model("claude-sonnet-4-20250514") is True
        assert snapshot.matches_model("claude-opus-4-20250514") is False

    def test_pricing_snapshot_rejects_naive_datetimes(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            PricingSnapshot(
                provider="openai",
                model_pattern="gpt-4o-mini",
                effective_from=datetime(2026, 3, 1),  # noqa: DTZ001
                effective_to=None,
                input_price_per_1m=0.15,
                output_price_per_1m=0.60,
                currency="USD",
                source_url="https://openai.com/api/pricing/",
                source_retrieved_at=datetime(2026, 3, 17, tzinfo=UTC),
            )

    def test_is_effective_at_rejects_naive_lookup_time(self) -> None:
        snapshot = PricingSnapshot(
            provider="openai",
            model_pattern="gpt-4o-mini",
            effective_from=datetime(2026, 3, 1, tzinfo=UTC),
            effective_to=None,
            input_price_per_1m=0.15,
            output_price_per_1m=0.60,
            currency="USD",
            source_url="https://openai.com/api/pricing/",
            source_retrieved_at=datetime(2026, 3, 17, tzinfo=UTC),
        )

        with pytest.raises(ValueError, match="timezone-aware"):
            snapshot.is_effective_at(datetime(2026, 3, 17))  # noqa: DTZ001
