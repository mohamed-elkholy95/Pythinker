"""Tests for TokenBudgetMiddleware."""

import pytest

from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareSignal,
)
from app.domain.services.agents.middleware_adapters.token_budget import (
    TokenBudgetMiddleware,
)


@pytest.fixture
def mw():
    return TokenBudgetMiddleware()


@pytest.fixture
def ctx():
    return MiddlewareContext(agent_id="test", session_id="test")


class TestTokenBudgetName:
    def test_name(self, mw):
        assert mw.name == "token_budget"


class TestBeforeStep:
    @pytest.mark.asyncio
    async def test_below_threshold_returns_continue(self, mw, ctx):
        ctx.token_budget_ratio = 0.50
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_above_95_returns_inject(self, mw, ctx):
        ctx.token_budget_ratio = 0.96
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.INJECT

    @pytest.mark.asyncio
    async def test_above_99_returns_force(self, mw, ctx):
        ctx.token_budget_ratio = 0.995
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.FORCE

    @pytest.mark.asyncio
    async def test_exactly_at_99_returns_force(self, mw, ctx):
        ctx.token_budget_ratio = 0.99
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.FORCE


class TestBeforeModel:
    @pytest.mark.asyncio
    async def test_below_threshold_returns_continue(self, mw, ctx):
        ctx.token_budget_ratio = 0.50
        result = await mw.before_model(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_above_99_returns_force(self, mw, ctx):
        ctx.token_budget_ratio = 0.995
        result = await mw.before_model(ctx)
        assert result.signal == MiddlewareSignal.FORCE
