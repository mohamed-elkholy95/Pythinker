from __future__ import annotations

import asyncio

import pytest

from app.domain.services.flows.acknowledgment import AcknowledgmentGenerator
from app.domain.services.flows.fast_ack_refiner import FastAcknowledgmentRefiner


class _FakeLLM:
    def __init__(self, content: str = "", delay: float = 0.0, raises: Exception | None = None):
        self._content = content
        self._delay = delay
        self._raises = raises

    async def ask(self, *args, **kwargs):
        if self._raises:
            raise self._raises
        if self._delay:
            await asyncio.sleep(self._delay)
        return {"content": self._content}


@pytest.mark.asyncio
async def test_fast_ack_refiner_returns_llm_refinement() -> None:
    llm = _FakeLLM(content="Got it! I'll review your reference and standardize the design system.")
    refiner = FastAcknowledgmentRefiner(llm=llm, fallback_generator=AcknowledgmentGenerator(), timeout_seconds=1.0)

    result = await refiner.generate("use code.html as reference and standardize buttons/colors")
    assert result.startswith("Got it!")
    assert "standardize" in result.lower()


@pytest.mark.asyncio
async def test_fast_ack_refiner_adds_got_it_prefix_when_missing() -> None:
    llm = _FakeLLM(content="I will research the best debugging prompt skills for Claude when coding.")
    refiner = FastAcknowledgmentRefiner(llm=llm, fallback_generator=AcknowledgmentGenerator(), timeout_seconds=1.0)

    result = await refiner.generate("research online best debugging prompt skills for claude code")
    assert result.startswith("Got it!")


@pytest.mark.asyncio
async def test_fast_ack_refiner_falls_back_on_timeout() -> None:
    llm = _FakeLLM(content="Got it! delayed", delay=0.2)
    fallback_gen = AcknowledgmentGenerator()
    refiner = FastAcknowledgmentRefiner(llm=llm, fallback_generator=fallback_gen, timeout_seconds=0.01)

    user_message = "create a research report on docker cleanup app"
    result = await refiner.generate(user_message)
    assert result == fallback_gen.generate(user_message)


@pytest.mark.asyncio
async def test_fast_ack_refiner_falls_back_on_error() -> None:
    llm = _FakeLLM(raises=RuntimeError("llm down"))
    fallback_gen = AcknowledgmentGenerator()
    refiner = FastAcknowledgmentRefiner(llm=llm, fallback_generator=fallback_gen, timeout_seconds=1.0)

    user_message = "research online best code review tools"
    result = await refiner.generate(user_message)
    assert result == fallback_gen.generate(user_message)


@pytest.mark.asyncio
async def test_fast_ack_refiner_sanitizes_numbered_topic_suffix() -> None:
    llm = _FakeLLM(
        content="Got it! I will create a comprehensive research report on report that covers the following topics: 1"
    )
    refiner = FastAcknowledgmentRefiner(llm=llm, fallback_generator=AcknowledgmentGenerator(), timeout_seconds=1.0)

    result = await refiner.generate("Create a comprehensive research report on the following topics")
    assert "on report that covers" not in result.lower()
    assert "following topics: 1" not in result.lower()
    assert "the following topics" in result.lower()


@pytest.mark.asyncio
async def test_fast_ack_refiner_prefers_specific_fallback_for_generic_topics_ack() -> None:
    llm = _FakeLLM(content="Got it! I will create a comprehensive research report on the following topics.")
    fallback_gen = AcknowledgmentGenerator()
    refiner = FastAcknowledgmentRefiner(llm=llm, fallback_generator=fallback_gen, timeout_seconds=1.0)

    user_message = (
        "Create a comprehensive research report that covers the following topics: "
        "1. LLM architecture. "
        "2. Tokenizers used in LLMs."
    )
    result = await refiner.generate(user_message)
    assert result == fallback_gen.generate(user_message)
    assert "llm architecture" in result.lower()
    assert "tokenizers used in llms" in result.lower()


# ─── _sanitize unit tests ───


