from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import get_settings as _get_settings
from app.domain.models.event import MessageEvent, UsageEvent
from app.domain.services.agents.base import BaseAgent


def _build_agent(*, llm: object) -> BaseAgent:
    repo = AsyncMock()
    repo.get_memory = AsyncMock(
        return_value=MagicMock(
            empty=True,
            get_messages=MagicMock(return_value=[]),
            add_message=MagicMock(),
            add_messages=MagicMock(),
        )
    )
    repo.save_memory = AsyncMock()

    parser = AsyncMock()
    parser.parse = AsyncMock(return_value={})

    return BaseAgent(
        agent_id="agent-usage-test",
        agent_repository=repo,
        llm=llm,  # type: ignore[arg-type]
        json_parser=parser,  # type: ignore[arg-type]
        tools=[],
    )


@pytest.mark.asyncio
async def test_execute_emits_usage_event_after_final_message(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _get_settings().model_copy(
        update={
            "llm_input_price_per_million": 1.5,
            "llm_output_price_per_million": 2.5,
        }
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)

    llm = MagicMock()
    llm.model_name = "gpt-4"
    llm.max_tokens = 2048
    llm.ask = AsyncMock(return_value={"role": "assistant", "content": "done"})

    agent = _build_agent(llm=llm)

    events = [event async for event in agent.execute("say hello")]

    assert len(events) == 2
    assert isinstance(events[0], MessageEvent)
    assert events[0].message == "done"
    assert isinstance(events[1], UsageEvent)
    assert events[1].iterations == 1
    assert events[1].prompt_tokens > 0
    assert events[1].completion_tokens > 0
    assert events[1].duration_seconds >= 0.0
    expected_cost = (events[1].prompt_tokens / 1_000_000) * 1.5 + (events[1].completion_tokens / 1_000_000) * 2.5
    assert events[1].estimated_cost_usd == pytest.approx(expected_cost)
