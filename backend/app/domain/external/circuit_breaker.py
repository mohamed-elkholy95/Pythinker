"""Circuit breaker port for protecting tool execution from cascading failures."""

from typing import Protocol


class CircuitBreakerPort(Protocol):
    """Domain-level circuit breaker interface.

    Tracks tool-level failures and prevents repeated calls to failing tools,
    allowing the system to use alternative approaches instead.
    """

    def can_execute(self, tool_name: str) -> bool:
        """Check if a tool call should proceed.

        Returns False when the circuit is open (tool has failed repeatedly).
        """
        ...

    def record_success(self, tool_name: str) -> None:
        """Record a successful tool call."""
        ...

    def record_failure(self, tool_name: str) -> None:
        """Record a failed tool call."""
        ...
