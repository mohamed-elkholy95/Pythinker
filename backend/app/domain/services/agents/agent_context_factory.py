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

        # Middleware adapters will be registered here as they are implemented.
        # For now, pipeline is empty (backward compatible).

        return AgentServiceContext(
            middleware_pipeline=pipeline,
            metrics=self._get_metrics(),
            feature_flags=flags,
        )

    @staticmethod
    def _load_feature_flags() -> dict[str, bool]:
        from app.core.config import get_feature_flags

        return get_feature_flags()

    @staticmethod
    def _get_metrics() -> MetricsPort:
        from app.domain.external.observability import get_null_metrics

        return get_null_metrics()
