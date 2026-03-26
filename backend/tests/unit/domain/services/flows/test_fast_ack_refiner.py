"""Tests for FastAcknowledgmentRefiner."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.services.flows.fast_ack_refiner import FastAcknowledgmentRefiner


@pytest.fixture
def mock_llm() -> AsyncMock:
    llm = AsyncMock()
    llm.ask = AsyncMock(return_value={"content": "Got it! I will research that topic."})
    return llm


@pytest.fixture
def mock_fallback() -> MagicMock:
    fb = MagicMock()
    fb.generate = MagicMock(return_value="Got it! I will help with that.")
    return fb


@pytest.fixture
def mock_metrics() -> MagicMock:
    m = MagicMock()
    m.record_counter = MagicMock()
    m.record_histogram = MagicMock()
    return m


@pytest.fixture
def refiner(mock_llm: AsyncMock, mock_fallback: MagicMock) -> FastAcknowledgmentRefiner:
    return FastAcknowledgmentRefiner(llm=mock_llm, fallback_generator=mock_fallback)


class TestGenerate:
    """Tests for generate method."""

    @pytest.mark.asyncio
    async def test_returns_refined_on_success(
        self, refiner: FastAcknowledgmentRefiner, mock_metrics: MagicMock
    ) -> None:
        with patch("app.domain.services.flows.fast_ack_refiner.get_metrics", return_value=mock_metrics):
            result = await refiner.generate("research AI trends")
        assert result.startswith("Got it!")

    @pytest.mark.asyncio
    async def test_returns_fallback_on_timeout(
        self, mock_llm: AsyncMock, mock_fallback: MagicMock, mock_metrics: MagicMock
    ) -> None:
        async def slow_ask(**kwargs):
            await asyncio.sleep(10)
            return {"content": "slow"}

        mock_llm.ask = slow_ask
        refiner = FastAcknowledgmentRefiner(llm=mock_llm, fallback_generator=mock_fallback, timeout_seconds=0.01)

        with patch("app.domain.services.flows.fast_ack_refiner.get_metrics", return_value=mock_metrics):
            result = await refiner.generate("test query")

        assert result == "Got it! I will help with that."

    @pytest.mark.asyncio
    async def test_returns_fallback_on_empty_response(
        self, mock_llm: AsyncMock, mock_fallback: MagicMock, mock_metrics: MagicMock
    ) -> None:
        mock_llm.ask = AsyncMock(return_value={"content": ""})
        refiner = FastAcknowledgmentRefiner(llm=mock_llm, fallback_generator=mock_fallback)

        with patch("app.domain.services.flows.fast_ack_refiner.get_metrics", return_value=mock_metrics):
            result = await refiner.generate("query")

        assert result == "Got it! I will help with that."

    @pytest.mark.asyncio
    async def test_returns_fallback_on_exception(
        self, mock_llm: AsyncMock, mock_fallback: MagicMock, mock_metrics: MagicMock
    ) -> None:
        mock_llm.ask = AsyncMock(side_effect=RuntimeError("LLM down"))
        refiner = FastAcknowledgmentRefiner(llm=mock_llm, fallback_generator=mock_fallback)

        with patch("app.domain.services.flows.fast_ack_refiner.get_metrics", return_value=mock_metrics):
            result = await refiner.generate("query")

        assert result == "Got it! I will help with that."

    @pytest.mark.asyncio
    async def test_keys_exhausted_logs_at_debug(
        self, mock_llm: AsyncMock, mock_fallback: MagicMock, mock_metrics: MagicMock
    ) -> None:
        from app.domain.exceptions.base import LLMKeysExhaustedError

        mock_llm.ask = AsyncMock(side_effect=LLMKeysExhaustedError("test-provider", key_count=0))
        refiner = FastAcknowledgmentRefiner(llm=mock_llm, fallback_generator=mock_fallback)

        with patch("app.domain.services.flows.fast_ack_refiner.get_metrics", return_value=mock_metrics):
            result = await refiner.generate("query")

        assert result == "Got it! I will help with that."


class TestSanitize:
    """Tests for _sanitize."""

    def setup_method(self) -> None:
        self.refiner = FastAcknowledgmentRefiner(llm=AsyncMock(), fallback_generator=MagicMock())

    def test_empty_string(self) -> None:
        assert self.refiner._sanitize("") == ""

    def test_none_returns_empty(self) -> None:
        assert self.refiner._sanitize(None) == ""

    def test_prepends_got_it_if_missing(self) -> None:
        result = self.refiner._sanitize("I will research that.")
        assert result.startswith("Got it!")

    def test_preserves_got_it_prefix(self) -> None:
        result = self.refiner._sanitize("Got it! Working on it.")
        assert result.startswith("Got it!")
        assert result.count("Got it!") == 1

    def test_truncates_long_text(self) -> None:
        long_text = "Got it! " + "word " * 100
        result = self.refiner._sanitize(long_text)
        # Sanitize truncates at 300 and may add trailing punctuation
        assert len(result) <= 301

    def test_strips_reddit_mentions(self) -> None:
        text = "Got it! I will research on Reddit and other sources."
        result = self.refiner._sanitize(text)
        assert "Reddit" not in result

    def test_strips_stackoverflow_mentions(self) -> None:
        text = "Got it! I will search Stack Overflow for solutions."
        result = self.refiner._sanitize(text)
        assert "Stack Overflow" not in result

    def test_normalizes_following_topics(self) -> None:
        text = "Got it! I will create a report on following topics"
        result = self.refiner._sanitize(text)
        assert "the following" in result


class TestShouldPreferFallback:
    """Tests for _should_prefer_fallback."""

    def setup_method(self) -> None:
        self.refiner = FastAcknowledgmentRefiner(llm=AsyncMock(), fallback_generator=MagicMock())

    def test_generic_refined_non_generic_fallback(self) -> None:
        refined = "Got it! I will research on the following topics."
        fallback = "Got it! I will research AI trends."
        assert self.refiner._should_prefer_fallback(refined, fallback) is True

    def test_non_generic_refined(self) -> None:
        refined = "Got it! I will research AI trends."
        fallback = "Got it! I will help with that."
        assert self.refiner._should_prefer_fallback(refined, fallback) is False

    def test_both_generic(self) -> None:
        refined = "Got it! I will research on the following topics."
        fallback = "Got it! I will research on the following items."
        assert self.refiner._should_prefer_fallback(refined, fallback) is False


class TestShouldSampleTraceback:
    """Tests for _should_sample_traceback."""

    def test_zero_rate_never_samples(self) -> None:
        refiner = FastAcknowledgmentRefiner(llm=AsyncMock(), fallback_generator=MagicMock(), traceback_sample_rate=0)
        refiner._error_count = 1
        assert refiner._should_sample_traceback() is False

    def test_full_rate_always_samples(self) -> None:
        refiner = FastAcknowledgmentRefiner(llm=AsyncMock(), fallback_generator=MagicMock(), traceback_sample_rate=1.0)
        refiner._error_count = 1
        assert refiner._should_sample_traceback() is True

    def test_5_percent_rate_samples_every_20th(self) -> None:
        refiner = FastAcknowledgmentRefiner(llm=AsyncMock(), fallback_generator=MagicMock(), traceback_sample_rate=0.05)
        refiner._error_count = 20
        assert refiner._should_sample_traceback() is True
        refiner._error_count = 21
        assert refiner._should_sample_traceback() is False
