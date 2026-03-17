"""Analytics service for agent monitoring dashboards.

Provides aggregated metrics and analytics queries for monitoring
agent performance, workflow efficiency, and tool usage.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Provides analytics queries for dashboards."""

    async def get_workflow_efficiency_metrics(self, days: int = 7) -> dict[str, Any]:
        """Calculate workflow efficiency metrics.

        Args:
            days: Number of days to analyze

        Returns:
            Workflow efficiency metrics
        """
        from app.infrastructure.models.documents import WorkflowStateDocument

        cutoff_date = datetime.now(UTC) - timedelta(days=days)

        workflow_states = await WorkflowStateDocument.find(WorkflowStateDocument.timestamp >= cutoff_date).to_list()

        if not workflow_states:
            return {
                "completion_rate": 0.0,
                "replanning_frequency": 0.0,
                "stuck_loop_occurrence": 0.0,
            }

        # Group by session
        sessions = {}
        for state in workflow_states:
            if state.session_id not in sessions:
                sessions[state.session_id] = []
            sessions[state.session_id].append(state)

        # Calculate metrics
        completed = sum(1 for states in sessions.values() if any(s.current_status == "COMPLETED" for s in states))
        completion_rate = completed / len(sessions) if sessions else 0

        # Replanning frequency (sessions with multiple PLANNING states)
        replanning_count = sum(
            1 for states in sessions.values() if sum(1 for s in states if s.current_status == "PLANNING") > 1
        )
        replanning_frequency = replanning_count / len(sessions) if sessions else 0

        # Stuck loop occurrence
        stuck_count = sum(1 for states in sessions.values() if any(s.stuck_loop_detected for s in states))
        stuck_loop_occurrence = stuck_count / len(sessions) if sessions else 0

        return {
            "period_days": days,
            "total_sessions": len(sessions),
            "completion_rate": completion_rate,
            "replanning_frequency": replanning_frequency,
            "stuck_loop_occurrence": stuck_loop_occurrence,
            "avg_state_transitions": sum(len(s) for s in sessions.values()) / len(sessions) if sessions else 0,
        }

    async def get_tool_performance_breakdown(self) -> dict[str, Any]:
        """Get tool success rates and performance.

        Returns:
            Tool performance breakdown
        """
        from collections import defaultdict

        from app.infrastructure.models.documents import ToolExecutionDocument

        cutoff_date = datetime.now(UTC) - timedelta(days=7)

        tool_executions = await ToolExecutionDocument.find(ToolExecutionDocument.started_at >= cutoff_date).to_list()

        if not tool_executions:
            return {"tools": []}

        # Aggregate by tool
        tool_stats: defaultdict = defaultdict(
            lambda: {
                "total": 0,
                "success": 0,
                "failures": 0,
                "total_duration_ms": 0,
                "retry_count": 0,
            }
        )

        for execution in tool_executions:
            stats = tool_stats[execution.tool_name]
            stats["total"] += 1
            if execution.success:
                stats["success"] += 1
            else:
                stats["failures"] += 1
            if execution.duration_ms:
                stats["total_duration_ms"] += execution.duration_ms
            stats["retry_count"] += execution.retry_count

        # Build results
        tools = []
        for tool_name, stats in sorted(tool_stats.items(), key=lambda x: x[1]["total"], reverse=True):
            tools.append(
                {
                    "tool_name": tool_name,
                    "total_executions": stats["total"],
                    "success_rate": stats["success"] / stats["total"] if stats["total"] > 0 else 0,
                    "failure_rate": stats["failures"] / stats["total"] if stats["total"] > 0 else 0,
                    "avg_duration_ms": stats["total_duration_ms"] / stats["total"] if stats["total"] > 0 else 0,
                    "avg_retries": stats["retry_count"] / stats["total"] if stats["total"] > 0 else 0,
                }
            )

        return {
            "tools": tools,
            "total_tool_executions": sum(t["total_executions"] for t in tools),
        }

    async def get_mode_selection_accuracy(self) -> dict[str, Any]:
        """Analyze mode selection decisions.

        Returns:
            Mode selection accuracy metrics
        """
        from app.domain.services.analyzers.pattern_detector import get_pattern_detector

        detector = get_pattern_detector()
        return await detector.detect_mode_selection_accuracy()

    async def get_resource_usage_summary(self) -> dict[str, Any]:
        """Get resource usage summary across sessions.

        Returns:
            Resource usage metrics
        """
        from app.infrastructure.models.documents import ToolExecutionDocument

        cutoff_date = datetime.now(UTC) - timedelta(days=7)

        tool_executions = await ToolExecutionDocument.find(
            ToolExecutionDocument.started_at >= cutoff_date,
        ).to_list()

        # Filter for executions with resource data
        with_resources = [
            t for t in tool_executions if t.container_cpu_percent is not None or t.container_memory_mb is not None
        ]

        if not with_resources:
            return {
                "avg_cpu_percent": 0.0,
                "avg_memory_mb": 0.0,
                "peak_cpu_percent": 0.0,
                "peak_memory_mb": 0.0,
            }

        cpu_values = [t.container_cpu_percent for t in with_resources if t.container_cpu_percent is not None]
        memory_values = [t.container_memory_mb for t in with_resources if t.container_memory_mb is not None]

        return {
            "avg_cpu_percent": sum(cpu_values) / len(cpu_values) if cpu_values else 0,
            "avg_memory_mb": sum(memory_values) / len(memory_values) if memory_values else 0,
            "peak_cpu_percent": max(cpu_values) if cpu_values else 0,
            "peak_memory_mb": max(memory_values) if memory_values else 0,
            "samples_collected": len(with_resources),
        }

    async def get_error_breakdown(self, days: int = 7) -> dict[str, Any]:
        """Get error breakdown by type.

        Args:
            days: Number of days to analyze

        Returns:
            Error breakdown metrics
        """
        from collections import Counter

        from app.infrastructure.models.documents import ToolExecutionDocument

        cutoff_date = datetime.now(UTC) - timedelta(days=days)

        failed_executions = await ToolExecutionDocument.find(
            ToolExecutionDocument.started_at >= cutoff_date,
            ToolExecutionDocument.success == False,  # noqa: E712
        ).to_list()

        if not failed_executions:
            return {
                "total_errors": 0,
                "error_types": [],
            }

        error_types: Counter = Counter(execution.error_type for execution in failed_executions if execution.error_type)

        return {
            "total_errors": len(failed_executions),
            "error_types": [
                {"error_type": error_type, "count": count, "percentage": (count / len(failed_executions)) * 100}
                for error_type, count in error_types.most_common()
            ],
        }

    async def get_dashboard_summary(self) -> dict[str, Any]:
        """Get summary metrics for main dashboard.

        Returns:
            Dashboard summary metrics
        """
        from app.domain.services.analyzers.pattern_detector import get_pattern_detector

        detector = get_pattern_detector()

        # Gather all metrics in parallel
        import asyncio

        performance_task = detector.detect_performance_trends(days=7)
        workflow_task = self.get_workflow_efficiency_metrics(days=7)
        tool_task = self.get_tool_performance_breakdown()
        mode_task = self.get_mode_selection_accuracy()
        error_task = self.get_error_breakdown(days=7)

        performance, workflow, tool_perf, mode_accuracy, errors = await asyncio.gather(
            performance_task,
            workflow_task,
            tool_task,
            mode_task,
            error_task,
        )

        return {
            "performance": performance,
            "workflow": workflow,
            "tool_performance": tool_perf,
            "mode_selection": mode_accuracy,
            "errors": errors,
            "generated_at": datetime.now(UTC).isoformat(),
        }


# Global instance
_analytics_service: AnalyticsService | None = None


def get_analytics_service() -> AnalyticsService:
    """Get the global analytics service instance.

    Returns:
        AnalyticsService instance
    """
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service