class TestSanitize:
    """Direct unit tests for the _sanitize method."""

    def _make_refiner(self) -> FastAcknowledgmentRefiner:
        return FastAcknowledgmentRefiner(
            llm=_FakeLLM(), fallback_generator=AcknowledgmentGenerator(), timeout_seconds=1.0
        )

    def test_empty_string(self) -> None:
        r = self._make_refiner()
        assert r._sanitize("") == ""

    def test_none_input(self) -> None:
        r = self._make_refiner()
        assert r._sanitize(None) == ""

    def test_prepends_got_it(self) -> None:
        r = self._make_refiner()
        assert r._sanitize("I will research this.").startswith("Got it!")

    def test_preserves_got_it_prefix(self) -> None:
        r = self._make_refiner()
        result = r._sanitize("Got it! I will research this.")
        assert result.startswith("Got it!")
        assert not result.startswith("Got it! Got it!")

    def test_strips_reddit_mention(self) -> None:
        r = self._make_refiner()
        result = r._sanitize("Got it! I will research this by searching Reddit and Google for results.")
        assert "reddit" not in result.lower()
        assert "google" not in result.lower()

    def test_strips_stack_overflow_mention(self) -> None:
        r = self._make_refiner()
        result = r._sanitize("Got it! I will look into this on Stack Overflow and forums.")
        assert "stack overflow" not in result.lower()
        assert "forums" not in result.lower()

    def test_replaces_reddit_research_with_online(self) -> None:
        r = self._make_refiner()
        result = r._sanitize("Got it! I will use Reddit research to find answers.")
        assert "reddit" not in result.lower()
        assert "online research" in result.lower()

    def test_truncates_at_300_chars(self) -> None:
        r = self._make_refiner()
        long_text = "Got it! " + "word " * 100
        result = r._sanitize(long_text)
        assert len(result) <= 301  # 300 + possible trailing period

    def test_truncated_text_ends_with_punctuation(self) -> None:
        r = self._make_refiner()
        long_text = "Got it! " + "word " * 100
        result = r._sanitize(long_text)
        assert result[-1] in ".!?"

    def test_fixes_on_following_topics_phrasing(self) -> None:
        r = self._make_refiner()
        result = r._sanitize("Got it! I will create a report on following topics.")
        assert "on the following topics" in result.lower()

    def test_strips_numbered_suffix_from_topics(self) -> None:
        r = self._make_refiner()
        result = r._sanitize("Got it! I will cover the following topics: 1")
        assert not result.endswith(": 1")
        assert "following topics" in result.lower()

    def test_collapses_double_spaces(self) -> None:
        r = self._make_refiner()
        result = r._sanitize("Got it!  I  will   research  this.")
        assert "  " not in result


# ─── _should_prefer_fallback ───


class TestShouldPreferFallback:
    def _make_refiner(self) -> FastAcknowledgmentRefiner:
        return FastAcknowledgmentRefiner(
            llm=_FakeLLM(), fallback_generator=AcknowledgmentGenerator(), timeout_seconds=1.0
        )

    def test_specific_refined_not_replaced(self) -> None:
        r = self._make_refiner()
        assert not r._should_prefer_fallback("Got it! I will research AI IDEs.", "Got it! I will help with that.")

    def test_generic_refined_replaced_by_specific_fallback(self) -> None:
        r = self._make_refiner()
        assert r._should_prefer_fallback(
            "Got it! I will create a report on the following topics.", "Got it! I will research AI IDEs."
        )

    def test_both_generic_not_replaced(self) -> None:
        r = self._make_refiner()
        assert not r._should_prefer_fallback(
            "Got it! I will cover on the following topics.",
            "Got it! I will cover on the following items.",
        )


# ─── _is_generic_topics_ack ───


class TestIsGenericTopicsAck:
    def _make_refiner(self) -> FastAcknowledgmentRefiner:
        return FastAcknowledgmentRefiner(
            llm=_FakeLLM(), fallback_generator=AcknowledgmentGenerator(), timeout_seconds=1.0
        )

    def test_matches_on_following_topics(self) -> None:
        r = self._make_refiner()
        assert r._is_generic_topics_ack("Got it! I will create a report on the following topics.")

    def test_matches_on_following_items(self) -> None:
        r = self._make_refiner()
        assert r._is_generic_topics_ack("I will cover on the following items.")

    def test_matches_on_following_sections(self) -> None:
        r = self._make_refiner()
        assert r._is_generic_topics_ack("Report on the following sections.")

    def test_no_match_specific(self) -> None:
        r = self._make_refiner()
        assert not r._is_generic_topics_ack("Got it! I will research AI IDEs and code review tools.")


# ─── _should_sample_traceback ───


class TestShouldSampleTraceback:
    def test_zero_rate_never_samples(self) -> None:
        r = FastAcknowledgmentRefiner(
            llm=_FakeLLM(),
            fallback_generator=AcknowledgmentGenerator(),
            timeout_seconds=1.0,
            traceback_sample_rate=0.0,
        )
        r._error_count = 1
        assert not r._should_sample_traceback()

    def test_full_rate_always_samples(self) -> None:
        r = FastAcknowledgmentRefiner(
            llm=_FakeLLM(),
            fallback_generator=AcknowledgmentGenerator(),
            timeout_seconds=1.0,
            traceback_sample_rate=1.0,
        )
        r._error_count = 1
        assert r._should_sample_traceback()

    def test_fifth_error_sampled_at_20_percent(self) -> None:
        r = FastAcknowledgmentRefiner(
            llm=_FakeLLM(),
            fallback_generator=AcknowledgmentGenerator(),
            timeout_seconds=1.0,
            traceback_sample_rate=0.2,
        )
        # interval = round(1/0.2) = 5, so every 5th error is sampled
        r._error_count = 5
        assert r._should_sample_traceback()
        r._error_count = 3
        assert not r._should_sample_traceback()


@pytest.mark.asyncio
async def test_fast_ack_refiner_handles_keys_exhausted() -> None:
    from app.domain.exceptions.base import LLMKeysExhaustedError

    llm = _FakeLLM(raises=LLMKeysExhaustedError("no keys", key_count=0))
    fallback_gen = AcknowledgmentGenerator()
    refiner = FastAcknowledgmentRefiner(llm=llm, fallback_generator=fallback_gen, timeout_seconds=1.0)

    result = await refiner.generate("research AI tools")
    assert result == fallback_gen.generate("research AI tools")
