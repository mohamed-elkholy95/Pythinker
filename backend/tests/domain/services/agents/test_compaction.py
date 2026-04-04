from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.services.agents.base import BaseAgent
from app.domain.services.agents.compaction import CompactionConfig, CompactionResult, CompactionStrategy
from app.domain.services.agents.memory_manager import ContextOptimizationReport, MemoryManager


def _build_agent() -> tuple[BaseAgent, AsyncMock, MagicMock]:
    repo = AsyncMock()
    memory = MagicMock()
    memory.get_messages.return_value = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
        {"role": "tool", "function_name": "file_read", "content": "tool output"},
    ]
    memory.messages = list(memory.get_messages.return_value)
    repo.get_memory = AsyncMock(return_value=memory)
    repo.save_memory = AsyncMock()

    llm = MagicMock()
    llm.model_name = "gpt-4"

    parser = AsyncMock()
    parser.parse = AsyncMock(return_value={})

    agent = BaseAgent(
        agent_id="agent-compaction-test",
        agent_repository=repo,
        llm=llm,  # type: ignore[arg-type]
        json_parser=parser,  # type: ignore[arg-type]
    )
    return agent, repo, memory


def test_compaction_config_defaults_match_plan() -> None:
    config = CompactionConfig()

    assert config.strategy == CompactionStrategy.SUMMARIZE
    assert config.target_tokens == 8_000
    assert config.preserve_last_n_messages == 6


@pytest.mark.asyncio
async def test_compact_truncate_uses_trim_messages_and_saves_memory() -> None:
    agent, repo, memory = _build_agent()
    original_messages = list(memory.get_messages.return_value)
    trimmed_messages = original_messages[-2:]

    agent._token_manager.count_messages_tokens = MagicMock(side_effect=[120, 40])

    trim_manager = MagicMock()
    trim_manager.trim_messages.return_value = (trimmed_messages, 80)

    with patch("app.domain.services.agents.base.TokenManager", return_value=trim_manager):
        result = await agent.compact(
            CompactionConfig(
                strategy=CompactionStrategy.TRUNCATE,
                target_tokens=40,
                preserve_last_n_messages=2,
            )
        )

    assert result == CompactionResult(
        tokens_before=120,
        tokens_after=40,
        messages_removed=2,
        strategy_used=CompactionStrategy.TRUNCATE,
    )
    assert memory.messages == trimmed_messages
    trim_manager.trim_messages.assert_called_once_with(
        original_messages,
        preserve_system=True,
        preserve_recent=2,
    )
    repo.save_memory.assert_awaited_once_with(agent._agent_id, agent.name, memory)


@pytest.mark.asyncio
async def test_compact_summarize_uses_structured_compact() -> None:
    agent, repo, memory = _build_agent()
    summarized_messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "summary"},
    ]

    agent._token_manager.count_messages_tokens = MagicMock(side_effect=[100, 30])

    with patch.object(
        MemoryManager,
        "structured_compact",
        new=AsyncMock(return_value=(summarized_messages, 70)),
    ) as structured_compact:
        result = await agent.compact(
            CompactionConfig(
                strategy=CompactionStrategy.SUMMARIZE,
                preserve_last_n_messages=4,
            )
        )

    assert result.strategy_used == CompactionStrategy.SUMMARIZE
    assert result.tokens_before == 100
    assert result.tokens_after == 30
    assert result.messages_removed == 2
    assert memory.messages == summarized_messages
    structured_compact.assert_awaited_once_with(memory.get_messages.return_value, agent.llm, preserve_recent=4)
    repo.save_memory.assert_awaited_once_with(agent._agent_id, agent.name, memory)


@pytest.mark.asyncio
async def test_compact_semantic_uses_optimize_context() -> None:
    agent, repo, memory = _build_agent()
    optimized_messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "optimized"},
        {"role": "assistant", "content": "recent"},
    ]
    report = ContextOptimizationReport(
        tokens_before=150,
        tokens_after=90,
        semantic_compacted=1,
        temporal_compacted=0,
    )

    agent._token_manager.count_messages_tokens = MagicMock(side_effect=[150, 90])

    with patch.object(
        MemoryManager,
        "optimize_context",
        return_value=(optimized_messages, report),
    ) as optimize_context:
        result = await agent.compact(
            CompactionConfig(
                strategy=CompactionStrategy.SEMANTIC,
                target_tokens=90,
                preserve_last_n_messages=5,
            )
        )

    assert result == CompactionResult(
        tokens_before=150,
        tokens_after=90,
        messages_removed=1,
        strategy_used=CompactionStrategy.SEMANTIC,
    )
    assert memory.messages == optimized_messages
    optimize_context.assert_called_once_with(
        memory.get_messages.return_value,
        preserve_recent=5,
        token_threshold=90,
    )
    repo.save_memory.assert_awaited_once_with(agent._agent_id, agent.name, memory)
