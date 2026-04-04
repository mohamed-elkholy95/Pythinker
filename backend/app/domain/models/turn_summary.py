"""Turn-level summary contract for agent execution.

This is a small, stable data structure intended to be returned by a turn runner
and/or emitted as a usage event at the end of a turn.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TurnSummary:
    iterations: int
    tools_called: list[str]
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    duration_seconds: float
