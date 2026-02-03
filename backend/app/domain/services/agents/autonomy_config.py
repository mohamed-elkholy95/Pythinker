"""
Autonomy configuration system for agent operations.

Provides configurable autonomy levels, permission flags, and safety limits
that control how autonomously an agent can operate. Integrates with
PlanActFlow for approval checkpoints at critical operations.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AutonomyLevel(str, Enum):
    """
    Autonomy levels controlling agent approval requirements.

    SUPERVISED: Requires user confirmation for ALL actions
    GUIDED: Requires confirmation only for critical actions (credentials, payments, deletions)
    AUTONOMOUS: Only requires confirmation for payments and irreversible actions
    UNRESTRICTED: No confirmation required (use with caution)
    """

    SUPERVISED = "supervised"
    GUIDED = "guided"
    AUTONOMOUS = "autonomous"
    UNRESTRICTED = "unrestricted"


class ActionCategory(str, Enum):
    """Categories of actions for permission checking."""

    CREDENTIAL_ACCESS = "credential_access"
    EXTERNAL_REQUEST = "external_request"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    SHELL_EXECUTE = "shell_execute"
    BROWSER_NAVIGATE = "browser_navigate"
    PAYMENT = "payment"
    DATA_MODIFICATION = "data_modification"
    SYSTEM_CONFIG = "system_config"
    NETWORK_REQUEST = "network_request"


# Actions that require confirmation at each autonomy level
CONFIRMATION_REQUIRED: dict[AutonomyLevel, set[ActionCategory]] = {
    AutonomyLevel.SUPERVISED: set(ActionCategory),  # All actions
    AutonomyLevel.GUIDED: {
        ActionCategory.CREDENTIAL_ACCESS,
        ActionCategory.PAYMENT,
        ActionCategory.FILE_DELETE,
        ActionCategory.DATA_MODIFICATION,
        ActionCategory.SYSTEM_CONFIG,
    },
    AutonomyLevel.AUTONOMOUS: {
        ActionCategory.PAYMENT,
        ActionCategory.SYSTEM_CONFIG,
    },
    AutonomyLevel.UNRESTRICTED: set(),  # No confirmation required
}


@dataclass
class PermissionFlags:
    """
    Fine-grained permission flags for agent operations.

    These flags override autonomy level settings when set to False,
    completely disabling certain capabilities regardless of level.
    """

    allow_credential_access: bool = True
    allow_external_requests: bool = True
    allow_file_system_write: bool = True
    allow_file_system_delete: bool = False  # Disabled by default for safety
    allow_shell_execute: bool = True
    allow_browser_navigation: bool = True
    allow_payment_operations: bool = False  # Disabled by default
    allow_data_modification: bool = True
    allow_system_config: bool = False  # Disabled by default

    # Domain/URL restrictions for external requests
    allowed_domains: set[str] | None = None  # None = all allowed
    blocked_domains: set[str] = field(
        default_factory=lambda: {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "internal",
        }
    )

    # Path restrictions for file operations
    allowed_paths: set[str] | None = None  # None = all allowed
    blocked_paths: set[str] = field(
        default_factory=lambda: {
            "/etc",
            "/var",
            "/usr",
            "/root",
            "/home",
            "~",
        }
    )

    def is_domain_allowed(self, domain: str) -> bool:
        """Check if a domain is allowed for external requests."""
        domain_lower = domain.lower()

        # Check blocked list first
        for blocked in self.blocked_domains:
            if blocked in domain_lower:
                return False

        # If allowed list is specified, domain must be in it
        if self.allowed_domains is not None:
            return any(allowed in domain_lower for allowed in self.allowed_domains)

        return True

    def is_path_allowed(self, path: str) -> bool:
        """Check if a file path is allowed for operations."""
        # Normalize path
        import os

        path_normalized = os.path.normpath(os.path.expanduser(path))

        # Check blocked list first
        for blocked in self.blocked_paths:
            blocked_normalized = os.path.normpath(os.path.expanduser(blocked))
            if path_normalized.startswith(blocked_normalized):
                return False

        # If allowed list is specified, path must be in it
        if self.allowed_paths is not None:
            return any(
                path_normalized.startswith(os.path.normpath(os.path.expanduser(allowed)))
                for allowed in self.allowed_paths
            )

        return True


@dataclass
class SafetyLimits:
    """
    Safety limits to prevent runaway agent execution.

    These are hard limits that cannot be overridden by autonomy level.
    When any limit is exceeded, the agent pauses for user intervention.
    """

    max_iterations: int = 200  # Maximum loop iterations per run (increased for complex tasks)
    max_tool_calls: int = 300  # Maximum tool invocations per run (codebase analysis needs more)
    max_execution_time_seconds: int = 3600  # 60 minutes for complex tasks
    max_tokens_per_run: int = 500000  # Token limit across all LLM calls
    max_cost_usd: float | None = None  # Optional cost limit

    # Tracking counters (not config, but state)
    current_iterations: int = field(default=0, repr=False)
    current_tool_calls: int = field(default=0, repr=False)
    start_time: datetime | None = field(default=None, repr=False)
    current_tokens: int = field(default=0, repr=False)
    current_cost: float = field(default=0.0, repr=False)

    def start_run(self) -> None:
        """Start a new run, resetting counters."""
        self.current_iterations = 0
        self.current_tool_calls = 0
        self.start_time = datetime.now()
        self.current_tokens = 0
        self.current_cost = 0.0
        logger.debug("Safety limits counters reset for new run")

    def increment_iteration(self) -> bool:
        """
        Increment iteration counter and check limit.

        Returns:
            True if within limits, False if limit exceeded
        """
        self.current_iterations += 1
        if self.current_iterations > self.max_iterations:
            logger.warning(f"Iteration limit exceeded: {self.current_iterations}/{self.max_iterations}")
            return False
        return True

    def increment_tool_calls(self, count: int = 1) -> bool:
        """
        Increment tool call counter and check limit.

        Returns:
            True if within limits, False if limit exceeded
        """
        self.current_tool_calls += count
        if self.current_tool_calls > self.max_tool_calls:
            logger.warning(f"Tool call limit exceeded: {self.current_tool_calls}/{self.max_tool_calls}")
            return False
        return True

    def add_tokens(self, tokens: int) -> bool:
        """
        Add to token counter and check limit.

        Returns:
            True if within limits, False if limit exceeded
        """
        self.current_tokens += tokens
        if self.current_tokens > self.max_tokens_per_run:
            logger.warning(f"Token limit exceeded: {self.current_tokens}/{self.max_tokens_per_run}")
            return False
        return True

    def add_cost(self, cost: float) -> bool:
        """
        Add to cost counter and check limit.

        Returns:
            True if within limits, False if limit exceeded (or no limit set)
        """
        self.current_cost += cost
        if self.max_cost_usd is not None and self.current_cost > self.max_cost_usd:
            logger.warning(f"Cost limit exceeded: ${self.current_cost:.4f}/${self.max_cost_usd:.4f}")
            return False
        return True

    def check_time_limit(self) -> bool:
        """
        Check if execution time limit has been exceeded.

        Returns:
            True if within limits, False if limit exceeded
        """
        if self.start_time is None:
            return True

        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed > self.max_execution_time_seconds:
            logger.warning(f"Time limit exceeded: {elapsed:.0f}s/{self.max_execution_time_seconds}s")
            return False
        return True

    def check_all_limits(self) -> tuple[bool, str | None]:
        """
        Check all limits at once.

        Returns:
            Tuple of (all_ok, reason_if_not_ok)
        """
        if self.current_iterations > self.max_iterations:
            return False, f"Iteration limit ({self.max_iterations}) exceeded"

        if self.current_tool_calls > self.max_tool_calls:
            return False, f"Tool call limit ({self.max_tool_calls}) exceeded"

        if self.current_tokens > self.max_tokens_per_run:
            return False, f"Token limit ({self.max_tokens_per_run}) exceeded"

        if self.max_cost_usd is not None and self.current_cost > self.max_cost_usd:
            return False, f"Cost limit (${self.max_cost_usd:.2f}) exceeded"

        if not self.check_time_limit():
            return False, f"Time limit ({self.max_execution_time_seconds}s) exceeded"

        return True, None

    def get_remaining(self) -> dict[str, Any]:
        """Get remaining capacity for all limits."""
        elapsed = 0
        if self.start_time:
            elapsed = (datetime.now() - self.start_time).total_seconds()

        return {
            "iterations": self.max_iterations - self.current_iterations,
            "tool_calls": self.max_tool_calls - self.current_tool_calls,
            "tokens": self.max_tokens_per_run - self.current_tokens,
            "time_seconds": max(0, self.max_execution_time_seconds - elapsed),
            "cost_usd": (self.max_cost_usd - self.current_cost if self.max_cost_usd else None),
        }


@dataclass
class ApprovalRequest:
    """Request for user approval of an action."""

    action_category: ActionCategory
    action_description: str
    tool_name: str | None = None
    parameters: dict[str, Any] | None = None
    risk_level: str = "medium"  # low, medium, high, critical
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "action_category": self.action_category.value,
            "action_description": self.action_description,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "risk_level": self.risk_level,
            "timestamp": self.timestamp.isoformat(),
        }


class AutonomyConfig:
    """
    Main autonomy configuration class.

    Combines autonomy level, permission flags, and safety limits
    to provide comprehensive control over agent behavior.
    """

    def __init__(
        self,
        level: AutonomyLevel = AutonomyLevel.GUIDED,
        permissions: PermissionFlags | None = None,
        limits: SafetyLimits | None = None,
    ):
        """
        Initialize autonomy configuration.

        Args:
            level: Autonomy level controlling approval requirements
            permissions: Fine-grained permission flags
            limits: Safety limits for execution
        """
        self.level = level
        self.permissions = permissions or PermissionFlags()
        self.limits = limits or SafetyLimits()

        # Pending approval requests
        self._pending_approvals: list[ApprovalRequest] = []

        # Approval callback (set by PlanActFlow)
        self._approval_callback: callable | None = None

        logger.info(f"Autonomy config initialized: level={level.value}")

    def set_approval_callback(self, callback: callable) -> None:
        """Set callback for requesting user approval."""
        self._approval_callback = callback

    def requires_approval(self, action_category: ActionCategory) -> bool:
        """
        Check if an action category requires user approval.

        Args:
            action_category: The category of action being performed

        Returns:
            True if approval is required, False otherwise
        """
        # First check permission flags - if disabled, action is blocked entirely
        permission_map = {
            ActionCategory.CREDENTIAL_ACCESS: self.permissions.allow_credential_access,
            ActionCategory.EXTERNAL_REQUEST: self.permissions.allow_external_requests,
            ActionCategory.FILE_WRITE: self.permissions.allow_file_system_write,
            ActionCategory.FILE_DELETE: self.permissions.allow_file_system_delete,
            ActionCategory.SHELL_EXECUTE: self.permissions.allow_shell_execute,
            ActionCategory.BROWSER_NAVIGATE: self.permissions.allow_browser_navigation,
            ActionCategory.PAYMENT: self.permissions.allow_payment_operations,
            ActionCategory.DATA_MODIFICATION: self.permissions.allow_data_modification,
            ActionCategory.SYSTEM_CONFIG: self.permissions.allow_system_config,
        }

        # If permission is disabled, always require approval (which will be denied)
        if action_category in permission_map and not permission_map[action_category]:
            return True

        # Check autonomy level requirements
        required_confirmations = CONFIRMATION_REQUIRED.get(self.level, set())
        return action_category in required_confirmations

    def is_action_allowed(self, action_category: ActionCategory) -> bool:
        """
        Check if an action category is allowed (regardless of approval).

        Args:
            action_category: The category of action being performed

        Returns:
            True if allowed, False if blocked by permissions
        """
        permission_map = {
            ActionCategory.CREDENTIAL_ACCESS: self.permissions.allow_credential_access,
            ActionCategory.EXTERNAL_REQUEST: self.permissions.allow_external_requests,
            ActionCategory.FILE_WRITE: self.permissions.allow_file_system_write,
            ActionCategory.FILE_DELETE: self.permissions.allow_file_system_delete,
            ActionCategory.SHELL_EXECUTE: self.permissions.allow_shell_execute,
            ActionCategory.BROWSER_NAVIGATE: self.permissions.allow_browser_navigation,
            ActionCategory.PAYMENT: self.permissions.allow_payment_operations,
            ActionCategory.DATA_MODIFICATION: self.permissions.allow_data_modification,
            ActionCategory.SYSTEM_CONFIG: self.permissions.allow_system_config,
        }

        return permission_map.get(action_category, True)

    async def request_approval(
        self,
        action_category: ActionCategory,
        action_description: str,
        tool_name: str | None = None,
        parameters: dict[str, Any] | None = None,
        risk_level: str = "medium",
    ) -> bool:
        """
        Request approval for an action if required.

        Args:
            action_category: Category of action
            action_description: Human-readable description
            tool_name: Name of the tool (if applicable)
            parameters: Tool parameters (if applicable)
            risk_level: Risk level (low, medium, high, critical)

        Returns:
            True if approved (or no approval needed), False if denied
        """
        # Check if action is allowed at all
        if not self.is_action_allowed(action_category):
            logger.warning(f"Action blocked by permissions: {action_category.value} - {action_description}")
            return False

        # Check if approval is required
        if not self.requires_approval(action_category):
            logger.debug(f"No approval required for {action_category.value}")
            return True

        # Create approval request
        request = ApprovalRequest(
            action_category=action_category,
            action_description=action_description,
            tool_name=tool_name,
            parameters=parameters,
            risk_level=risk_level,
        )

        # If callback is set, request approval
        if self._approval_callback:
            try:
                approved = await self._approval_callback(request)
                if approved:
                    logger.info(f"Action approved: {action_description}")
                else:
                    logger.warning(f"Action denied: {action_description}")
                return approved
            except Exception as e:
                logger.error(f"Approval callback failed: {e}")
                return False

        # No callback - add to pending and block
        self._pending_approvals.append(request)
        logger.warning(f"Action requires approval but no callback set: {action_description}")
        return False

    def categorize_tool(self, tool_name: str) -> ActionCategory:
        """
        Categorize a tool name into an action category.

        Args:
            tool_name: Name of the tool

        Returns:
            Appropriate ActionCategory for the tool
        """
        tool_lower = tool_name.lower()

        # Credential-related tools
        if any(kw in tool_lower for kw in ["credential", "password", "secret", "key", "auth"]):
            return ActionCategory.CREDENTIAL_ACCESS

        # File operations
        if any(kw in tool_lower for kw in ["file_write", "file_create", "save"]):
            return ActionCategory.FILE_WRITE
        if any(kw in tool_lower for kw in ["file_delete", "remove", "rm"]):
            return ActionCategory.FILE_DELETE

        # Shell/command execution
        if any(kw in tool_lower for kw in ["shell", "exec", "command", "bash", "run"]):
            return ActionCategory.SHELL_EXECUTE

        # Browser/web
        if any(kw in tool_lower for kw in ["browser", "navigate", "click", "page"]):
            return ActionCategory.BROWSER_NAVIGATE
        if any(kw in tool_lower for kw in ["search", "fetch", "request", "api"]):
            return ActionCategory.EXTERNAL_REQUEST

        # Payment
        if any(kw in tool_lower for kw in ["pay", "purchase", "buy", "charge", "billing"]):
            return ActionCategory.PAYMENT

        # Data modification
        if any(kw in tool_lower for kw in ["update", "modify", "edit", "change"]):
            return ActionCategory.DATA_MODIFICATION

        # Default to external request for unknown tools
        return ActionCategory.NETWORK_REQUEST

    def check_limits(self) -> tuple[bool, str | None]:
        """
        Check all safety limits.

        Returns:
            Tuple of (within_limits, reason_if_exceeded)
        """
        return self.limits.check_all_limits()

    def start_run(self) -> None:
        """Start a new run, resetting limit counters."""
        self.limits.start_run()
        self._pending_approvals.clear()

    def get_status(self) -> dict[str, Any]:
        """Get current autonomy status for monitoring."""
        within_limits, reason = self.check_limits()
        return {
            "autonomy_level": self.level.value,
            "within_limits": within_limits,
            "limit_exceeded_reason": reason,
            "remaining": self.limits.get_remaining(),
            "pending_approvals": len(self._pending_approvals),
            "current_stats": {
                "iterations": self.limits.current_iterations,
                "tool_calls": self.limits.current_tool_calls,
                "tokens": self.limits.current_tokens,
                "cost_usd": self.limits.current_cost,
            },
        }

    @classmethod
    def from_settings(cls, settings: Any) -> "AutonomyConfig":
        """
        Create AutonomyConfig from application settings.

        Args:
            settings: Application settings object

        Returns:
            Configured AutonomyConfig instance
        """
        # Map string level to enum
        level_str = getattr(settings, "autonomy_level", "guided")
        try:
            level = AutonomyLevel(level_str.lower())
        except ValueError:
            level = AutonomyLevel.GUIDED
            logger.warning(f"Invalid autonomy level '{level_str}', defaulting to GUIDED")

        # Build permission flags from settings
        permissions = PermissionFlags(
            allow_credential_access=getattr(settings, "allow_credential_access", True),
            allow_external_requests=getattr(settings, "allow_external_requests", True),
            allow_file_system_write=getattr(settings, "allow_file_system_write", True),
            allow_file_system_delete=getattr(settings, "allow_file_system_delete", False),
            allow_shell_execute=getattr(settings, "allow_shell_execute", True),
            allow_browser_navigation=getattr(settings, "allow_browser_navigation", True),
            allow_payment_operations=getattr(settings, "allow_payment_operations", False),
        )

        # Build safety limits from settings
        limits = SafetyLimits(
            max_iterations=getattr(settings, "max_iterations", 50),
            max_tool_calls=getattr(settings, "max_tool_calls", 100),
            max_execution_time_seconds=getattr(settings, "max_execution_time_seconds", 1800),
            max_tokens_per_run=getattr(settings, "max_tokens_per_run", 500000),
            max_cost_usd=getattr(settings, "max_cost_usd", None),
        )

        return cls(level=level, permissions=permissions, limits=limits)


# Singleton instance
_autonomy_config: AutonomyConfig | None = None


def get_autonomy_config() -> AutonomyConfig:
    """Get the global autonomy configuration singleton."""
    global _autonomy_config
    if _autonomy_config is None:
        _autonomy_config = AutonomyConfig()
    return _autonomy_config


def set_autonomy_config(config: AutonomyConfig) -> None:
    """Set the global autonomy configuration singleton."""
    global _autonomy_config
    _autonomy_config = config
    logger.info(f"Global autonomy config set to level: {config.level.value}")
