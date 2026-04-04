"""Tool permission model for configurable allow/deny rules.

ToolPermissionRule maps a glob-style tool name pattern to an action.
PermissionPolicy holds an ordered list of rules; first match wins.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class PermissionAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class PermissionTier(IntEnum):
    """Ordered permission tiers for tool execution."""

    READ_ONLY = 0
    SANDBOX_WRITE = 1
    WORKSPACE_WRITE = 2
    DANGER = 3

    def as_str(self) -> str:
        """Return the external label used in user-facing messages."""
        return {
            PermissionTier.READ_ONLY: "read-only",
            PermissionTier.SANDBOX_WRITE: "sandbox-write",
            PermissionTier.WORKSPACE_WRITE: "workspace-write",
            PermissionTier.DANGER: "danger-full-access",
        }[self]


@dataclass(frozen=True)
class ToolPermissionRule:
    """A single permission rule for a tool name pattern.

    Attributes:
        tool_pattern: Glob pattern matched against the tool function name
                      (e.g. "shell_*", "file_write", "*").
        action: ALLOW or DENY.
        reason: Human-readable explanation used in denial messages.
    """

    tool_pattern: str
    action: PermissionAction
    reason: str = ""

    def matches(self, function_name: str) -> bool:
        """Return True if *function_name* matches this rule's pattern."""
        return fnmatch.fnmatch(function_name, self.tool_pattern)


@dataclass
class PermissionPolicy:
    """Ordered list of ToolPermissionRule instances.

    Evaluation: first matching rule wins.
    If no rule matches, the default action is ALLOW.
    """

    rules: list[ToolPermissionRule] = field(default_factory=list)

    def evaluate(self, function_name: str) -> tuple[PermissionAction, str]:
        """Return the action and reason for the given function name.

        Returns:
            (PermissionAction.ALLOW, "") if no rule matches or the first
            matching rule allows; (PermissionAction.DENY, reason) otherwise.
        """
        for rule in self.rules:
            if rule.matches(function_name):
                return rule.action, rule.reason
        return PermissionAction.ALLOW, ""

    def is_denied(self, function_name: str) -> tuple[bool, str]:
        """Convenience: returns (True, reason) when tool is denied."""
        action, reason = self.evaluate(function_name)
        return action == PermissionAction.DENY, reason
