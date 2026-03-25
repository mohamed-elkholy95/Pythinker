"""Domain Logging Port - Structured agent logging interface.

Provides a standardized logging interface for agent operations,
tool calls, and workflow transitions with automatic context binding.
"""

import logging
import time
from typing import Any


class AgentLogger:
    """Structured logger for agent operations.

    Binds agent_id and session_id to all log entries automatically.
    Provides domain-specific logging methods for tool calls,
    agent steps, and workflow transitions.
    """

    def __init__(self, agent_id: str, session_id: str | None = None):
        self._logger = logging.getLogger(f"agent.{agent_id}")
        self._agent_id = agent_id
        self._session_id = session_id

    def _extra(self, **kwargs: Any) -> dict[str, Any]:
        """Build extra dict with automatic context fields."""
        base: dict[str, Any] = {"agent_id": self._agent_id}
        if self._session_id:
            base["session_id"] = self._session_id
        base.update(kwargs)
        return base

    def tool_started(
        self,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> float:
        """Log tool execution start. Returns start_time for duration calc."""
        start = time.time()
        safe_args = _truncate_args(arguments) if arguments else {}
        self._logger.info(
            "tool_started: %s",
            tool_name,
            extra=self._extra(
                event="tool_started",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                arguments=safe_args,
            ),
        )
        return start

    def tool_completed(
        self,
        tool_name: str,
        tool_call_id: str,
        start_time: float,
        success: bool,
        message: str | None = None,
    ) -> None:
        """Log tool execution completion with duration."""
        duration_ms = (time.time() - start_time) * 1000
        log_fn = self._logger.info if success else self._logger.warning
        log_fn(
            "tool_completed: %s (%.0fms, success=%s)",
            tool_name,
            duration_ms,
            success,
            extra=self._extra(
                event="tool_completed",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                duration_ms=round(duration_ms, 2),
                success=success,
                result_message=message[:200] if message else None,
            ),
        )
        # Record Prometheus tool metrics
        try:
            from app.core.prometheus_metrics import record_tool_call

            record_tool_call(
                tool=tool_name,
                status="success" if success else "error",
                latency=duration_ms / 1000.0,
            )
        except Exception:
            pass  # Telemetry must not crash tool execution

    def tool_failed(
        self,
        tool_name: str,
        tool_call_id: str,
        error: str,
        start_time: float | None = None,
    ) -> None:
        """Log tool execution failure."""
        duration_ms = (time.time() - start_time) * 1000 if start_time else None
        self._logger.error(
            "tool_failed: %s - %s",
            tool_name,
            error[:200],
            extra=self._extra(
                event="tool_failed",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error=error[:500],
                duration_ms=round(duration_ms, 2) if duration_ms else None,
            ),
        )

    def agent_step(
        self,
        step: str,
        iteration: int,
        token_usage: dict[str, int] | None = None,
    ) -> None:
        """Log an agent iteration/step."""
        self._logger.info(
            "agent_step: %s (iter=%d)",
            step,
            iteration,
            extra=self._extra(
                event="agent_step",
                step=step,
                iteration=iteration,
                token_usage=token_usage,
            ),
        )

    def workflow_transition(
        self,
        from_state: str,
        to_state: str,
        reason: str | None = None,
    ) -> None:
        """Log a workflow state transition."""
        self._logger.info(
            "workflow_transition: %s -> %s",
            from_state,
            to_state,
            extra=self._extra(
                event="workflow_transition",
                from_state=from_state,
                to_state=to_state,
                reason=reason,
            ),
        )

    def security_event(
        self,
        action: str,
        tool_name: str,
        reason: str,
    ) -> None:
        """Log a security-related event (blocked tool, risk assessment)."""
        self._logger.warning(
            "security_event: %s on %s - %s",
            action,
            tool_name,
            reason,
            extra=self._extra(
                event="security_event",
                action=action,
                tool_name=tool_name,
                reason=reason,
            ),
        )

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Structured debug log."""
        self._logger.debug(msg, extra=self._extra(**kwargs))

    def info(self, msg: str, **kwargs: Any) -> None:
        """Structured info log."""
        self._logger.info(msg, extra=self._extra(**kwargs))

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Structured warning log."""
        self._logger.warning(msg, extra=self._extra(**kwargs))

    def error(self, msg: str, **kwargs: Any) -> None:
        """Structured error log."""
        self._logger.error(msg, extra=self._extra(**kwargs))


def _truncate_args(args: dict[str, Any], max_value_len: int = 100) -> dict[str, Any]:
    """Truncate argument values for safe logging."""
    result = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > max_value_len:
            result[k] = v[:max_value_len] + "..."
        else:
            result[k] = v
    return result


def get_agent_logger(agent_id: str, session_id: str | None = None) -> AgentLogger:
    """Factory function for AgentLogger.

    Args:
        agent_id: Agent identifier for log correlation
        session_id: Optional session identifier

    Returns:
        AgentLogger bound to the given agent context
    """
    return AgentLogger(agent_id, session_id)
