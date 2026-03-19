"""Tests for AgentServiceContext and AgentContextFactory."""

from app.domain.services.agents.agent_context import AgentServiceContext
from app.domain.services.agents.agent_context_factory import AgentContextFactory
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline


class TestAgentServiceContext:
    def test_construction(self):
        pipeline = MiddlewarePipeline()
        from app.domain.external.observability import get_null_metrics

        ctx = AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=get_null_metrics(),
            feature_flags={"test": True},
        )
        assert ctx.feature_flags["test"] is True

    def test_get_middleware_by_name(self):
        class Named(BaseMiddleware):
            @property
            def name(self):
                return "my_mw"

        pipeline = MiddlewarePipeline([Named()])
        from app.domain.external.observability import get_null_metrics

        ctx = AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=get_null_metrics(),
            feature_flags={},
        )
        assert ctx.get_middleware("my_mw") is not None
        assert ctx.get_middleware("nonexistent") is None


class TestAgentContextFactory:
    def test_creates_context_with_empty_pipeline(self):
        factory = AgentContextFactory()
        ctx = factory.create(
            agent_id="test",
            session_id="test",
            feature_flags={"test_flag": True},
        )
        assert isinstance(ctx, AgentServiceContext)
        assert ctx.feature_flags["test_flag"] is True
        assert len(ctx.middleware_pipeline.middleware) == 0  # Empty until Task 11
