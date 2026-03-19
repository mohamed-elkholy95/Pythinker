"""Middleware adapter for token budget management."""

from __future__ import annotations

from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
)


class TokenBudgetMiddleware(BaseMiddleware):
    """Checks token budget and forces conclusion when exhausted."""

    FORCE_CONCLUDE_RATIO: float = 0.95
    HARD_STOP_RATIO: float = 0.99

    @property
    def name(self) -> str:
        return "token_budget"

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        if ctx.token_budget_ratio >= self.HARD_STOP_RATIO:
            return MiddlewareResult(
                signal=MiddlewareSignal.FORCE,
                message="TOKEN BUDGET EMERGENCY (99%+). Provide final summary now.",
            )
        if ctx.token_budget_ratio >= self.FORCE_CONCLUDE_RATIO:
            return MiddlewareResult(
                signal=MiddlewareSignal.INJECT,
                message="TOKEN BUDGET CRITICAL (95%+). Conclude current step now.",
            )
        return MiddlewareResult.ok()

    async def before_model(self, ctx: MiddlewareContext) -> MiddlewareResult:
        if ctx.token_budget_ratio >= self.HARD_STOP_RATIO:
            return MiddlewareResult(
                signal=MiddlewareSignal.FORCE,
                message="Token budget exhausted. Cannot make LLM call.",
            )
        return MiddlewareResult.ok()
