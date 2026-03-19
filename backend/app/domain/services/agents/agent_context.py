"""Session-scoped service container for agent middleware and services."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.external.observability import MetricsPort
from app.domain.services.agents.middleware import AgentMiddleware
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline


@dataclass(slots=True)
class AgentServiceContext:
    """All services needed by an agent, scoped to a single session."""

    middleware_pipeline: MiddlewarePipeline
    metrics: MetricsPort
    feature_flags: dict[str, bool]

    def get_middleware(self, name: str) -> AgentMiddleware | None:
        """Retrieve a specific middleware by name for introspection/stats."""
        for mw in self.middleware_pipeline.middleware:
            if mw.name == name:
                return mw
        return None
