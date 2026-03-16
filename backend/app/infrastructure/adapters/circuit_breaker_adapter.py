"""Adapter bridging core CircuitBreakerRegistry to domain CircuitBreakerPort."""

import logging

from app.core.circuit_breaker_registry import CircuitBreakerRegistry

logger = logging.getLogger(__name__)


class ToolCircuitBreakerAdapter:
    """Per-tool circuit breaker using the core registry.

    Each tool gets its own circuit breaker keyed by tool name,
    so one failing tool doesn't block all others.
    """

    def can_execute(self, tool_name: str) -> bool:
        """Check if the tool's circuit is closed (safe to call)."""
        breaker = CircuitBreakerRegistry.get_or_create(f"tool:{tool_name}")
        return breaker.can_execute()

    def record_success(self, tool_name: str) -> None:
        """Record successful tool execution."""
        breaker = CircuitBreakerRegistry.get_or_create(f"tool:{tool_name}")
        breaker.record_success()

    def record_failure(self, tool_name: str) -> None:
        """Record failed tool execution."""
        breaker = CircuitBreakerRegistry.get_or_create(f"tool:{tool_name}")
        breaker.record_failure()
