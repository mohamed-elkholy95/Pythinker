"""Turn-level compaction contract for agent memory."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CompactionStrategy(StrEnum):
    """Supported memory compaction strategies."""

    TRUNCATE = "truncate"
    SUMMARIZE = "summarize"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class CompactionConfig:
    """Configuration for a single compaction request."""

    strategy: CompactionStrategy = CompactionStrategy.SUMMARIZE
    target_tokens: int = 8_000
    preserve_last_n_messages: int = 6


@dataclass(frozen=True)
class CompactionResult:
    """Outcome of a compaction run."""

    tokens_before: int
    tokens_after: int
    messages_removed: int
    strategy_used: CompactionStrategy
