"""
Security Assessment for Agent Actions

Inspired by OpenHands' security risk assessment system, this module
classifies the risk level of tool actions and determines whether
user confirmation is required before execution.

Risk Levels:
- LOW: Safe operations (read, search, view)
- MEDIUM: Modifying operations (write, install, execute)
- HIGH: Destructive or sensitive operations (delete, credentials, payment)
- CRITICAL: Operations that require explicit user consent
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Set
from enum import Enum

logger = logging.getLogger(__name__)


class ActionSecurityRisk(Enum):
    """Security risk classification for actions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class SecurityAssessment:
    """Result of security assessment for an action."""
    risk_level: ActionSecurityRisk
    reason: str
    requires_confirmation: bool
    suggestions: List[str]
    blocked: bool = False


class SecurityAssessor:
    """
    Assess security risk of tool actions.

    This assessor analyzes tool calls and their arguments to determine
    the potential risk level and whether user confirmation is needed.

    Usage:
        assessor = SecurityAssessor(autonomy_level="autonomous")
        assessment = assessor.assess_action("shell_exec", {"command": "rm -rf /"})
        if assessment.blocked:
            # Action should not be executed
        elif assessment.requires_confirmation:
            # Ask user for confirmation
    """

    # Shell command patterns by risk level
    CRITICAL_SHELL_PATTERNS = [
        r"rm\s+(-rf?|--recursive)\s+/(?!\w)",  # rm -rf /
        r"rm\s+-rf?\s+~",  # rm -rf ~
        r":()\{.*\|.*&\s*\};:",  # Fork bomb
        r"dd\s+if=.*of=/dev/[sh]d",  # Overwrite disk
        r"mkfs\.",  # Format filesystem
        r">\s*/dev/[sh]d",  # Write to raw disk
        r"chmod\s+-R\s+777\s+/",  # Open permissions on root
    ]

    HIGH_RISK_SHELL_PATTERNS = [
        r"rm\s+-rf?",  # Any recursive delete
        r"rm\s+.*\*",  # Wildcard delete
        r"sudo\s+rm",  # Privileged delete
        r"curl.*\|\s*(ba)?sh",  # Pipe to shell
        r"wget.*\|\s*(ba)?sh",  # Pipe to shell
        r"eval\s+",  # Eval command
        r">\s*/etc/",  # Write to system config
        r"chmod\s+777",  # World-writable permissions
        r"chown\s+-R",  # Recursive ownership change
        r"DROP\s+DATABASE",  # SQL drop
        r"DROP\s+TABLE",  # SQL drop
        r"TRUNCATE\s+",  # SQL truncate
        r"DELETE\s+FROM.*WHERE\s+1\s*=\s*1",  # Delete all
    ]

    MEDIUM_RISK_SHELL_PATTERNS = [
        r"pip\s+install",  # Package installation
        r"npm\s+install",  # Package installation
        r"apt(-get)?\s+install",  # System package
        r"brew\s+install",  # Homebrew
        r"git\s+push",  # Push to remote
        r"git\s+push\s+-f",  # Force push
        r"docker\s+run",  # Container execution
        r"sudo\s+",  # Any sudo command
        r"systemctl\s+(start|stop|restart)",  # Service control
    ]

    # Sensitive data patterns
    SENSITIVE_DATA_PATTERNS = [
        r"password",
        r"api[_-]?key",
        r"secret",
        r"token",
        r"credential",
        r"private[_-]?key",
        r"access[_-]?key",
        r"auth",
    ]

    # File paths that are sensitive
    SENSITIVE_PATHS = [
        "/etc/passwd",
        "/etc/shadow",
        "~/.ssh/",
        "~/.aws/",
        ".env",
        ".credentials",
        "secrets.json",
        "credentials.json",
    ]

    def __init__(
        self,
        autonomy_level: str = "autonomous",
        allow_credential_access: bool = False,
        allow_destructive_operations: bool = False,
        custom_blocked_patterns: Optional[List[str]] = None,
    ):
        """
        Initialize the security assessor.

        Args:
            autonomy_level: One of "supervised", "guided", "autonomous", "unrestricted"
            allow_credential_access: Whether to allow credential-related operations
            allow_destructive_operations: Whether to allow destructive operations
            custom_blocked_patterns: Additional patterns to block
        """
        self.autonomy_level = autonomy_level
        self.allow_credential_access = allow_credential_access
        self.allow_destructive_operations = allow_destructive_operations
        self.custom_blocked_patterns = custom_blocked_patterns or []

        # Track recent assessments for pattern detection
        self._assessment_history: List[SecurityAssessment] = []

    def assess_action(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> SecurityAssessment:
        """
        Assess the security risk of a proposed tool action.

        Args:
            tool_name: Name of the tool to be called
            tool_args: Arguments to be passed to the tool

        Returns:
            SecurityAssessment with risk level and recommendations
        """
        # Start with unknown risk
        risk_level = ActionSecurityRisk.LOW
        reasons: List[str] = []
        suggestions: List[str] = []
        blocked = False

        # Assess based on tool type
        if tool_name in ("shell_exec", "shell_execute", "execute_command"):
            assessment = self._assess_shell_command(tool_args)
            return assessment

        elif tool_name in ("file_write", "file_delete", "file_append"):
            assessment = self._assess_file_operation(tool_name, tool_args)
            return assessment

        elif tool_name.startswith("browser_"):
            assessment = self._assess_browser_operation(tool_name, tool_args)
            return assessment

        elif tool_name.startswith("mcp_"):
            # MCP tools are external - treat with caution
            risk_level = ActionSecurityRisk.MEDIUM
            reasons.append("External MCP tool call")
            suggestions.append("Verify MCP server is trusted")

        # Default assessment for unknown tools
        return SecurityAssessment(
            risk_level=risk_level,
            reason="; ".join(reasons) if reasons else "Standard operation",
            requires_confirmation=self._requires_confirmation(risk_level),
            suggestions=suggestions,
            blocked=blocked,
        )

    def _assess_shell_command(self, tool_args: Dict[str, Any]) -> SecurityAssessment:
        """Assess shell command risk."""
        command = tool_args.get("command", "")
        command_lower = command.lower()

        reasons: List[str] = []
        suggestions: List[str] = []

        # Check for critical patterns (always blocked)
        for pattern in self.CRITICAL_SHELL_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return SecurityAssessment(
                    risk_level=ActionSecurityRisk.CRITICAL,
                    reason=f"Critical risk pattern detected: {pattern}",
                    requires_confirmation=True,
                    suggestions=["This command is potentially destructive and blocked by default"],
                    blocked=not self.allow_destructive_operations,
                )

        # Check for high risk patterns
        for pattern in self.HIGH_RISK_SHELL_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                reasons.append(f"High-risk pattern: {pattern}")
                suggestions.append("Verify this operation is intended")

                if not self.allow_destructive_operations:
                    return SecurityAssessment(
                        risk_level=ActionSecurityRisk.HIGH,
                        reason="; ".join(reasons),
                        requires_confirmation=True,
                        suggestions=suggestions,
                        blocked=False,
                    )

        # Check for medium risk patterns
        for pattern in self.MEDIUM_RISK_SHELL_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                reasons.append(f"Modifying operation: {pattern}")

                return SecurityAssessment(
                    risk_level=ActionSecurityRisk.MEDIUM,
                    reason="; ".join(reasons) if reasons else "Package/system modification",
                    requires_confirmation=self.autonomy_level == "supervised",
                    suggestions=suggestions,
                    blocked=False,
                )

        # Check for sensitive data exposure
        for pattern in self.SENSITIVE_DATA_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                if not self.allow_credential_access:
                    reasons.append(f"Potential credential access: {pattern}")
                    suggestions.append("Ensure credentials are handled securely")

                    return SecurityAssessment(
                        risk_level=ActionSecurityRisk.HIGH,
                        reason="; ".join(reasons),
                        requires_confirmation=True,
                        suggestions=suggestions,
                        blocked=False,
                    )

        # Check custom blocked patterns
        for pattern in self.custom_blocked_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return SecurityAssessment(
                    risk_level=ActionSecurityRisk.HIGH,
                    reason=f"Custom blocked pattern: {pattern}",
                    requires_confirmation=True,
                    suggestions=["This pattern is blocked by configuration"],
                    blocked=True,
                )

        # Default: low risk
        return SecurityAssessment(
            risk_level=ActionSecurityRisk.LOW,
            reason="Standard shell command",
            requires_confirmation=False,
            suggestions=[],
            blocked=False,
        )

    def _assess_file_operation(
        self,
        tool_name: str,
        tool_args: Dict[str, Any]
    ) -> SecurityAssessment:
        """Assess file operation risk."""
        file_path = tool_args.get("file_path", tool_args.get("path", ""))
        content = tool_args.get("content", "")

        reasons: List[str] = []
        suggestions: List[str] = []

        # Check for sensitive paths
        for sensitive_path in self.SENSITIVE_PATHS:
            if sensitive_path in file_path:
                return SecurityAssessment(
                    risk_level=ActionSecurityRisk.HIGH,
                    reason=f"Operation on sensitive path: {sensitive_path}",
                    requires_confirmation=True,
                    suggestions=["Verify this file operation is intended"],
                    blocked=not self.allow_credential_access,
                )

        # File deletion is always at least medium risk
        if tool_name == "file_delete":
            return SecurityAssessment(
                risk_level=ActionSecurityRisk.MEDIUM,
                reason="File deletion operation",
                requires_confirmation=self.autonomy_level in ("supervised", "guided"),
                suggestions=["Ensure file is not needed before deletion"],
                blocked=False,
            )

        # Check content for sensitive data patterns
        if content:
            for pattern in self.SENSITIVE_DATA_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    reasons.append(f"Content contains sensitive pattern: {pattern}")
                    suggestions.append("Ensure sensitive data is handled appropriately")

                    return SecurityAssessment(
                        risk_level=ActionSecurityRisk.MEDIUM,
                        reason="; ".join(reasons),
                        requires_confirmation=self.autonomy_level == "supervised",
                        suggestions=suggestions,
                        blocked=False,
                    )

        # Default file write is low risk
        return SecurityAssessment(
            risk_level=ActionSecurityRisk.LOW,
            reason="Standard file operation",
            requires_confirmation=False,
            suggestions=[],
            blocked=False,
        )

    def _assess_browser_operation(
        self,
        tool_name: str,
        tool_args: Dict[str, Any]
    ) -> SecurityAssessment:
        """Assess browser operation risk."""
        url = tool_args.get("url", "")
        text = tool_args.get("text", "")

        # Check for credential entry
        if tool_name == "browser_type":
            text_lower = text.lower() if text else ""

            # Check if typing sensitive data
            for pattern in self.SENSITIVE_DATA_PATTERNS:
                if re.search(pattern, text_lower):
                    return SecurityAssessment(
                        risk_level=ActionSecurityRisk.HIGH,
                        reason="Potential credential entry in browser",
                        requires_confirmation=True,
                        suggestions=[
                            "Suggest user takeover for credential entry",
                            "Never store or log credentials"
                        ],
                        blocked=not self.allow_credential_access,
                    )

        # Check for payment/financial URLs
        payment_indicators = ["checkout", "payment", "billing", "purchase", "cart"]
        if url:
            url_lower = url.lower()
            for indicator in payment_indicators:
                if indicator in url_lower:
                    return SecurityAssessment(
                        risk_level=ActionSecurityRisk.HIGH,
                        reason=f"Financial/payment URL detected: {indicator}",
                        requires_confirmation=True,
                        suggestions=["User should handle payment operations directly"],
                        blocked=True,
                    )

        # Navigation and viewing are low risk
        return SecurityAssessment(
            risk_level=ActionSecurityRisk.LOW,
            reason="Standard browser operation",
            requires_confirmation=False,
            suggestions=[],
            blocked=False,
        )

    def _requires_confirmation(self, risk_level: ActionSecurityRisk) -> bool:
        """Determine if confirmation is required based on risk and autonomy level."""
        if self.autonomy_level == "unrestricted":
            return False

        if self.autonomy_level == "supervised":
            return risk_level != ActionSecurityRisk.LOW

        if self.autonomy_level == "guided":
            return risk_level in (ActionSecurityRisk.HIGH, ActionSecurityRisk.CRITICAL)

        # autonomous
        return risk_level == ActionSecurityRisk.CRITICAL

    def add_blocked_pattern(self, pattern: str) -> None:
        """Add a custom pattern to block."""
        self.custom_blocked_patterns.append(pattern)

    def get_risk_summary(self) -> Dict[str, Any]:
        """Get summary of recent risk assessments."""
        if not self._assessment_history:
            return {
                "total_assessments": 0,
                "risk_distribution": {},
                "blocked_count": 0,
                "confirmation_required_count": 0,
            }

        risk_counts = {}
        blocked_count = 0
        confirmation_count = 0

        for assessment in self._assessment_history[-50:]:  # Last 50
            risk_counts[assessment.risk_level.value] = (
                risk_counts.get(assessment.risk_level.value, 0) + 1
            )
            if assessment.blocked:
                blocked_count += 1
            if assessment.requires_confirmation:
                confirmation_count += 1

        return {
            "total_assessments": len(self._assessment_history),
            "risk_distribution": risk_counts,
            "blocked_count": blocked_count,
            "confirmation_required_count": confirmation_count,
        }
