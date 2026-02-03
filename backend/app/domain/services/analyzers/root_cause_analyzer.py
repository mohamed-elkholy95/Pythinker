"""Root cause analyzer for failed agent sessions.

Analyzes session events, decisions, and tool executions to identify
the root cause of failures.
"""

import logging
from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RootCause(BaseModel):
    """Root cause analysis result."""

    cause_type: str  # tool_failure_cascade, stuck_loop, resource_exhaustion, etc.
    description: str
    confidence: float  # 0.0-1.0
    contributing_factors: list[str]
    recommended_fix: str
    session_id: str
    analyzed_at: datetime


class RootCauseAnalyzer:
    """Analyzes failed sessions to identify root causes."""

    CAUSE_TYPES: ClassVar[list[str]] = [
        "tool_failure_cascade",
        "stuck_verification_loop",
        "resource_exhaustion",
        "llm_hallucination",
        "wrong_mode_selection",
        "token_budget_exceeded",
        "sandbox_failure",
        "network_timeout",
        "context_confusion",
    ]

    async def analyze_failed_session(self, session_id: str) -> RootCause:
        """Analyze a failed session to determine root cause.

        Args:
            session_id: Session identifier to analyze

        Returns:
            RootCause with analysis results
        """
        from app.infrastructure.models.documents import (
            AgentDecisionDocument,
            ToolExecutionDocument,
            WorkflowStateDocument,
        )

        # Gather all relevant data
        decisions = (
            await AgentDecisionDocument.find(AgentDecisionDocument.session_id == session_id)
            .sort("+timestamp")
            .to_list()
        )

        tool_executions = (
            await ToolExecutionDocument.find(ToolExecutionDocument.session_id == session_id)
            .sort("+started_at")
            .to_list()
        )

        workflow_states = (
            await WorkflowStateDocument.find(WorkflowStateDocument.session_id == session_id)
            .sort("+timestamp")
            .to_list()
        )

        # Check for patterns
        patterns = {
            "tool_failure_cascade": self._check_tool_failure_cascade(tool_executions),
            "stuck_verification_loop": self._check_stuck_loop(workflow_states),
            "resource_exhaustion": self._check_resource_exhaustion(tool_executions),
            "wrong_mode_selection": self._check_wrong_mode(decisions),
            "token_budget_exceeded": self._check_token_budget(workflow_states),
        }

        # Find highest confidence pattern
        best_cause = max(patterns.items(), key=lambda x: x[1])
        cause_type, confidence = best_cause

        # Build contributing factors
        contributing_factors = []
        for pattern_type, conf in patterns.items():
            if conf > 0.3 and pattern_type != cause_type:
                contributing_factors.append(pattern_type)

        # Generate description and recommendation
        description = self._generate_description(cause_type, tool_executions, workflow_states, decisions)
        recommended_fix = self._generate_recommendation(cause_type)

        return RootCause(
            cause_type=cause_type,
            description=description,
            confidence=confidence,
            contributing_factors=contributing_factors,
            recommended_fix=recommended_fix,
            session_id=session_id,
            analyzed_at=datetime.now(),
        )

    def _check_tool_failure_cascade(self, tool_executions: list[Any]) -> float:
        """Check for cascading tool failures.

        Args:
            tool_executions: List of tool execution documents

        Returns:
            Confidence score (0.0-1.0)
        """
        if not tool_executions:
            return 0.0

        failures = [t for t in tool_executions if not t.success]
        if len(failures) < 2:
            return 0.0

        # Check if failures are consecutive
        consecutive_failures = 0
        for i in range(len(tool_executions) - 1):
            if not tool_executions[i].success and not tool_executions[i + 1].success:
                consecutive_failures += 1

        failure_rate = len(failures) / len(tool_executions)
        cascade_score = consecutive_failures / max(len(failures) - 1, 1)

        return min(failure_rate * 0.5 + cascade_score * 0.5, 1.0)

    def _check_stuck_loop(self, workflow_states: list[Any]) -> float:
        """Check for stuck verification loops.

        Args:
            workflow_states: List of workflow state documents

        Returns:
            Confidence score (0.0-1.0)
        """
        if not workflow_states:
            return 0.0

        # Count verification loops
        max_verification_loops = max(
            (state.verification_loops for state in workflow_states),
            default=0,
        )

        # Check for stuck loop detections
        stuck_detections = sum(1 for state in workflow_states if state.stuck_loop_detected)

        if max_verification_loops >= 5 or stuck_detections > 0:
            return min(max_verification_loops / 10.0 + stuck_detections * 0.3, 1.0)

        return 0.0

    def _check_resource_exhaustion(self, tool_executions: list[Any]) -> float:
        """Check for resource exhaustion.

        Args:
            tool_executions: List of tool execution documents

        Returns:
            Confidence score (0.0-1.0)
        """
        if not tool_executions:
            return 0.0

        high_cpu_count = sum(1 for t in tool_executions if t.container_cpu_percent and t.container_cpu_percent > 90)

        high_memory_count = sum(
            1
            for t in tool_executions
            if t.container_memory_mb and t.container_memory_mb > 3500  # Near 4GB limit
        )

        if high_cpu_count > len(tool_executions) * 0.3 or high_memory_count > len(tool_executions) * 0.3:
            return min((high_cpu_count + high_memory_count) / len(tool_executions), 1.0)

        return 0.0

    def _check_wrong_mode(self, decisions: list[Any]) -> float:
        """Check for wrong mode selection.

        Args:
            decisions: List of decision documents

        Returns:
            Confidence score (0.0-1.0)
        """
        if not decisions:
            return 0.0

        mode_decisions = [d for d in decisions if d.decision_type == "mode_selection"]
        if not mode_decisions:
            return 0.0

        # Check if mode decision led to error
        wrong_mode_count = sum(1 for d in mode_decisions if d.led_to_error)

        if wrong_mode_count > 0:
            return min(wrong_mode_count / len(mode_decisions), 1.0)

        return 0.0

    def _check_token_budget(self, workflow_states: list[Any]) -> float:
        """Check for token budget issues.

        Args:
            workflow_states: List of workflow state documents

        Returns:
            Confidence score (0.0-1.0)
        """
        if not workflow_states:
            return 0.0

        critical_pressure_count = sum(1 for state in workflow_states if state.context_pressure == "critical")

        if critical_pressure_count > len(workflow_states) * 0.5:
            return min(critical_pressure_count / len(workflow_states), 1.0)

        return 0.0

    def _generate_description(
        self,
        cause_type: str,
        tool_executions: list[Any],
        workflow_states: list[Any],
        decisions: list[Any],
    ) -> str:
        """Generate human-readable description of root cause.

        Args:
            cause_type: Type of root cause identified
            tool_executions: Tool execution data
            workflow_states: Workflow state data
            decisions: Decision data

        Returns:
            Description string
        """
        descriptions = {
            "tool_failure_cascade": f"Multiple consecutive tool failures detected ({len([t for t in tool_executions if not t.success])} failures out of {len(tool_executions)} executions)",
            "stuck_verification_loop": f"Agent stuck in verification loop (max {max((s.verification_loops for s in workflow_states), default=0)} loops)",
            "resource_exhaustion": "Container resource limits exceeded during execution",
            "wrong_mode_selection": "Task routed to incorrect agent mode",
            "token_budget_exceeded": f"Context token limit critically exceeded ({sum(1 for s in workflow_states if s.context_pressure == 'critical')} critical events)",
        }

        return descriptions.get(
            cause_type,
            f"Unspecified failure cause: {cause_type}",
        )

    def _generate_recommendation(self, cause_type: str) -> str:
        """Generate recommended fix for root cause.

        Args:
            cause_type: Type of root cause

        Returns:
            Recommendation string
        """
        recommendations = {
            "tool_failure_cascade": "Review tool retry logic and error handling; check sandbox environment health",
            "stuck_verification_loop": "Review verification criteria; implement loop detection with circuit breaker",
            "resource_exhaustion": "Increase container resource limits or optimize tool usage",
            "wrong_mode_selection": "Improve intent classification; review mode selection criteria",
            "token_budget_exceeded": "Implement better context compaction; use more aggressive summarization",
        }

        return recommendations.get(
            cause_type,
            "Review logs and error patterns for specific failure mode",
        )


# Global instance
_root_cause_analyzer: RootCauseAnalyzer | None = None


def get_root_cause_analyzer() -> RootCauseAnalyzer:
    """Get the global root cause analyzer instance.

    Returns:
        RootCauseAnalyzer instance
    """
    global _root_cause_analyzer
    if _root_cause_analyzer is None:
        _root_cause_analyzer = RootCauseAnalyzer()
    return _root_cause_analyzer
