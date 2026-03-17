"""Pattern detection across multiple sessions.

Identifies recurring failure patterns, tool correlation issues,
and system-wide trends.
"""

import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.repositories.analytics_repository import get_analytics_repository

logger = logging.getLogger(__name__)


class PatternDetector:
    """Detects patterns across multiple sessions."""

    async def detect_common_failure_modes(self, days: int = 7) -> list[dict[str, Any]]:
        """Find recurring failure patterns across sessions.

        Args:
            days: Number of days to look back

        Returns:
            List of failure patterns with frequency and examples
        """
        from app.domain.services.analyzers.root_cause_analyzer import get_root_cause_analyzer

        analytics_repo = get_analytics_repository()
        if not analytics_repo:
            logger.warning("Analytics repository not configured")
            return []

        cutoff_date = datetime.now(UTC) - timedelta(days=days)

        # Get failed sessions
        failed_sessions = await analytics_repo.get_failed_sessions(cutoff_date, limit=100)

        if not failed_sessions:
            return []

        analyzer = get_root_cause_analyzer()

        # Analyze each failed session
        cause_counts: Counter = Counter()
        cause_examples: defaultdict = defaultdict(list)

        for session in failed_sessions:
            try:
                root_cause = await analyzer.analyze_failed_session(session.session_id)
                cause_counts[root_cause.cause_type] += 1

                if len(cause_examples[root_cause.cause_type]) < 3:
                    cause_examples[root_cause.cause_type].append(
                        {
                            "session_id": session.session_id,
                            "description": root_cause.description,
                            "confidence": root_cause.confidence,
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to analyze session {session.session_id}: {e}")

        # Build results
        patterns = []
        for cause_type, count in cause_counts.most_common():
            patterns.append(
                {
                    "cause_type": cause_type,
                    "frequency": count,
                    "percentage": (count / len(failed_sessions)) * 100,
                    "examples": cause_examples[cause_type],
                }
            )

        return patterns

    async def detect_tool_correlation_issues(self) -> list[dict[str, Any]]:
        """Find tools that frequently fail together.

        Returns:
            List of tool correlation patterns
        """
        analytics_repo = get_analytics_repository()
        if not analytics_repo:
            logger.warning("Analytics repository not configured")
            return []

        # Get recent failed tool executions
        cutoff_date = datetime.now(UTC) - timedelta(days=7)
        failed_executions = await analytics_repo.get_failed_tool_executions(cutoff_date, limit=500)

        if not failed_executions:
            return []

        # Group by session
        session_failures: defaultdict = defaultdict(list)
        for execution in failed_executions:
            session_failures[execution.session_id].append(execution.tool_name)

        # Find tool pairs that fail together
        tool_pairs: Counter = Counter()
        for tools in session_failures.values():
            if len(tools) >= 2:
                unique_tools = list(set(tools))
                for i in range(len(unique_tools)):
                    for j in range(i + 1, len(unique_tools)):
                        pair = tuple(sorted([unique_tools[i], unique_tools[j]]))
                        tool_pairs[pair] += 1

        # Build results
        correlations = []
        for (tool1, tool2), count in tool_pairs.most_common(10):
            if count >= 3:  # Only report pairs that occur at least 3 times
                correlations.append(
                    {
                        "tool1": tool1,
                        "tool2": tool2,
                        "co_failure_count": count,
                    }
                )

        return correlations

    async def detect_mode_selection_accuracy(self) -> dict[str, Any]:
        """Analyze mode selection decision accuracy.

        Returns:
            Mode selection accuracy metrics
        """
        analytics_repo = get_analytics_repository()
        if not analytics_repo:
            logger.warning("Analytics repository not configured")
            return {
                "total_decisions": 0,
                "accuracy": 0.0,
                "errors": 0,
            }

        cutoff_date = datetime.now(UTC) - timedelta(days=7)

        # Get mode selection decisions
        mode_decisions = await analytics_repo.get_mode_selection_decisions(cutoff_date, limit=500)

        if not mode_decisions:
            return {
                "total_decisions": 0,
                "accuracy": 0.0,
                "errors": 0,
            }

        errors = sum(1 for d in mode_decisions if d.led_to_error)
        accuracy = (len(mode_decisions) - errors) / len(mode_decisions)

        # Break down by selected mode
        mode_breakdown: defaultdict = defaultdict(lambda: {"total": 0, "errors": 0})
        for decision in mode_decisions:
            mode = decision.selected_option
            mode_breakdown[mode]["total"] += 1
            if decision.led_to_error:
                mode_breakdown[mode]["errors"] += 1

        return {
            "total_decisions": len(mode_decisions),
            "accuracy": accuracy,
            "errors": errors,
            "mode_breakdown": {
                mode: {
                    **stats,
                    "error_rate": stats["errors"] / stats["total"] if stats["total"] > 0 else 0,
                }
                for mode, stats in mode_breakdown.items()
            },
        }

    async def detect_performance_trends(self, days: int = 7) -> dict[str, Any]:
        """Detect performance trends over time.

        Args:
            days: Number of days to analyze

        Returns:
            Performance trend metrics
        """
        analytics_repo = get_analytics_repository()
        if not analytics_repo:
            logger.warning("Analytics repository not configured")
            return {}

        cutoff_date = datetime.now(UTC) - timedelta(days=days)

        # Get sessions
        sessions = await analytics_repo.get_sessions_since(cutoff_date, limit=500)

        if not sessions:
            return {}

        # Calculate metrics
        total_sessions = len(sessions)
        failed_sessions = sum(1 for s in sessions if s.status == "error")
        success_rate = (total_sessions - failed_sessions) / total_sessions if total_sessions > 0 else 0

        # Get tool executions
        tool_executions = await analytics_repo.get_tool_executions_since(cutoff_date, limit=1000)

        if tool_executions:
            durations = [t.duration_ms for t in tool_executions if t.duration_ms]
            avg_duration = sum(durations) / len(durations) if durations else 0

            tool_success_rate = sum(1 for t in tool_executions if t.success) / len(tool_executions)
        else:
            avg_duration = 0
            tool_success_rate = 0

        return {
            "period_days": days,
            "total_sessions": total_sessions,
            "success_rate": success_rate,
            "failure_rate": 1 - success_rate,
            "tool_executions": len(tool_executions),
            "avg_tool_duration_ms": avg_duration,
            "tool_success_rate": tool_success_rate,
        }


# Global instance
_pattern_detector: PatternDetector | None = None


def get_pattern_detector() -> PatternDetector:
    """Get the global pattern detector instance.

    Returns:
        PatternDetector instance
    """
    global _pattern_detector
    if _pattern_detector is None:
        _pattern_detector = PatternDetector()
    return _pattern_detector
