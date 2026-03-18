"""
Speculative execution module for advanced execution strategies.

Provides speculative execution and other optimizations.
"""

from app.domain.services.agents.speculative.executor import (
    SpeculativeExecutor,
    SpeculativeResult,
    get_speculative_executor,
)

__all__ = [
    "SpeculativeExecutor",
    "SpeculativeResult",
    "get_speculative_executor",
]
