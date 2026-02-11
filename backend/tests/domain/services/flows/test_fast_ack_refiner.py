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
