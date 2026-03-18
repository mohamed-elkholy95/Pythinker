from datetime import UTC, datetime

from app.domain.models.pricing_snapshot import PricingSnapshot
from app.domain.services.usage.normalization import NormalizedUsage, normalize_provider_usage
from app.domain.services.usage.pricing import select_pricing_snapshot


class TestNormalizeProviderUsage:
    def test_normalize_openai_usage_extracts_cached_and_reasoning_tokens(self) -> None:
        raw_usage = {
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "prompt_tokens_details": {"cached_tokens": 20},
            "completion_tokens_details": {"reasoning_tokens": 12},
            "total_tokens": 140,
        }

        normalized = normalize_provider_usage("openai", raw_usage)

        assert isinstance(normalized, NormalizedUsage)
        assert normalized.input_tokens == 100
        assert normalized.cached_input_tokens == 20
        assert normalized.output_tokens == 40
        assert normalized.reasoning_tokens == 12
        assert normalized.total_tokens == 140
        assert normalized.raw_usage == raw_usage

    def test_normalize_anthropic_usage_rolls_cache_fields_into_cached_input(self) -> None:
        raw_usage = {
            "input_tokens": 120,
            "output_tokens": 30,
            "cache_read_input_tokens": 40,
            "cache_creation_input_tokens": 15,
        }

        normalized = normalize_provider_usage("anthropic", raw_usage)

        assert normalized.input_tokens == 120
        assert normalized.cached_input_tokens == 40
        assert normalized.cache_creation_input_tokens == 15
        assert normalized.output_tokens == 30
        assert normalized.reasoning_tokens == 0
        assert normalized.total_tokens == 150

    def test_normalize_unknown_provider_keeps_raw_usage_and_defaults_missing_fields(self) -> None:
        raw_usage = {
            "prompt_tokens": 22,
            "completion_tokens": 11,
        }

        normalized = normalize_provider_usage("ollama", raw_usage)

        assert normalized.input_tokens == 22
        assert normalized.cached_input_tokens == 0
        assert normalized.output_tokens == 11
        assert normalized.reasoning_tokens == 0
        assert normalized.total_tokens == 33
        assert normalized.raw_usage == raw_usage

    def test_normalize_usage_supports_slots_based_objects(self) -> None:
        class SlotUsage:
            __slots__ = ("completion_tokens", "prompt_tokens", "total_tokens")

            def __init__(self) -> None:
                self.prompt_tokens = 12
                self.completion_tokens = 8
                self.total_tokens = 20

        normalized = normalize_provider_usage("ollama", SlotUsage())

        assert normalized.input_tokens == 12
        assert normalized.output_tokens == 8
        assert normalized.total_tokens == 20

    def test_normalize_usage_falls_back_for_non_numeric_token_fields(self) -> None:
        raw_usage = {
            "prompt_tokens": "unknown",
            "completion_tokens": "11",
        }

        normalized = normalize_provider_usage("ollama", raw_usage)

        assert normalized.input_tokens == 0
        assert normalized.output_tokens == 11
        assert normalized.total_tokens == 11


class TestSelectPricingSnapshot:
    def test_select_pricing_snapshot_uses_effective_date(self) -> None:
        snapshots = [
            PricingSnapshot(
                provider="openai",
                model_pattern="gpt-4o-mini",
                effective_from=datetime(2025, 1, 1, tzinfo=UTC),
                effective_to=datetime(2025, 12, 31, tzinfo=UTC),
                input_price_per_1m=0.15,
                output_price_per_1m=0.60,
                cached_read_price_per_1m=0.075,
                currency="USD",
                source_url="https://openai.com/api/pricing/",
                source_retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
            ),
            PricingSnapshot(
                provider="openai",
                model_pattern="gpt-4o-mini",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                effective_to=None,
                input_price_per_1m=0.20,
                output_price_per_1m=0.80,
                cached_read_price_per_1m=0.10,
                currency="USD",
                source_url="https://openai.com/api/pricing/",
                source_retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ]

        snapshot = select_pricing_snapshot(
            provider="openai",
            model_name="gpt-4o-mini",
            at_time=datetime(2026, 3, 17, tzinfo=UTC),
            snapshots=snapshots,
        )

        assert snapshot is not None
        assert snapshot.effective_from.year == 2026
        assert snapshot.input_price_per_1m == 0.20

    def test_select_pricing_snapshot_returns_none_when_provider_mismatches(self) -> None:
        snapshots = [
            PricingSnapshot(
                provider="anthropic",
                model_pattern="claude-sonnet-4",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                effective_to=None,
                input_price_per_1m=3.0,
                output_price_per_1m=15.0,
                currency="USD",
                source_url="https://platform.claude.com/docs/about-claude/pricing",
                source_retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]

        snapshot = select_pricing_snapshot(
            provider="openai",
            model_name="gpt-4o-mini",
            at_time=datetime(2026, 3, 17, tzinfo=UTC),
            snapshots=snapshots,
        )

        assert snapshot is None
