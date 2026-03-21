"""Shared enums for application configuration.

These enums are defined separately to avoid circular imports between
config modules and any code that imports from config.
"""

from enum import Enum


class StreamingMode(str, Enum):
    """Sandbox streaming mode selection."""

    CDP_ONLY = "cdp_only"


class SandboxLifecycleMode(str, Enum):
    """Sandbox lifecycle mode selection."""

    STATIC = "static"
    EPHEMERAL = "ephemeral"


class FlowMode(str, Enum):
    """Unified flow engine selection.

    Controls which execution flow is used for agent tasks.
    Replaces the legacy enable_coordinator boolean.
    """

    PLAN_ACT = "plan_act"  # Default: custom PlanActFlow
    COORDINATOR = "coordinator"  # Swarm coordinator mode
