"""Domain-level alerting port.

Allows domain flows to check alert thresholds without importing
the concrete AlertManager from app.core.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AlertPort(Protocol):
    """Fire-and-forget alert interface for the domain layer."""

    def check_thresholds(self, session_id: str, metrics: dict[str, Any]) -> None:
        """Evaluate metrics against configured thresholds.

        Implementations may log, send notifications, or no-op.
        """
        ...
