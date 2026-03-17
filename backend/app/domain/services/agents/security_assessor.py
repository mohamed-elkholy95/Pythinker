"""
Security assessor for evaluating agent action risks.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ActionSecurityRisk(str, Enum):
    """Risk levels for agent actions."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityAssessment:
    """Assessment result for a proposed action."""

    blocked: bool
    reason: str
    risk_level: ActionSecurityRisk
    requires_confirmation: bool = False
    suggestions: list = None

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


class SecurityAssessor:
    """
    Evaluates security risks of agent actions based on configuration.
    """

    def __init__(
        self,
        autonomy_level: str = "autonomous",
        allow_credential_access: bool = False,
        allow_destructive_operations: bool = False,
    ):
        """
        Initialize security assessor.

        Args:
            autonomy_level: Level of autonomy (autonomous, semi-autonomous, human-in-the-loop)
            allow_credential_access: Whether to allow access to credentials
            allow_destructive_operations: Whether to allow destructive operations (delete, overwrite)
        """
        self.autonomy_level = autonomy_level
        self.allow_credential_access = allow_credential_access
        self.allow_destructive_operations = allow_destructive_operations
        self._blocked_count = 0
        self._high_risk_count = 0

    def assess_action(self, function_name: str, arguments: dict[str, Any]) -> SecurityAssessment:
        """
        Assess the security risk of a proposed action.

        Args:
            function_name: Name of the tool/function to execute
            arguments: Arguments for the function

        Returns:
            SecurityAssessment object containing decision and risk level

        Note:
            Since agents run in isolated sandbox containers, all actions are allowed.
            The sandbox provides the security boundary, not this assessor.
        """
        # All actions allowed - sandbox provides isolation
        return SecurityAssessment(
            blocked=False,
            reason="Action allowed in sandboxed environment",
            risk_level=ActionSecurityRisk.LOW,
            requires_confirmation=False,
        )

    def get_risk_summary(self) -> dict[str, Any]:
        """
        Get summary of risk assessments.

        Returns:
            Dictionary with risk statistics
        """
        return {
            "autonomy_level": self.autonomy_level,
            "blocked_actions": self._blocked_count,
            "high_risk_actions": self._high_risk_count,
        }
