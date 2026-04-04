"""Tests for middleware pipeline routing in BaseAgent execute loop."""

from unittest.mock import MagicMock

from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline


class TestBaseAgentHasPipeline:
    """Verify BaseAgent constructs a middleware pipeline."""

    def test_base_agent_has_pipeline(self):
        from app.domain.services.agents.base import BaseAgent

        agent = BaseAgent(
            agent_id="test",
            agent_repository=MagicMock(),
            llm=MagicMock(),
            json_parser=MagicMock(),
            tools=[],
        )
        assert hasattr(agent, "_pipeline")
        assert isinstance(agent._pipeline, MiddlewarePipeline)

    def test_default_pipeline_has_6_middleware(self):
        from app.domain.services.agents.base import BaseAgent

        agent = BaseAgent(
            agent_id="test",
            agent_repository=MagicMock(),
            llm=MagicMock(),
            json_parser=MagicMock(),
            tools=[],
        )
        names = [mw.name for mw in agent._pipeline.middleware]
        assert "security_assessment" in names
        assert "permission_gate" in names
        assert "hallucination_guard" in names
        assert "efficiency_monitor" in names
        assert "stuck_detection" in names
        assert "error_handler" in names
        assert len(names) == 6

    def test_injected_service_context_overrides_default(self):
        from app.domain.external.observability import get_null_metrics
        from app.domain.services.agents.agent_context import AgentServiceContext
        from app.domain.services.agents.base import BaseAgent

        custom_pipeline = MiddlewarePipeline()
        ctx = AgentServiceContext(
            middleware_pipeline=custom_pipeline,
            metrics=get_null_metrics(),
            feature_flags={},
        )
        agent = BaseAgent(
            agent_id="test",
            agent_repository=MagicMock(),
            llm=MagicMock(),
            json_parser=MagicMock(),
            tools=[],
            service_context=ctx,
        )
        assert agent._pipeline is custom_pipeline
        assert len(agent._pipeline.middleware) == 0
