"""Tests for AgentServiceContext."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domain.services.agents.agent_context import AgentServiceContext
from app.domain.services.agents.middleware import AgentMiddleware, MiddlewareResult
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline


def _make_mock_middleware(name: str) -> MagicMock:
    """Create a mock middleware with the given name."""
    mw = MagicMock(spec=AgentMiddleware)
    mw.name = name
    return mw


def _make_pipeline(middleware: list[MagicMock] | None = None) -> MiddlewarePipeline:
    return MiddlewarePipeline(middleware=middleware or [])


class TestAgentServiceContextConstruction:
    def test_stores_middleware_pipeline(self) -> None:
        pipeline = _make_pipeline()
        metrics = MagicMock()
        ctx = AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=metrics,
            feature_flags={},
        )
        assert ctx.middleware_pipeline is pipeline

    def test_stores_metrics(self) -> None:
        pipeline = _make_pipeline()
        metrics = MagicMock()
        ctx = AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=metrics,
            feature_flags={},
        )
        assert ctx.metrics is metrics

    def test_stores_feature_flags(self) -> None:
        pipeline = _make_pipeline()
        flags = {"feature_a": True, "feature_b": False}
        ctx = AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=MagicMock(),
            feature_flags=flags,
        )
        assert ctx.feature_flags == flags

    def test_empty_feature_flags(self) -> None:
        ctx = AgentServiceContext(
            middleware_pipeline=_make_pipeline(),
            metrics=MagicMock(),
            feature_flags={},
        )
        assert ctx.feature_flags == {}


class TestAgentServiceContextGetMiddleware:
    def test_get_middleware_found(self) -> None:
        mw = _make_mock_middleware("security_assessment")
        pipeline = _make_pipeline([mw])
        ctx = AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=MagicMock(),
            feature_flags={},
        )
        result = ctx.get_middleware("security_assessment")
        assert result is mw

    def test_get_middleware_not_found_returns_none(self) -> None:
        mw = _make_mock_middleware("tool_budget")
        pipeline = _make_pipeline([mw])
        ctx = AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=MagicMock(),
            feature_flags={},
        )
        result = ctx.get_middleware("nonexistent")
        assert result is None

    def test_get_middleware_empty_pipeline_returns_none(self) -> None:
        ctx = AgentServiceContext(
            middleware_pipeline=_make_pipeline(),
            metrics=MagicMock(),
            feature_flags={},
        )
        assert ctx.get_middleware("anything") is None

    def test_get_middleware_finds_correct_one_among_multiple(self) -> None:
        mw_a = _make_mock_middleware("alpha")
        mw_b = _make_mock_middleware("beta")
        mw_c = _make_mock_middleware("gamma")
        pipeline = _make_pipeline([mw_a, mw_b, mw_c])
        ctx = AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=MagicMock(),
            feature_flags={},
        )
        assert ctx.get_middleware("beta") is mw_b

    def test_feature_flags_accessible_after_construction(self) -> None:
        ctx = AgentServiceContext(
            middleware_pipeline=_make_pipeline(),
            metrics=MagicMock(),
            feature_flags={"adaptive_model": True},
        )
        assert ctx.feature_flags["adaptive_model"] is True
