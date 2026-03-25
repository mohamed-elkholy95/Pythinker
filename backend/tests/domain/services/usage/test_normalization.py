"""Tests for provider usage normalization."""

from app.domain.services.usage.normalization import (
    NormalizedUsage,
    normalize_provider_usage,
)


class TestNormalizedUsageDefaults:
    def test_defaults(self) -> None:
        n = NormalizedUsage()
        assert n.input_tokens == 0
        assert n.output_tokens == 0
        assert n.cached_input_tokens == 0
        assert n.reasoning_tokens == 0
        assert n.total_tokens == 0
        assert n.raw_usage == {}


class TestNormalizeOpenAI:
    def test_basic(self) -> None:
        raw = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        n = normalize_provider_usage("openai", raw)
        assert n.input_tokens == 100
        assert n.output_tokens == 50
        assert n.total_tokens == 150

    def test_with_cached_tokens(self) -> None:
        raw = {
            "prompt_tokens": 500,
            "completion_tokens": 200,
            "total_tokens": 700,
            "prompt_tokens_details": {"cached_tokens": 300},
        }
        n = normalize_provider_usage("openai", raw)
        assert n.cached_input_tokens == 300

    def test_with_reasoning_tokens(self) -> None:
        raw = {
            "prompt_tokens": 500,
            "completion_tokens": 200,
            "total_tokens": 700,
            "completion_tokens_details": {"reasoning_tokens": 100},
        }
        n = normalize_provider_usage("openai", raw)
        assert n.reasoning_tokens == 100

    def test_preserves_raw(self) -> None:
        raw = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        n = normalize_provider_usage("openai", raw)
        assert n.raw_usage == raw


class TestNormalizeAnthropic:
    def test_basic(self) -> None:
        raw = {"input_tokens": 200, "output_tokens": 100}
        n = normalize_provider_usage("anthropic", raw)
        assert n.input_tokens == 200
        assert n.output_tokens == 100
        assert n.total_tokens == 300

    def test_with_cache(self) -> None:
        raw = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_input_tokens": 800,
            "cache_creation_input_tokens": 200,
        }
        n = normalize_provider_usage("anthropic", raw)
        assert n.cached_input_tokens == 800
        assert n.cache_creation_input_tokens == 200


class TestNormalizeGeneric:
    def test_fallback_prompt_tokens(self) -> None:
        raw = {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75}
        n = normalize_provider_usage("unknown_provider", raw)
        assert n.input_tokens == 50
        assert n.output_tokens == 25
        assert n.total_tokens == 75

    def test_fallback_input_tokens(self) -> None:
        raw = {"input_tokens": 50, "output_tokens": 25}
        n = normalize_provider_usage("some_provider", raw)
        assert n.input_tokens == 50
        assert n.output_tokens == 25
        assert n.total_tokens == 75

    def test_none_usage(self) -> None:
        n = normalize_provider_usage("openai", None)
        assert n.input_tokens == 0
        assert n.output_tokens == 0
        assert n.total_tokens == 0

    def test_empty_dict(self) -> None:
        n = normalize_provider_usage("openai", {})
        assert n.total_tokens == 0
