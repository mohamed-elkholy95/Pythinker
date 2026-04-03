"""Factory that builds session-scoped AgentServiceContext."""

from __future__ import annotations

import logging

from app.domain.external.observability import MetricsPort
from app.domain.services.agents.agent_context import AgentServiceContext
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline

logger = logging.getLogger(__name__)


class AgentContextFactory:
    """Builds session-scoped service contexts with configured middleware.

    Middleware order (to be populated in Task 11):
    1. WallClockPressure  2. TokenBudget  3. SecurityAssessment
    4. HallucinationGuard 5. EfficiencyMonitor 6. UrlFailureGuard
    7. StuckDetection 8. ErrorHandler
    """

    def create(
        self,
        agent_id: str,
        session_id: str,
        tools: list | None = None,
        research_mode: str | None = None,
        feature_flags: dict[str, bool] | None = None,
    ) -> AgentServiceContext:
        """Create a session-scoped context with all middleware registered."""
        flags = feature_flags or self._load_feature_flags()
        pipeline = MiddlewarePipeline()

        # Order: cheapest/most critical first
        from app.domain.services.agents.hallucination_detector import ToolHallucinationDetector
        from app.domain.services.agents.middleware_adapters.efficiency_monitor import EfficiencyMonitorMiddleware
        from app.domain.services.agents.middleware_adapters.error_handler import ErrorHandlerMiddleware
        from app.domain.services.agents.middleware_adapters.hallucination_guard import HallucinationGuardMiddleware
        from app.domain.services.agents.middleware_adapters.security_assessment import SecurityAssessmentMiddleware
        from app.domain.services.agents.middleware_adapters.stuck_detection import StuckDetectionMiddleware
        from app.domain.services.agents.middleware_adapters.token_budget import TokenBudgetMiddleware
        from app.domain.services.agents.middleware_adapters.url_failure_guard import UrlFailureGuardMiddleware
        from app.domain.services.agents.middleware_adapters.wall_clock_pressure import WallClockPressureMiddleware

        tool_names = self._extract_tool_names(tools or [])

        pipeline.use(WallClockPressureMiddleware())
        pipeline.use(TokenBudgetMiddleware())
        pipeline.use(SecurityAssessmentMiddleware())
        pipeline.use(HallucinationGuardMiddleware(detector=ToolHallucinationDetector(tool_names)))
        pipeline.use(EfficiencyMonitorMiddleware(research_mode=research_mode))
        pipeline.use(UrlFailureGuardMiddleware())
        pipeline.use(StuckDetectionMiddleware())
        pipeline.use(ErrorHandlerMiddleware())

        return AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=self._get_metrics(),
            feature_flags=flags,
        )

    @staticmethod
    def _extract_tool_names(tools: list) -> list[str]:
        """Extract tool function names from tool objects."""
        names = []
        for tool in tools:
            if hasattr(tool, "get_tools"):
                for schema in tool.get_tools():
                    name = schema.get("function", {}).get("name", "")
                    if name:
                        names.append(name)
        return names

    @staticmethod
    def _load_feature_flags() -> dict[str, bool]:
        from app.core.config import get_feature_flags

        return get_feature_flags()

    @staticmethod
    def _get_metrics() -> MetricsPort:
        from app.domain.external.observability import get_null_metrics

        return get_null_metrics()
